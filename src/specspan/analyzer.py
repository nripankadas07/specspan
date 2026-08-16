"""Parse structured Markdown requirements and build a trace graph."""

from __future__ import annotations

import json
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from . import SCHEMA_VERSION, __version__
from .safeio import _close_owned_fd


# Keep the final capture greedy and strip it after matching.  A lazy wildcard
# followed by optional whitespace can require polynomial backtracking on long
# malformed lines; these forms remain linear while preserving the format.
HEADING = re.compile(r"^#{1,6}[ \t]+(REQ-[A-Z0-9][A-Z0-9-]*)[ \t]*:(.*)$")
FIELD = re.compile(r"^(Status|Priority|Depends-On|Must|Must-Not|Acceptance)[ \t]*:(.*)$", re.I)
ANNOTATION = re.compile(r"@spec\s+(REQ-[A-Z0-9][A-Z0-9-]*)\b")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cs", ".rb", ".php", ".sh"}
IGNORED_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "dist", "build", "artifacts", "__pycache__"}
LEVEL_RANK = {"note": 1, "warning": 2, "error": 3}
MAX_CHANGED_FILE_BYTES = 8 * 1024 * 1024
UTF8_BOM = b"\xef\xbb\xbf"


def _normal(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _regular_lstat(path: Path) -> Optional[os.stat_result]:
    try:
        metadata = path.lstat()
    except OSError:
        return None
    return metadata if stat.S_ISREG(metadata.st_mode) else None


def _stable_metadata(metadata: os.stat_result) -> Tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_stable_regular_bytes(path: Path, limit: int) -> bytes:
    """Read one unchanged regular file without following its final component."""
    if not hasattr(os, "O_NOFOLLOW"):
        raise OSError("stable file input requires no-follow file opens")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("input must be a regular file: %s" % path)
    if before.st_size > limit:
        raise ValueError("input exceeds the %d-byte limit: %s" % (limit, path))
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_NOFOLLOW
    )
    descriptor = -1
    try:
        descriptor = os.open(str(path), flags)
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or _stable_metadata(opened_before) != _stable_metadata(before)
        ):
            raise ValueError("input changed while it was opened: %s" % path)
        chunks = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(65536, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise ValueError("input exceeds the %d-byte limit: %s" % (limit, path))
        opened_after = os.fstat(descriptor)
        after = path.lstat()
        if (
            _stable_metadata(opened_after) != _stable_metadata(opened_before)
            or _stable_metadata(after) != _stable_metadata(opened_before)
        ):
            raise ValueError("input changed while it was read: %s" % path)
        return b"".join(chunks)
    finally:
        if descriptor >= 0:
            owned_descriptor = descriptor
            descriptor = -1
            _close_owned_fd(owned_descriptor)


def _read_regular_text(root: Path, path: Path) -> Optional[str]:
    """Read only a stable regular file contained by root.

    The lexical walk filters special files first. This second check, a
    non-blocking no-follow open, and descriptor identity validation prevent a
    path replacement from becoming a FIFO wait or symlink escape.
    """
    before = _regular_lstat(path)
    if before is None:
        return None
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    if resolved != path.absolute():
        return None
    try:
        payload = _read_stable_regular_bytes(path, max(before.st_size + 1, 1))
    except (OSError, ValueError):
        return None
    return payload.decode("utf-8", errors="replace")


def _iter_paths(root: Path, suffixes: Set[str], within: Optional[Path] = None) -> Iterable[Path]:
    start = within or root
    if not start.exists():
        return
    for current, dirs, files in os.walk(str(start)):
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in IGNORED_DIRS and not (Path(current) / name).is_symlink()
        )
        for name in sorted(files):
            path = Path(current) / name
            if path.suffix.lower() in suffixes and _regular_lstat(path) is not None:
                yield path


