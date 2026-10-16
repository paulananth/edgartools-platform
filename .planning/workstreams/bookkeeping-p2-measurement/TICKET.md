# Bookkeeping P2 measurement harness: autoplan

Owner: Codex. Branch: `codex/bookkeeping-p2-measurement-autoplan`.
Scope: review a measurement-only implementation plan. Runtime implementation,
Bookkeeping optimizations, migration, activation and deployment are not authorized
by this planning ticket. This narrows PR #977's already approved P2 plan.

## Checklist

- [x] Inspect live main, Claude ownership, existing P2 plan, code and reusable test facilities — verified Git/worktrees, PR #988, current engine/CLI and PG16 support; 2026-10-15 21:10 ET.
- [x] Write the scoped intake and capture a verified external restore point — original contents compared exactly with external restore; 2026-10-15 21:10 ET.
- [x] Load review skills and complete CLI reviewer preflight — CEO/DX/Eng methodologies loaded, Claude 2.1.301 and Codex 0.162.1 available; Codex auth/model probes passed; 2026-10-15 21:10 ET.
- [x] Complete CEO review, independent voices, alternatives and decision registries — Codex six concerns resolved, actual Claude credit failure recorded, spec recheck PASS, case contract and registries saved; 2026-10-15 21:17 ET.
- [x] Record the no-UI assessment and complete DX review with independent voices — eight passes and required outputs saved; five Codex findings resolved in contract, actual Claude credit failure recorded; 2026-10-15 21:24 ET.
- [x] Complete engineering review last, independent voices and test-path mapping — actual Codex focused recheck PASS; six engineering findings resolved; 27 future proof groups, no behavior tests run; 2026-10-16 08:51 ET.
- [x] Write test-plan and implementation-task artifacts; validate links, scope and overlap — five planning artifacts, 25 unique decisions, 27 proof groups, five aggregated tasks, all relative links and whitespace valid; live overlap guard passed; 2026-10-16 08:51 ET.
- [x] Refresh live main/Claude PRs and rebase the saved planning branch — scoped Git diff confirms reviewed runtime/support/dependencies unchanged; rebased onto 3064a4e4 without conflict; 2026-10-16 08:52 ET.
- [x] Present the final approval gate and record the operator's decision — operator replied “approved”; accepted four new code/test files, dedicated lifecycle helper and baseline-only metadata with speedup calculations deferred; 2026-10-16 08:54 ET.
- [x] Learning → skill: none — this planning review applies existing proof/ownership rules; no demonstrated skill defect or new verified runtime behavior warrants a skill edit; 2026-10-16 08:51 ET.

Completion: DONE_WITH_CONCERNS. Planning approved; CI repair verified on a49e4f4f, all six checks passed in run 38916114512. Claude plan review limitation remains below.
Review limitation: Claude voices were unavailable because the configured model
required usage credits; independent Codex reviews and final engineering PASS remain
the recorded evidence. Harness implementation and harness behavior tests have not started.
No durable learnings this session.

## PR #1011 CI repair

The operator requested CI failures fixed after publication. Keep the approved
measurement plan unchanged. Investigate the committed Mapping Document mismatch;
regeneration may update a derived workbook, with no rule/runtime changes.

- [x] Reproduce the CI failure with the affected test and identify the stale generated content — exact two-cell mismatch reproduced locally; workbook from #1003 predates generator wording in #1009; 2026-10-16 10:28 ET.
- [x] Confirm no active runtime overlaps the repair, then regenerate only the affected Mapping Document — candidate-path inspection and live overlap guard passed; `rules mapdoc write --only fund_structure` updated only F2/F3 of Matching rules; 2026-10-16 10:28 ET.
- [x] Run bounded affected testmon tests and compare generated cells/notes against the prior workbook — fresh dedicated testmon data, 24 tests passed in 17.09s; all other cells and Notes equal; 2026-10-16 10:28 ET.
- [x] Review Standards, Spec and GoF — existing generator and regression test retained, no rule/runtime change or pattern refactor; named workbook/ticket diff checked; 2026-10-16 10:28 ET.
- [x] Commit by named paths, push and verify all PR checks — repair a49e4f4f pushed; all six checks SUCCESS in [CI run 38916114512](https://github.com/paulananth/edgartools-platform/actions/runs/38916114512), including unit/architecture, MDM, real PostgreSQL integration, Rust engine, shell lint and aggregate gate; 2026-10-16 10:34 ET.
- [x] Learning → skill: none — existing Mapping Document regeneration and equality-test guidance applies; no new skill defect or runtime behavior change; 2026-10-16 10:28 ET.

### Standards

The operator authorized the CI repair. Only the generated Fund Mapping Document
and this checklist changed; overlap guard passed. No source rules, tests or
runtime code were weakened or modified.

### Spec

The workbook now agrees with the current generator in both matching-rule cells.
The original whole-catalog equality regression fails before regeneration and
passes afterward; all 24 tests in its module passed. The Bookkeeping plan and
its four future implementation files remain unchanged/unimplemented.

### GoF

The available gof-refactor-reviewer method was applied to mapdoc generator code
and the #1003/#1009 history before and after the repair. This is stale generated
content at an existing tested seam; leave the implementation unchanged.
