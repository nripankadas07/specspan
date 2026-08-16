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
both files and repeated CLI arguments. The changed-file list itself is opened
as a non-blocking, no-follow regular descriptor and its identity, size, and
timestamps must remain stable through the read. Decoding is strict UTF-8 with
at most one BOM at byte zero; path controls and document C0/C1/format controls
outside JSON/line whitespace are rejected.

Cycle diagnostics perform a deterministic graph walk inside each strongly
connected component so every displayed arrow corresponds to a declared edge.
Both strongly connected component discovery and cycle extraction use explicit
stacks, so valid dependency depth is not limited by Python's recursion limit.
Fenced Markdown code is excluded before requirement headings or fields are
interpreted.

Malformed content beginning with a JSON object or array delimiter is treated as
invalid JSON and never reinterpreted as a line-oriented path. The complete
report bundle is staged in unique regular files and flushed before publication.
A verified-directory advisory lock serializes cooperating writers from
preflight through cleanup. Existing artifacts are moved to private backups;
descriptor-relative atomic renames restore the complete original set if any
publication fails. Renames that complete before reporting an error are
reconciled using source/target inode state. Temporary and backup files are then
removed, with explicit single-owner descriptor/stream cleanup on every failure
path. Every directory component is identity-checked and
must be real; Darwin's `/var` alias is normalized only after ownership, target,
and identity checks. Non-regular artifact targets are rejected before staging,
and platforms without descriptor-relative filesystem operations fail closed.
SARIF artifact paths are percent-encoded URI references.

The source distribution contains every test/fixture, example, document, and
deterministic demo artifact. Packaging tests extract it, run its full suite, and
build the installable wheel from that extracted release tree.

CSV projections prefix formula-shaped cells with a literal apostrophe before
RFC 4180 quoting, so spreadsheet software cannot execute requirement metadata
or paths as formulae.