def parse_requirements(root: Path, spec_dir: Path) -> List[Dict[str, Any]]:
    requirements: List[Dict[str, Any]] = []
    for path in _iter_paths(root, {".md"}, spec_dir):
        text = _read_regular_text(root, path)
        if text is None:
            continue
        relative = _relative(root, path)
        lines = text.splitlines()
        current: Optional[Dict[str, Any]] = None
        acceptance_mode = False
        fence: Optional[Tuple[str, int]] = None
        for number, line in enumerate(lines, 1):
            fence_match = FENCE.match(line)
            if fence_match:
                marker = fence_match.group(1)
                if fence is None:
                    fence = (marker[0], len(marker))
                elif (
                    marker[0] == fence[0]
                    and len(marker) >= fence[1]
                    and not fence_match.group(2).strip()
                ):
                    fence = None
                continue
            if fence is not None:
                continue
            heading = HEADING.match(line)
            if heading:
                current = {
                    "id": heading.group(1),
                    "title": heading.group(2).strip(),
                    "path": relative,
                    "line": number,
                    "status": "active",
                    "priority": "should",
                    "depends_on": [],
                    "must": [],
                    "must_not": [],
                    "acceptance": [],
                }
                requirements.append(current)
                acceptance_mode = False
                continue
            if current is None:
                continue
            field = FIELD.match(line)
            if field:
                key = field.group(1).lower().replace("-", "_")
                value = field.group(2).strip()
                acceptance_mode = key == "acceptance"
                if key in {"status", "priority"}:
                    current[key] = value.lower() if value else current[key]
                elif key == "depends_on":
                    current[key].extend(
                        item.strip().upper() for item in value.split(",") if item.strip()
                    )
                elif key in {"must", "must_not", "acceptance"} and value:
                    current[key].append(value)
                continue
            if acceptance_mode and re.match(r"^\s*[-*]\s+", line):
                current["acceptance"].append(re.sub(r"^\s*[-*]\s+", "", line).strip())
            elif line.strip() and not line.startswith(" "):
                acceptance_mode = False
    for requirement in requirements:
        requirement["depends_on"] = sorted(set(requirement["depends_on"]))
    return requirements


def _is_test_path(relative: str) -> bool:
    path = Path(relative)
    lowered_parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    return bool(
        lowered_parts & {"test", "tests", "spec", "specs", "__tests__"}
        or name.startswith("test_")
        or name.endswith("_test" + path.suffix.lower())
        or ".test." in name
        or ".spec." in name
    )


def parse_evidence(root: Path, spec_dir: Path) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for path in _iter_paths(root, SOURCE_SUFFIXES):
        try:
            path.relative_to(spec_dir)
            continue
        except ValueError:
            pass
        text = _read_regular_text(root, path)
        if text is None:
            continue
        relative = _relative(root, path)
        kind = "test" if _is_test_path(relative) else "code"
        lines = text.splitlines()
        for number, line in enumerate(lines, 1):
            for match in ANNOTATION.finditer(line):
                evidence.append(
                    {
                        "requirement_id": match.group(1),
                        "kind": kind,
                        "path": relative,
                        "line": number,
                        "evidence": line.strip()[:200],
                    }
                )
    return sorted(evidence, key=lambda item: (item["requirement_id"], item["kind"], item["path"], item["line"]))


def _strong_components(nodes: Sequence[str], edges: Mapping[str, Sequence[str]]) -> List[List[str]]:
    """Iterative Kosaraju SCC in stable traversal order."""
    node_set = set(nodes)
    adjacency = {
        node: sorted(set(edges.get(node, [])) & node_set) for node in node_set
    }
    visited: Set[str] = set()
    finished: List[str] = []
    for start in sorted(node_set):
        if start in visited:
            continue
        visited.add(start)
        stack: List[Tuple[str, int]] = [(start, 0)]
        while stack:
            node, index = stack[-1]
            targets = adjacency[node]
            if index >= len(targets):
                stack.pop()
                finished.append(node)
                continue
            target = targets[index]
            stack[-1] = (node, index + 1)
            if target not in visited:
                visited.add(target)
                stack.append((target, 0))

    reverse: Dict[str, List[str]] = {node: [] for node in node_set}
    for source, targets in adjacency.items():
        for target in targets:
            reverse[target].append(source)
    for targets in reverse.values():
        targets.sort()

    assigned: Set[str] = set()
    result: List[List[str]] = []
    for start in reversed(finished):
        if start in assigned:
            continue
        assigned.add(start)
        component: List[str] = []
        pending = [start]
        while pending:
            node = pending.pop()
            component.append(node)
            for target in reversed(reverse[node]):
                if target not in assigned:
                    assigned.add(target)
                    pending.append(target)
        result.append(sorted(component))
    return sorted(result)


