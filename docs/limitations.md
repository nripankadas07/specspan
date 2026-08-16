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
- Broken annotations and dependencies are findings, not impact targets.
- CSV output neutralizes leading formula operators; consumers should still
  treat all generated artifacts as untrusted data.
- Markdown output encodes dynamic values as literals; HTML output escapes them.
- No shell, VCS command, code execution, or network access occurs.
