# Implementation notes: tested custom parsing findings

Owner: Claude, from 2026-10-03. The operator's words, after Codex's #804 merged:
"codex finished and pr created and merges now claude take over and finishes".
The follow-up (SEC Company and GLEIF on the engine, and the bundled skill) is
`.scratch/mastering-to-done/issues/21-self-sustaining-data-skill.md`. Codex: do
not start this work; ask the operator first.

Earlier: Owner: Codex. The operator withdrew the Claude assignment on 2026-10-02.

## Start here

Review [PR #784](https://github.com/paulananth/edgartools-platform/pull/784)
and its research/experiments on `codex/custom-parsing-research-20261002`.
Codex owns follow-up work in a dedicated Codex branch/worktree. Fetch current
main and reconcile its source with the research baseline before implementation.
Start with the [loader-independent Bookkeeping design](bookkeeping-loader-independent-design-2026-10-02.md).

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

First remove Bookkeeping's workload dependency through the proposed generic
task protocol. Then consider the SEC Company scalar projection as separate
parsing work:

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
separate evidence requirements for any production refactor. These notes
records a recommendation; it does not claim that refactor is implemented.