def _directed_cycle(component: Sequence[str], edges: Mapping[str, Sequence[str]]) -> List[str]:
    """Return a deterministic cycle whose every adjacent pair is a real edge."""
    allowed = set(component)
    start = min(component)
    if start in edges.get(start, []):
        return [start, start]

    visited = {start}
    path = [start]
    stack: List[Tuple[str, int, List[str]]] = [
        (start, 0, sorted(set(edges.get(start, [])) & allowed))
    ]
    while stack:
        node, index, targets = stack[-1]
        if index >= len(targets):
            stack.pop()
            path.pop()
            continue
        target = targets[index]
        stack[-1] = (node, index + 1, targets)
        if target == start:
            return path + [start]
        if target in visited:
            continue
        visited.add(target)
        path.append(target)
        stack.append((target, 0, sorted(set(edges.get(target, [])) & allowed)))
    raise ValueError("strongly connected component did not contain a directed cycle")


def _finding(
    rule: str,
    level: str,
    message: str,
    path: str,
    line: int,
    requirement_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "rule": rule,
        "level": level,
        "message": message,
        "path": path,
        "line": line,
    }
    if requirement_id:
        payload["requirement_id"] = requirement_id
    return payload


def analyze(root_value: str, spec_dir_value: str = "specs") -> Dict[str, Any]:
    supplied_root = Path(root_value)
    if supplied_root.is_symlink():
        raise ValueError("root must not be a symbolic link: %s" % root_value)
    root = supplied_root.resolve()
    if not root.is_dir():
        raise ValueError("root must be an existing directory: %s" % root_value)
    spec_candidate = root / spec_dir_value
    try:
        spec_dir = spec_candidate.resolve()
    except OSError as exc:
        raise ValueError("cannot resolve spec directory: %s" % spec_dir_value) from exc
    try:
        spec_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("spec directory must be inside root") from exc
    if spec_dir != spec_candidate.absolute():
        raise ValueError("spec directory must not traverse a symbolic link")
    if not spec_dir.is_dir():
        raise ValueError("spec directory does not exist: %s" % spec_dir_value)

    requirements = parse_requirements(root, spec_dir)
    evidence = parse_evidence(root, spec_dir)
    findings: List[Dict[str, Any]] = []
    if not requirements:
        findings.append(
            _finding(
                "no-requirements",
                "error",
                "Specification directory contains no structured REQ requirements.",
                _relative(root, spec_dir),
                1,
            )
        )

    by_id: Dict[str, List[Dict[str, Any]]] = {}
    for requirement in requirements:
        by_id.setdefault(requirement["id"], []).append(requirement)
    canonical = {identifier: values[0] for identifier, values in sorted(by_id.items())}

    for identifier, values in sorted(by_id.items()):
        for duplicate in values[1:]:
            findings.append(
                _finding(
                    "duplicate-requirement",
                    "error",
                    "%s is declared more than once." % identifier,
                    duplicate["path"],
                    duplicate["line"],
                    identifier,
                )
            )

    edges: Dict[str, List[str]] = {identifier: [] for identifier in canonical}
    for requirement in requirements:
        identifier = requirement["id"]
        must = {_normal(value) for value in requirement["must"] if _normal(value)}
        must_not = {_normal(value) for value in requirement["must_not"] if _normal(value)}
        for contradiction in sorted(must & must_not):
            findings.append(
                _finding(
                    "contradictory-constraint",
                    "error",
                    "%s both requires and prohibits: %s" % (identifier, contradiction),
                    requirement["path"],
                    requirement["line"],
                    identifier,
                )
            )
        for dependency in requirement["depends_on"]:
            if dependency not in canonical:
                findings.append(
                    _finding(
                        "broken-dependency",
                        "error",
                        "%s depends on unknown %s." % (identifier, dependency),
                        requirement["path"],
                        requirement["line"],
                        identifier,
                    )
                )
            else:
                edges.setdefault(identifier, []).append(dependency)

    for component in _strong_components(sorted(canonical), edges):
        self_cycle = len(component) == 1 and component[0] in edges.get(component[0], [])
        if len(component) > 1 or self_cycle:
            cycle = _directed_cycle(component, edges)
            requirement = canonical[cycle[0]]
            findings.append(
                _finding(
                    "dependency-cycle",
                    "error",
                    "Dependency cycle: %s." % " -> ".join(cycle),
                    requirement["path"],
                    requirement["line"],
                    cycle[0],
                )
            )

    linked: Dict[str, List[Dict[str, Any]]] = {identifier: [] for identifier in canonical}
    for item in evidence:
        identifier = item["requirement_id"]
        if identifier not in canonical:
            findings.append(
                _finding(
                    "broken-annotation",
                    "error",
                    "Annotation references unknown %s." % identifier,
                    item["path"],
                    item["line"],
                    identifier,
                )
            )
        else:
            linked[identifier].append(item)

    traceability = []
    for identifier, requirement in sorted(canonical.items()):
        links = linked[identifier]
        code_links = sorted({item["path"] for item in links if item["kind"] == "code"})
        test_links = sorted({item["path"] for item in links if item["kind"] == "test"})
        active = requirement["status"] not in {"draft", "retired", "deprecated"}
        if active and not links:
            findings.append(
                _finding(
                    "orphan-requirement",
                    "warning",
                    "%s has no code or test evidence." % identifier,
                    requirement["path"],
                    requirement["line"],
                    identifier,
                )
            )
        if active and not test_links:
            findings.append(
                _finding(
                    "unverified-requirement",
                    "warning",
                    "%s has no test evidence." % identifier,
                    requirement["path"],
                    requirement["line"],
                    identifier,
                )
            )
        traceability.append(
            {
                "requirement_id": identifier,
                "status": requirement["status"],
                "spec_path": requirement["path"],
                "code_paths": code_links,
                "test_paths": test_links,
                "verified": bool(test_links),
            }
        )

    findings.sort(
        key=lambda item: (-LEVEL_RANK[item["level"]], item["path"], item["line"], item["rule"], item.get("requirement_id", ""))
    )
    dependencies = [
        {"from": identifier, "to": dependency}
        for identifier in sorted(edges)
        for dependency in sorted(set(edges[identifier]))
    ]
    summary = {
        "requirements": len(requirements),
        "unique_requirements": len(canonical),
        "evidence_links": len(evidence),
        "verified": sum(1 for item in traceability if item["verified"]),
        "findings": len(findings),
        "errors": sum(1 for item in findings if item["level"] == "error"),
        "warnings": sum(1 for item in findings if item["level"] == "warning"),
        "notes": sum(1 for item in findings if item["level"] == "note"),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "subject": {"name": root.name, "root": ".", "spec_dir": Path(spec_dir_value).as_posix()},
        "summary": summary,
        "requirements": requirements,
        "evidence": evidence,
        "graph": {"dependencies": dependencies, "traceability": traceability},
        "findings": findings,
        "limits": [
            "Only structured REQ headings, fields, and explicit @spec annotations are interpreted.",
            "Trace links prove declared association, not behavioral correctness or test quality.",
            "Impact analysis consumes a supplied file list and never invokes version-control commands.",
            "Contradiction checks compare normalized explicit Must and Must-Not clauses only.",
            "Fenced Markdown code blocks are ignored while parsing requirements.",
        ],
    }


