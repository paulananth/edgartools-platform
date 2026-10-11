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
- [x] Recheck ownership/overlap, tests and checklist; commit on the dedicated Codex branch. Verified fresh origin/main and open-PR checks, guard (13 files, no overlap), registered CLI profile/native runtime digest, diff checks and all listed local evidence; implementation committed as 965ea0a2 on codex/rust-configured-reduction; 2026-10-11 15:14 ET.

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

This first implementation slice is complete locally. See RESULTS.md for exact
scope and measurements. No deployment/activation or full-pipeline production
qualification is claimed. Materialized combination and configured merge kernels
are subsequent slices, not unfinished parts of this bounded reduction ticket.

## PR and landing follow-up

- [x] Refresh main, review the final diff and rerun affected tests on the updated branch. Verified main 70418146 merged without source conflict, specialist and Claude review, rebuilt native binding and 120 affected Python passes; full Rust suite and 4 reduction tests pass; 915 broader passes plus all 15 jq-prerequisite reruns pass; 2026-10-11 15:24 ET.
- [x] Clarify native per-group row-limit wording found during review and test terminal failure at that boundary. Verified 4 native reduction tests and rebuilt binding's 120 Python tests; benchmark binary and rebuilt runtime identities distinguished in RESULTS.md; 2026-10-11 15:24 ET.
- [x] Publish a PR with output parity, performance and memory evidence; check repository overlap before pushing. Verified PR #911 includes the full slice, tests, benchmark speedup/RSS tradeoff and rollout limits; guard passed before commit and push; documentation-release audit found no further edits; 2026-10-11 15:26 ET.
- [ ] Verify all CI jobs, review results and the final PR contents before reporting merge readiness.
- [ ] Merge after the final readiness gate and verify GitHub's merge commit; preserve the shared dirty checkout.
