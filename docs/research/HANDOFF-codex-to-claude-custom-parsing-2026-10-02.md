# Claude handoff: tested custom parsing findings

## Start here

Review this branch's research and experiments:
`codex/custom-parsing-research-20261002`. The PR description links this note.
Use your own `claude/<topic>` branch and dedicated worktree for implementation.
Fetch current main and reconcile its source with the research baseline before
selecting work. The Codex branch remains owned by Codex.

Read the [tested results](configuration-replacement-results-2026-10-02.md)
first; use the [inventory](custom-parsing-inventory-2026-10-02.md) for caller
evidence. Both record baseline `542a9fa0` and their limits.

The PR branch incorporates main at `4e51a84f` (#781/#782). Three uncalled
helpers from the baseline inventory were already removed by #781; those
historical entries are marked accordingly. They require no new deletion task.

## Findings to carry forward

The 41 Python comparisons and 13 Rust probes passed. Several passing tests
prove incompatibilities; they do not establish 54 equivalent replacements.
Fixtures are synthetic and bounded. Production code and approved rules were
unchanged; experiments are not registered runtime contracts.

The demonstrated opportunity is the ten scalar field lookups in
`stage_company_loader`: existing path traversal plus configured paths matched
four fixtures exactly when the caller's CIK/run/raw-object/load-mode context
was preserved. A generic Silver consumer for that mapping still needs to be
implemented. MDM `mapped_field` is not a direct substitute: it converts a
whitespace-only value to null while the Silver loader preserves it.

GLEIF scalar projection also matched bounded fixtures, including full assertion
IDs and provenance. Retain source validation, scope, deletion, period selection
and UTC normalization: direct mapping demonstrably loses those behaviors.

Keep SEC individual classification, address conversion, parallel filing-array
expansion and Company aggregation until replacements pass the relevant positive
and failure cases. The tested overlap classifier admitted an unknown form as
Person. Simple addresses lost country interpretation. Existing mapping operators
did not supply array expansion or grouping.

Keep the native GLEIF reader. The Rust prototype lost valid CDATA text and
accepted malformed, namespace/header/count/DTD cases that Python rejected.
Its ordinary scalar projection match is not complete reader equivalence.

## Suggested implementation ticket

If the operator selects implementation, start with the SEC Company scalar
projection only:

1. Define versioned, validated paths for the ten fields and wire a generic
   Silver projection consumer using the existing traversal behavior.
2. Preserve blank, missing and scalar values plus all caller context. Keep
   classification, pagination and the other loader behavior independently
   covered.
3. Extend comparisons to supported input shapes and run affected
   Silver/Company and architecture tests before removing inline field lookups.
4. Follow Rules registration, version and approval requirements for runtime
   configuration. The experiment YAML is evidence, not an approved contract.

The GoF review found existing function registries sufficient. No new class
hierarchy or design pattern is recommended.

## Verification and review boundary

The result report contains commands to reproduce both research suites and the
exact environment used. Review the counterexamples alongside the matches.
Full CI, PostgreSQL qualification, real source sampling and deployment remain
separate evidence requirements for any production refactor. This handoff
records a recommendation; it does not claim that refactor is implemented.