def _normalize_changed(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("changed paths must be non-empty strings")
    if any(unicodedata.category(character) in {"Cc", "Cf"} for character in value):
        raise ValueError("changed paths must not contain control characters: %r" % value)
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if (
        not normalized
        or normalized in {".", ".."}
        or normalized.startswith("/")
        or normalized.startswith("//")
        or re.match(r"^[A-Za-z]:/", normalized)
        or "\x00" in normalized
        or ".." in normalized.split("/")
    ):
        raise ValueError("changed paths must be non-empty relative paths: %r" % value)
    return normalized


def _decode_changed_file_list(payload: bytes, path: Path) -> str:
    if payload.startswith(UTF8_BOM):
        payload = payload[len(UTF8_BOM) :]
    if UTF8_BOM in payload:
        raise ValueError(
            "changed-file list may contain one UTF-8 BOM only at byte zero: %s" % path
        )
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("changed-file list is not valid UTF-8 %s: %s" % (path, exc)) from exc
    disallowed = [
        character
        for character in text
        if unicodedata.category(character) in {"Cc", "Cf"}
        and character not in {"\t", "\n", "\r"}
    ]
    if disallowed:
        raise ValueError("changed-file list contains disallowed control characters: %s" % path)
    return text


def load_changed_files(path_value: str) -> List[str]:
    path = Path(path_value)
    try:
        payload = _read_stable_regular_bytes(path, MAX_CHANGED_FILE_BYTES)
        text = _decode_changed_file_list(payload, path)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read changed-file list %s: %s" % (path, exc)) from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        if text.lstrip().startswith(("[", "{")):
            raise ValueError("cannot parse changed-file JSON %s: %s" % (path, exc)) from exc
        values = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    else:
        if not isinstance(parsed, list):
            raise ValueError("changed-file JSON must be a list of non-empty relative strings")
        if any(not isinstance(item, str) or not item.strip() for item in parsed):
            raise ValueError("changed-file JSON must be a list of non-empty relative strings")
        values = parsed
    return sorted({_normalize_changed(value) for value in values})


def impact(artifact: Mapping[str, Any], changed_files: Sequence[str]) -> Dict[str, Any]:
    changed = sorted({_normalize_changed(value) for value in changed_files})
    changed_set = set(changed)
    requirement_ids = {item["id"] for item in artifact.get("requirements", [])}
    direct: Dict[str, Set[str]] = {}
    for requirement in artifact.get("requirements", []):
        if requirement["path"] in changed_set:
            direct.setdefault(requirement["id"], set()).add("spec:%s" % requirement["path"])
    for item in artifact.get("evidence", []):
        if item["path"] in changed_set and item["requirement_id"] in requirement_ids:
            direct.setdefault(item["requirement_id"], set()).add("%s:%s" % (item["kind"], item["path"]))

    reverse: Dict[str, Set[str]] = {}
    for edge in artifact.get("graph", {}).get("dependencies", []):
        if edge["from"] in requirement_ids and edge["to"] in requirement_ids:
            reverse.setdefault(edge["to"], set()).add(edge["from"])
    reasons: Dict[str, Set[str]] = {identifier: set(values) for identifier, values in direct.items()}
    queue = sorted(reasons)
    while queue:
        current = queue.pop(0)
        for dependent in sorted(reverse.get(current, set())):
            before = bool(reasons.get(dependent))
            reasons.setdefault(dependent, set()).add("depends-on:%s" % current)
            if not before:
                queue.append(dependent)
    return {
        "schema_version": "specspan-impact/v1",
        "changed_files": changed,
        "impacted": [
            {"requirement_id": identifier, "direct": identifier in direct, "reasons": sorted(values)}
            for identifier, values in sorted(reasons.items())
        ],
        "summary": {
            "changed_files": len(changed),
            "direct_requirements": len(direct),
            "total_requirements": len(reasons),
        },
    }
