# Research notes

The project responds to the shift from prompt-first generation toward explicit,
versioned intent and verification:

- [GitHub Spec Kit](https://github.com/github/spec-kit) demonstrates
  spec-driven development workflows for coding agents.
- [GitHub on specification-driven development](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)
  describes specifications as the source of truth for implementation.
- [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/) provides the
  interoperable finding format.

SpecSpan is not a clone of those workflows. It focuses narrowly on transparent,
zero-dependency traceability, deterministic graph checks, and caller-supplied
change impact.
