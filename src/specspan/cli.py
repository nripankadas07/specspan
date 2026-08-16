"""SpecSpan command-line interface."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from .analyzer import analyze, impact, load_changed_files
from .reporting import write_bundle


def _write_demo_fixture(root: Path) -> None:
    specs = root / "specs"
    source = root / "src"
    tests = root / "tests"
    specs.mkdir(parents=True)
    source.mkdir()
    tests.mkdir()
    (specs / "product.md").write_text(
        "# REQ-CORE-001: Authorize transfers\n"
        "Status: active\nMust: Reject unauthorized transfers\n"
        "Acceptance:\n- An unauthorized transfer is rejected.\n\n"
        "# REQ-TRANSFER-001: Execute a transfer\n"
        "Status: active\nDepends-On: REQ-CORE-001\n"
        "Must: Move the amount exactly once\n"
        "Acceptance:\n- A valid transfer updates the balance.\n\n"
        "# REQ-AUDIT-001: Record the outcome\n"
        "Status: active\nDepends-On: REQ-TRANSFER-001\n"
        "Must: Record one outcome event\n",
        encoding="utf-8",
    )
    (source / "authorization.py").write_text(
        "def authorized(balance, amount):\n"
        "    \"\"\"@spec REQ-CORE-001\"\"\"\n"
        "    return amount > 0 and balance >= amount\n",
        encoding="utf-8",
    )
    (source / "transfer.py").write_text(
        "def transfer(balance, amount):\n"
        "    \"\"\"@spec REQ-TRANSFER-001\"\"\"\n"
        "    return balance - amount\n\n"
        "def audit(status):\n"
        "    \"\"\"@spec REQ-AUDIT-001\"\"\"\n"
        "    return 'transfer:' + status\n",
        encoding="utf-8",
    )
    (tests / "test_transfer.py").write_text(
        "def test_authorized():\n"
        "    \"\"\"@spec REQ-CORE-001\"\"\"\n"
        "    assert True\n\n"
        "def test_transfer():\n"
        "    \"\"\"@spec REQ-TRANSFER-001\"\"\"\n"
        "    assert True\n",
        encoding="utf-8",
    )


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--spec-dir", default="specs")
    parser.add_argument("--out", default="artifacts/specspan")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specspan", description="Trace structured requirements to code and tests.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="analyze requirement traceability")
    _common(check)
    check.add_argument("--fail-on", choices=["none", "warning", "error"], default="error")

    impact_parser = sub.add_parser("impact", help="map a supplied changed-file list to requirements")
    _common(impact_parser)
    impact_parser.add_argument("--changed-files", required=True)
    impact_parser.add_argument("--changed", action="append", default=[])

    demo = sub.add_parser("demo", help="analyze the bundled deterministic example")
    demo.add_argument("--out", default="artifacts/demo")
    return parser


def _should_fail(artifact, threshold: str) -> bool:
    if threshold == "none":
        return False
    if threshold == "error":
        return artifact["summary"]["errors"] > 0
    return artifact["summary"]["errors"] > 0 or artifact["summary"]["warnings"] > 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "check":
            artifact = analyze(args.root, args.spec_dir)
            output = write_bundle(artifact, args.out)
            print("%d requirements; %d errors; %d warnings; report %s" % (artifact["summary"]["unique_requirements"], artifact["summary"]["errors"], artifact["summary"]["warnings"], output / "report.html"))
            return 1 if _should_fail(artifact, args.fail_on) else 0
        if args.command == "impact":
            artifact = analyze(args.root, args.spec_dir)
            changed = load_changed_files(args.changed_files) + list(args.changed)
            impact_value = impact(artifact, changed)
            output = write_bundle(artifact, args.out, impact_value)
            print("%d changed files -> %d impacted requirements; report %s" % (impact_value["summary"]["changed_files"], impact_value["summary"]["total_requirements"], output / "report.html"))
            return 0
        if args.command == "demo":
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "specspan-demo"
                _write_demo_fixture(root)
                artifact = analyze(str(root), "specs")
                changed = ["src/authorization.py"]
                impact_value = impact(artifact, changed)
            output = write_bundle(artifact, args.out, impact_value)
            print("demo: %d requirements, %d findings, %d impacted" % (artifact["summary"]["unique_requirements"], artifact["summary"]["findings"], impact_value["summary"]["total_requirements"]))
            print("report: %s" % (output / "report.html"))
            return 0
    except (OSError, ValueError) as exc:
        print("specspan: error: %s" % exc, file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
