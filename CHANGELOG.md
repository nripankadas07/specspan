# Changelog

## 0.1.1 - 2026-08-16

- Replace recursive strongly connected component and cycle walks with stable
  iterative graph algorithms for deeply chained requirement sets.
- Reject malformed JSON-shaped changed-file lists instead of reinterpreting
  them as newline-delimited filenames.
- Stage complete report bundles and publish them through symlink-safe,
  descriptor-relative atomic renames with backup/rollback on failure; reject
  every unverified path symlink and non-regular artifact target, and fail closed
  when descriptor-relative operations are unavailable.
- Percent-encode SARIF artifact paths as URI references.
- Publish SPDX `License-Expression` and bundled license metadata in wheels.
- Read changed-file lists only through stable, non-blocking, no-follow regular
  descriptors; accept at most one leading UTF-8 BOM and reject invalid UTF-8,
  C0/C1 controls, format controls, and mid-stream BOMs.
- Serialize cooperating bundle writers with a verified-directory advisory lock,
  reconcile renames that complete before reporting an error, and guard ownership
  across every descriptor/stream error path.
- Ship tests, fixtures, examples, demo goldens, and documentation in the sdist;
  extract it, run its full suite, and build the release wheel from it in CI.

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
