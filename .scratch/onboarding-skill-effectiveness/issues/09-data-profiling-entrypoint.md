# data-profiling: Make the entrypoint executable

Type: task
Status: resolved
Priority: P0
Blocked by: 03, 08
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-profiling](../../../skills/data-profiling/SKILL.md)
Step: 3 of 6
Skill dependencies: data-platform
Applicability: Every new captured dataset; compare mode only when an approved delivery changes.

## Question

What is the shortest sufficient entrypoint for a reader to perform this phase correctly using existing supported commands?

## Scope and evidence

Keep the entrypoint focused on applicability, prerequisites, exact supported commands, expected outputs, next owner and stop conditions. Inputs: captured input inventory and hashes, existing kinds, known identifier formats and profiling settings. Outputs: REPORT.md, findings.yaml, fingerprints and invalid-row evidence kept private where required. Open optional references only when needed; do not move a hard stop out of the required reading path.

Check existing splits before proposing another move; line count alone is not a completion measure.

Start from skills/data-profiling/SKILL.md: Modes, Profile once, How to work, Compare a new delivery. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make the entrypoint executable](./03-data-platform-entrypoint.md); [data-profiling: Reconcile shared rules](./08-data-profiling-consistent-rules.md)

Priority rationale: Reusable evidence is the input to every source model.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Produce an entrypoint that consumes captured input inventory and hashes, existing kinds, known identifier formats and profiling settings and yields REPORT.md, findings.yaml, fingerprints and invalid-row evidence kept private where required; verified against the profiler's argument parser, input fingerprinting and report writer (2026-11-20 19:17 ET).
- [x] Verify referenced paths and supported commands; retain mandatory stops and discoverability of optional detail; checked compare's `--help`, report output paths, and the required-path hard stops (2026-11-20 19:17 ET).
- [x] Walk the documented legal-entity register and relationship-file example through profiling and the approved-findings handoff to Data Onboarding and Data Quality; no input data was loaded (2026-11-20 19:17 ET).
- [x] Published the scoped entrypoint through [Ticket 09: add the data-profiling entrypoint](https://github.com/paulananth/edgartools-platform/pull/1980), merged 2026-11-20 19:38 ET; 147 genericity and guide-path tests pass (2026-11-24).
- [x] Learning → skill: the `Run this phase` section separates required input context and the single-run outputs from conditional compare handling, then names the next owner (2026-11-20 19:17 ET).


## Answer

The repository-owned `skills/data-profiling/SKILL.md` now provides the `Run this phase` entrypoint: required input context, supported run/compare commands, expected private artifacts, hard stops and the next owner. Its implementation is published in [Ticket 09: add the data-profiling entrypoint](https://github.com/paulananth/edgartools-platform/pull/1980). `tests/unit/test_profiling_genericity.py` and `tests/unit/test_guides_name_existing_paths.py` passed 147 tests. The installed `skill://data-profiling` copy remains older and lacks `Run this phase`; this resolution covers the repository-owned skill and does not claim the installed bundle was refreshed. No data was profiled and no provider was queried.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
