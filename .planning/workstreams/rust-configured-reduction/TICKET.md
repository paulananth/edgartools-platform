# Configured reduction in the Rust core

Scope: one bounded implementation slice of the agreed configured Rust core
with Python callers. Own `crates/source-contract/src/reduction.rs`, its native
binding/module registration, the Python source-engine facade, the reduction
worker, reduction tests and this workstream. Preserve Claude's Company/control
and profiling work, the existing materialized combination path and MDM merging.

- [x] Confirm refreshed main and isolated worktree; inspect Claude worktrees/PRs and overlap. Verified dedicated branch/worktree at 45525cd8, clean Claude source surfaces and open PR #910's profiling-only files; guard passed before edits and on refreshed origin/main; 2026-10-11 15:08 ET.
- [x] Review reduction and facade code/history with gof-refactor-reviewer; record the design boundary. Verified original reduction, PyO3/facade and history; retain adapter and existing worker, no new hierarchy (review below); 2026-10-11 15:08 ET.
- [x] Implement bounded generic Rust reduction with Python caller; preserve authentication, exact output semantics, state budgets and failure behavior. Verified native accumulation/finalization, bounded conversion batches, poison-on-failure, unchanged Python EOF/publication boundary and native execution identity coverage; 2026-10-11 15:08 ET.
- [x] Qualify differential parity, bound violations, late-corruption refusal and retry/verification behavior using existing and native tests. Verified 120 targeted Python tests, full pre-existing cargo suite plus 3 native reduction tests; seeded differential expected tables, exact Unicode/control byte budgets, late faults and existing idempotency/verification pass; 2026-10-11 15:08 ET.
- [x] Measure a bounded full-worker comparison against the prior Python implementation; record results without claiming production qualification. Verified five trials at 20k/100k rows per table with 1/2/4 workers, exact output hash parity; small workload repeated after test activity stopped. Recorded 3.17–4.74x median speedup and 10.3–33.4% higher peak RSS in RESULTS.md and raw benchmark JSON; 2026-10-11 15:13 ET.
- [x] Update only affected skill guidance after local qualification and ownership checks. Verified COMBINING documents native state, unchanged budgets, Python authentication and pinned-runtime recovery; platform command/link checks pass; no parsing/onboarding/activation instructions changed; 2026-10-11 15:08 ET.
- [ ] Recheck ownership/overlap, tests and checklist; commit on the dedicated Codex branch.

Baseline: fetched origin/main `45525cd8bc1df550bfba10022bd5eead1f41359d`.
Branch: `codex/rust-configured-reduction`; dedicated worktree. Claude's live
worktree changes and open PR #910 do not touch this slice at initial inspection.
The inherited `.planning/active-workstream` (`fix-pipelines`) remains unchanged.

Design review: retain the existing SourceEngine facade and source.combine
worker. History `3368da36` added authenticated incremental reduction; keep
Python traversal/authentication and publish-after-EOF, move only generic state
accumulation/finalization into Rust. No new GoF hierarchy: native adapter plus
the current caller is sufficient. Costs to measure: Python/native text copying
and batch calls; avoid retaining input rows in native reduction state.
