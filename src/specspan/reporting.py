"""Serialize SpecSpan artifacts and reports."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from pathlib import Path
from typing import Any, Mapping, Optional


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _markdown_literal(value: Any) -> str:
    """Encode untrusted values so they remain literal Markdown text."""
    safe = []
    for character in str(value):
        if character.isalnum() or character == " ":
            safe.append(character)
        else:
            safe.append("&#%d;" % ord(character))
    return "".join(safe)


def _csv_literal(value: Any) -> str:
    """Keep untrusted cells from being interpreted as spreadsheet formulae."""
    text = str(value)
    stripped = text.lstrip(" \t\r\n")
    if text.startswith(("\t", "\r", "\n")) or stripped.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _csv_report(artifact: Mapping[str, Any]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["requirement_id", "status", "spec_path", "code_paths", "test_paths", "verified"])
    for item in artifact["graph"]["traceability"]:
        writer.writerow(
            [
                _csv_literal(item["requirement_id"]),
                _csv_literal(item["status"]),
                _csv_literal(item["spec_path"]),
                _csv_literal(";".join(item["code_paths"])),
                _csv_literal(";".join(item["test_paths"])),
                _csv_literal(str(item["verified"]).lower()),
            ]
        )
    return output.getvalue()


def sarif(artifact: Mapping[str, Any]) -> Dict[str, Any]:
    rule_ids = sorted({item["rule"] for item in artifact["findings"]})
    rules = [
        {"id": rule, "shortDescription": {"text": rule.replace("-", " ").title()}}
        for rule in rule_ids
    ]
    results = []
    for item in artifact["findings"]:
        results.append(
            {
                "ruleId": item["rule"],
                "level": item["level"],
                "message": {"text": item["message"]},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": item["path"]},
                            "region": {"startLine": item["line"]},
                        }
                    }
                ],
                "properties": {"requirement_id": item.get("requirement_id", "")},
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "specspan", "version": artifact["tool_version"], "rules": rules}}, "results": results}],
    }


def markdown_report(artifact: Mapping[str, Any], impact_value: Optional[Mapping[str, Any]] = None) -> str:
    summary = artifact["summary"]
    lines = [
        "# SpecSpan traceability report",
        "",
        "- Requirements: %d (%d unique)" % (summary["requirements"], summary["unique_requirements"]),
        "- Verified: %d" % summary["verified"],
        "- Findings: %d errors, %d warnings" % (summary["errors"], summary["warnings"]),
        "",
        "## Traceability",
        "",
        "| Requirement | Status | Code | Tests | Verified |",
        "|---|---|---|---|---|",
    ]
    for item in artifact["graph"]["traceability"]:
        lines.append(
            "| `%s` | %s | %s | %s | %s |"
            % (
                _markdown_literal(item["requirement_id"]),
                _markdown_literal(item["status"]),
                "<br>".join(
                    "`%s`" % _markdown_literal(value) for value in item["code_paths"]
                )
                or "—",
                "<br>".join(
                    "`%s`" % _markdown_literal(value) for value in item["test_paths"]
                )
                or "—",
                "yes" if item["verified"] else "no",
            )
        )
    lines.extend(["", "## Findings", ""])
    for item in artifact["findings"]:
        lines.append(
            "- **%s / %s** `%s:%d` — %s"
            % (
                _markdown_literal(item["level"]),
                _markdown_literal(item["rule"]),
                _markdown_literal(item["path"]),
                item["line"],
                _markdown_literal(item["message"]),
            )
        )
    if not artifact["findings"]:
        lines.append("- No findings.")
    if impact_value is not None:
        lines.extend(["", "## Change impact", ""])
        for item in impact_value["impacted"]:
            lines.append(
                "- `%s` — %s"
                % (
                    _markdown_literal(item["requirement_id"]),
                    ", ".join(_markdown_literal(value) for value in item["reasons"]),
                )
            )
        if not impact_value["impacted"]:
            lines.append("- No linked requirements impacted.")
    lines.extend(["", "## Limits", ""])
    lines.extend("- %s" % _markdown_literal(value) for value in artifact["limits"])
    lines.append("")
    return "\n".join(lines)


def html_report(artifact: Mapping[str, Any], impact_value: Optional[Mapping[str, Any]] = None) -> str:
    rows = []
    for item in artifact["graph"]["traceability"]:
        rows.append(
            "<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td><td class='%s'>%s</td></tr>"
            % (
                html.escape(item["requirement_id"]),
                html.escape(item["status"]),
                "<br>".join("<code>%s</code>" % html.escape(value) for value in item["code_paths"]) or "—",
                "<br>".join("<code>%s</code>" % html.escape(value) for value in item["test_paths"]) or "—",
                "ok" if item["verified"] else "bad",
                "verified" if item["verified"] else "missing",
            )
        )
    finding_rows = "".join(
        "<li class='%s'><strong>%s</strong> <code>%s:%d</code> — %s</li>"
        % (
            html.escape(item["level"]),
            html.escape(item["rule"]),
            html.escape(item["path"]),
            item["line"],
            html.escape(item["message"]),
        )
        for item in artifact["findings"]
    ) or "<li>No findings.</li>"
    impact_html = ""
    if impact_value is not None:
        items = "".join(
            "<li><code>%s</code> — %s</li>"
            % (html.escape(item["requirement_id"]), html.escape(", ".join(item["reasons"])))
            for item in impact_value["impacted"]
        ) or "<li>No linked requirements impacted.</li>"
        impact_html = "<section><h2>Change impact</h2><ul>%s</ul></section>" % items
    embedded = html.escape(stable_json({"traceability": artifact, "impact": impact_value}))
    summary = artifact["summary"]
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SpecSpan report</title><style>
body{font:15px system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#182230;background:#f7f9fc}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}.card{background:white;border:1px solid #e4e7ec;padding:16px;border-radius:12px}.n{font-size:28px;font-weight:800}table{width:100%%;border-collapse:collapse;background:white}th,td{text-align:left;padding:10px;border-bottom:1px solid #e4e7ec;vertical-align:top}.ok{color:#067647;font-weight:700}.bad,.error{color:#b42318;font-weight:700}.warning{color:#b54708}section{margin-top:24px;background:white;border:1px solid #e4e7ec;padding:18px;border-radius:12px}pre{background:#101828;color:#f2f4f7;padding:16px;border-radius:8px;overflow:auto}details{margin-top:24px}@media(max-width:700px){.cards{grid-template-columns:1fr 1fr}}
</style><h1>SpecSpan</h1><p>Deterministic requirement → code → test evidence.</p>
<div class="cards"><div class="card"><div class="n">%d</div>requirements</div><div class="card"><div class="n">%d</div>verified</div><div class="card"><div class="n">%d</div>errors</div><div class="card"><div class="n">%d</div>warnings</div></div>
<h2>Traceability</h2><table><thead><tr><th>Requirement</th><th>Status</th><th>Code</th><th>Tests</th><th>State</th></tr></thead><tbody>%s</tbody></table>
<section><h2>Findings</h2><ul>%s</ul></section>%s<details><summary>Canonical artifact</summary><pre>%s</pre></details></html>""" % (
        summary["unique_requirements"], summary["verified"], summary["errors"], summary["warnings"], "".join(rows), finding_rows, impact_html, embedded
    )


def write_bundle(
    artifact: Mapping[str, Any], output_value: str, impact_value: Optional[Mapping[str, Any]] = None
) -> Path:
    output = Path(output_value)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "specspan.json": stable_json(artifact),
        "traceability.csv": _csv_report(artifact),
        "findings.sarif": stable_json(sarif(artifact)),
        "report.md": markdown_report(artifact, impact_value),
        "report.html": html_report(artifact, impact_value),
    }
    if impact_value is not None:
        files["impact.json"] = stable_json(impact_value)
    checksums = []
    for name, content in sorted(files.items()):
        (output / name).write_text(content, encoding="utf-8")
        checksums.append("%s  %s" % (hashlib.sha256(content.encode("utf-8")).hexdigest(), name))
    (output / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    return output
