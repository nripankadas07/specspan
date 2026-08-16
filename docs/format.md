# Requirement format

A requirement begins at a Markdown heading shaped as:

```text
# REQ-IDENTIFIER: Human-readable title
```

Identifiers use uppercase letters, digits, and hyphens. Supported fields are:

- `Status`: `active` by default; `draft`, `retired`, and `deprecated` do not
  require evidence.
- `Priority`: free text, `should` by default.
- `Depends-On`: comma-separated requirement IDs.
- `Must`: repeatable positive constraint.
- `Must-Not`: repeatable negative constraint.
- `Acceptance`: inline text or a following Markdown bullet list.

Exact normalized clauses present in both `Must` and `Must-Not` are reported as
contradictions. SpecSpan intentionally does not infer semantic contradictions
from arbitrary natural language.

Source annotations use `@spec REQ-ID`. Multiple annotations on a line are
supported. Evidence includes the relative path, line, source/test kind, and
truncated source line.

Only non-symlink regular Markdown and source files are input. Symlinked files or
directories and special files such as FIFOs are not evidence.

Structured headings and fields inside fenced Markdown code blocks are examples,
not live requirements, and are ignored. An existing specification directory
with no live structured requirements produces a `no-requirements` error.

Markdown reports encode every dynamic identifier, status, path, message, and
impact reason as literal text. HTML reports escape the same values.
