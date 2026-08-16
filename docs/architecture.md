# Architecture

SpecSpan has a read-only analysis pipeline:

1. Walk supported regular files in lexical order, excluding symbolic links,
   special files, ignored directories, and any path outside the root.
2. Parse requirement headings and structured fields from Markdown.
3. Scan supported source files for explicit `@spec REQ-…` annotations.
4. Build requirement-dependency and requirement-evidence edges.
5. Run deterministic graph checks, including strongly connected components for
   dependency cycles.
6. Create one canonical `specspan/v1` artifact.
7. Derive CSV, SARIF, Markdown, HTML, checksums, and optional impact output.

Before a file is opened, `lstat` must identify it as regular. A non-blocking,
no-follow open then verifies descriptor type, identity, and root containment;
this prevents FIFO waits and useful file/symlink replacement races.

No absolute root path, current time, random ID, VCS metadata, or execution
result enters the canonical artifact. Impact analysis starts with supplied file
paths, adds direct spec/evidence links, then walks reverse dependency edges to
find dependent requirements. Evidence and dependency edges whose endpoints do
not exist in the canonical requirement set remain findings and never become
invented impact records.

Changed-file JSON is type-preserving: only a list of non-empty relative strings
is valid. The same normalizer rejects absolute and parent-traversing paths from
both files and repeated CLI arguments.

Cycle diagnostics perform a deterministic graph walk inside each strongly
connected component so every displayed arrow corresponds to a declared edge.
Fenced Markdown code is excluded before requirement headings or fields are
interpreted.

CSV projections prefix formula-shaped cells with a literal apostrophe before
RFC 4180 quoting, so spreadsheet software cannot execute requirement metadata
or paths as formulae.
