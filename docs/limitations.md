# Limitations

- Only structured headings, supported fields, and explicit annotations are
  interpreted.
- An annotation is declared evidence, not behavioral proof.
- Test-path classification is conventional and can misclassify unusual layouts.
- Renames are visible only as paths supplied by the caller.
- Impact analysis is file-level, not symbol- or AST-level.
- Contradiction detection covers exact normalized `Must`/`Must-Not` matches.
- SpecSpan does not determine whether acceptance criteria are sufficient.
- Generated code and source suffixes outside the documented set are ignored.
- Symbolic links and all non-regular files are excluded from evidence.
- Changed-file inputs accept relative paths only and do not resolve renames.
- Changed-file list inputs are limited to 8 MiB, strict UTF-8, and at most one
  leading BOM. Tabs/newlines/carriage returns remain valid document whitespace;
  other C0/C1 and Unicode format controls are rejected.
- Inputs beginning with `[` or `{` must be valid JSON rather than line-oriented
  path lists.
- Broken annotations and dependencies are findings, not impact targets.
- CSV output neutralizes leading formula operators; consumers should still
  treat all generated artifacts as untrusted data.
- Markdown output encodes dynamic values as literals; HTML output escapes them.
- Output path components must not be symlinks, and named artifacts must be
  regular files when they already exist. Bundle publication stages all files
  and restores the original set after an in-process publication failure, but a
  concurrent reader can briefly observe sequential atomic renames.
- The directory lock is advisory and coordinates only SpecSpan writers using
  this implementation. Abrupt process/host failure can leave private temporary
  or backup files and a partially published set for manual recovery.
- Secure output fails closed on platforms without descriptor-relative file,
  directory, stat, rename, unlink, and advisory-lock operations.
- No shell, VCS command, code execution, or network access occurs.
