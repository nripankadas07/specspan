# Changelog

## 0.1.0 - 2026-08-16

- Initial `specspan/v1` traceability artifact.
- Structured Markdown parsing and explicit code/test annotations.
- Contradiction, duplicate, broken-link, dependency-cycle, orphan, and
  unverified checks.
- Caller-supplied changed-file impact with reverse-dependency propagation.
- JSON, CSV, SARIF, Markdown, HTML, and checksum reports.
- Empty-spec errors, fenced-code exclusion, and edge-valid dependency-cycle paths.
- Self-contained installed-wheel demo fixtures and clean-wheel regression coverage.
- Skip symbolic links and non-regular files before reading, then revalidate file
  identity and containment after a non-blocking no-follow open.
- Enforce typed, non-empty relative changed-file paths for JSON, line, API, and
  CLI inputs.
- Encode every dynamic Markdown report field as literal text.
- Exclude broken evidence/dependency targets from impact propagation.
- Neutralize formula-shaped values in every CSV data cell.
