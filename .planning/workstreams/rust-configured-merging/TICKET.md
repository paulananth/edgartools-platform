# Configured merging and field survivorship

Status: claimed by Codex. Branch: `codex/rust-configured-merging`.
Baseline: `e4be301962e0c2c1b6ab6efc0eb500747b7c718e` (origin/main).

## Contract

The generic configured core lives in Rust, called through Python. Custom code
stays Python. This bounded slice moves accepted identity-decision replay and
configured field eligibility and priority/winner ordering
into native kernels. Existing `replay`, `current_claims`, `select_fields` and
`MergeStage` remain the caller seams. Source-history folding in `current_claims`
remains Python in this slice; automatic matching, profile qualification, policy
authority/digests, timestamp parsing, canonical value comparisons, output materialization and orchestration
remain Python. No new configuration vocabulary or custom Rust callbacks.

Preserve identity kinds, bindings, merge dependencies, exclusions, corrections,
quarantine, source retirement, overrides and reversal semantics. Preserve source
order, recency, deterministic ties, authorized clears, unknown-time/age rules,
kind defaults, profile field authority, disagreement and review order. Preserve
Python numeric/Unicode canonical spelling, assertion and policy hashes, limits,
transaction fencing, atomic commits, lost-ack replay and recovery. Native kernels
return references to caller payloads, never re-encode arbitrary field values.
Database constraints/locks/freshness/leases/history remain authoritative.
Native loops release the GIL; the execution digest must pin all changed runtime
files and the installed native binary. No deployment or policy activation.

## Verification and design

User agreed both seams: public computation APIs for parity, MergeStage for real
PostgreSQL 16 persistence and recovery. Fixed literal expectations plus the
unchanged baseline implementation as an independent migration parity oracle.
GoF review: existing facade/adapter seams fit this change; survivorship history
(#698/#706/#715) shows policy churn, not a need for a new class hierarchy. Retain
Python policy assembly and add native computation behind the existing facade.
Qualification is offline; performance claims require measured full caller paths.

## Parts

- [x] Inspect live worktrees, ownership, instructions and existing interfaces; guard proposed edits. Verified fresh e4be3019 worktree, clean Claude merge-size tree, no open PR overlap, guard passes; 2026-10-11 16:12 ET.
- [x] Implement configured field selection through Rust with public API regression/parity tests. Verified installed native ranking and public select_fields tests in 60 passing focused tests; 2026-10-11 16:12 ET.
- [x] Implement accepted identity replay through Rust with public API regression/parity tests. Verified 60 focused tests, including revocation/quarantine and year-9999 subsecond reversal; 2026-10-11 16:12 ET.
- [x] Pin changed computation files in the worker runtime digest. Verified all three new dependencies alter runtime identity, 47 configured mapping tests pass; 2026-10-11 16:20 ET.
- [x] Verify public MergeStage persistence, correction, fencing and recovery on real PostgreSQL 16. Verified 63 restricted-role tests in test_clean_mdm_postgres and test_clean_stage_record (133.55s); 2026-10-11 16:12 ET.
- [ ] Measure bounded offline computation and full MergeStage paths, including semantics and memory.
- [x] Update only skill instructions affected by implemented capabilities; verify examples. Guard passed, responsibility note only; doctor resolves all 131 commands with engine loaded, no activation changes; 2026-10-11 16:20 ET.
- [ ] Run regular Rust type checks, focused tests, then the complete maintained test suite once.
- [x] Review against baseline with Standards, Spec and independent GoF agents, and address findings. Independent reviews and rechecks confirm future-operand finding resolved in bf2278e3, no remaining findings; see REVIEW.md; 2026-10-11 16:25 ET.
- [x] Fix review finding: filter future decisions before native operand marshalling and preserve active override references. Verified red/green public regression and 14 identity passes; reversed merges also ignore unused survivor/dependency metadata; mypy clean; 2026-10-11 16:24 ET.
- [ ] Guard and commit the verified implementation on this dedicated branch.
- [ ] Rebase onto freshly fetched main, preserve qualification notes, and verify upstream profiling/skill changes.

Qualification note: 1,000 field/profile and 1,000 identity baseline comparisons pass.
200/600-record real MergeStage business hashes match; small workloads can be slower.
Timing while broad tests run is noisy; final measurements will run without that load.
Full maintained suite completed in 35m06s: 2,828 passes, one existing xfail,
one future-expiry failure from the earlier in-process adapter snapshot. Fresh
MDM rerun at the committed correction passes all 648 tests, including that case. Installed-bundle tests use committed HEAD,
so a guarded implementation checkpoint precedes that portion and final review.
