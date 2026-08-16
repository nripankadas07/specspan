# specspan

`specspan` turns structured Markdown requirements and explicit `@spec` code
annotations into a deterministic requirement → code → test trace graph.

It detects duplicate requirements, explicit contradictions, broken dependency
links, dependency cycles, unknown annotations, orphan requirements, and active
requirements without test evidence. Impact analysis maps a supplied changed-file
list to directly linked requirements and all transitive dependents. It never
runs Git, a shell, source code, or a model.

Python 3.9+; zero runtime dependencies; fully offline.

## Quick start

```bash
python -m pip install -e .
specspan check examples/demo --spec-dir specs --out artifacts/check
specspan demo --out artifacts/demo
```

Without installation:

```bash
PYTHONPATH=src python -m specspan demo --out artifacts/demo
```

## Requirement format

```markdown
# REQ-TRANSFER-001: Execute an authorized transfer
Status: active
Priority: must
Depends-On: REQ-AUTH-001
Must: Move the amount exactly once
Must-Not: Create a negative balance
Acceptance:
- A valid transfer updates both balances atomically.
```

Trace implementation and tests with inspectable annotations:

```python
def transfer(...):
    """Apply one debit. @spec REQ-TRANSFER-001"""
```

Paths recognized as tests include `tests/`, `test_*.py`, `*.test.ts`, and
similar conventional forms. Draft, retired, and deprecated requirements remain
in the graph but do not trigger orphan or unverified warnings.

## Commands

```text
specspan check [ROOT] --spec-dir specs --out DIR [--fail-on none|warning|error]
specspan impact [ROOT] --spec-dir specs --changed-files FILE [--changed PATH] --out DIR
specspan demo --out DIR
```

`--changed-files` accepts either a JSON array or newline-delimited paths. JSON
must be an array of non-empty relative strings; absolute paths, parent
traversal, objects, numbers, booleans, and nulls are rejected. Values supplied
with `--changed` follow the same path rules. The caller supplies this list;
SpecSpan performs no repository command.

`check` fails on errors by default. Use `--fail-on none` only when generating a
non-gating exploratory report.

## Output

```text
specspan.json         canonical specspan/v1 artifact
traceability.csv      review-friendly matrix
findings.sarif        SARIF 2.1.0 code-scanning output
impact.json           present for impact runs
report.md             portable report
report.html           self-contained visual report
checksums.sha256      deterministic digests
```

Traversal reads only regular files physically contained by the analysis root.
Symbolic links, FIFOs, sockets, devices, and symlinked roots/spec directories
are skipped or rejected. Dynamic Markdown values are encoded as literals, and
HTML values are escaped.

## What a link means

An annotation proves that a maintainer declared a relationship. It does not
prove that code implements the requirement, that the test is meaningful, or
that a specification is complete. SpecSpan makes missing and contradictory
evidence visible; humans still judge correctness.

See [architecture](docs/architecture.md), [format](docs/format.md), and
[limitations](docs/limitations.md).

## Develop

```bash
make test
make demo
```

## License

MIT

See the [roadmap](ROADMAP.md), [research provenance](docs/research.md), and [AI-assistance disclosure](AI_ASSISTED.md).
