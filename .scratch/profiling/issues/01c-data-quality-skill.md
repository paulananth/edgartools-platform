# 01c data-quality skill

Type: task. Phase: A. Blocked by: 01b. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [x] GoF consult: leave run.py; detectors as plain functions in a new profiling/quality.py; defect-to-engine map as a dict in the data-quality helper, checked against the engine's CHECKS and FIXES 2026-10-05 20:06 ET
- [x] skills/data-quality/ extracted from onboarding quality + refining change-quality (skills/data-quality: SKILL.md, quality_plan.py draft and measure; tests/unit/test_data_quality_plan.py, 7 tests) 2026-10-05 20:23 ET
- [x] Invalid-row marking with evidence-backed fixes (invalid_rows.jsonl: orphans folded to the one matching key, off-dependency rows to the usual parent, otherwise needs steward; tests in test_profiling_quality.py and test_profiling_time_and_hierarchy.py) 2026-10-05 20:23 ET
- [x] Callers rewired (guard first) (guard named the stale Codex worktree codex/bundled-data-guidance-20261004, PR #817 merged; operator ruled "Proceed: it's stale" for these two files; commit 45d58c73) 2026-10-05 20:23 ET
- [x] Both trials' defects become loadable checks (Trial B: 28 of 29 defects became checks or fixes; Trial A: 82 of 128; the rest new code with what its check would test; trials/B/quality and trials/A/quality) 2026-10-05 22:23 ET
- [x] Profiling's quality items carry rows and masked examples (findings §3 schema), moved here from 01b (added 2026-10-05 20:02 ET) (profiling/quality.py detectors; Trial B: every count equals the engine's) 2026-10-05 20:23 ET
- [x] Each invalid hierarchy row marked (count and masked examples in findings, full key list in a sidecar), with a check and an evidence-backed fix or "needs steward", moved here from 01b (added 2026-10-05 20:02 ET) (Trial B: 4 rows, each with a fix and its evidence, e.g. 38 of 41 rows) 2026-10-05 20:23 ET
- [x] Verify rr invalid-row counts (3,194 for one relationship type with holds 1.0: cycles or an artefact) before building on them (added 2026-10-05 20:02 ET) (full rr file: 3,192 funds name themselves as their own manager, plus one 2-cycle of 2 nodes = 3,194; real, now reported as 'names itself as its parent' apart from cycles) 2026-10-05 20:23 ET
- [x] New code values in compare (moved here from 01b; distribution drift stays with refining-rules) (added 2026-10-05 20:02 ET) (drift codes_new from the approved code-list guards; test in test_profiling_quality.py) 2026-10-05 20:23 ET
- [x] Each defect maps to an existing check or fix, or becomes "new code: ticket"; the engine's quality code is not edited (added 2026-10-05 20:02 ET) (CATALOG in quality_plan.py, each target asserted in the engine's CHECKS; others listed as new code) 2026-10-05 20:23 ET
- [x] Trial checks proven: engine check_quality loads them, quality.apply counts equal profiling's counts, one planted record per check (added 2026-10-05 20:02 ET) (both trials: each quality.yaml loads through the rules loader and registration's checks, every count equals profiling's, every planted record fires; Trial A marks 7,170 rows, 3,903 with an evidence-backed fix, 3,267 for a steward, 0 without either; Trial A 54 min) 2026-10-05 22:23 ET
- [x] Genericity lint covers skills/data-quality; doctor 0 unresolved; rules skill command test passes (added 2026-10-05 20:02 ET) (lint 28 passed incl. skills/data-quality; doctor unresolved []; test_rules_skill_commands passed) 2026-10-05 20:23 ET
- [x] Three-axis review (Standards, Spec, GoF): masking gaps in marked rows, double-counted rows, per-code queries, withhold double-count, a crash on tests with no planted value, and smaller items fixed with tests; loading through files.source answered by loads() (rules loader plus registration's checks) 2026-10-05 22:23 ET
- [ ] ~~Tell coincidental code dependencies from real hierarchies~~ deferred to a profiling follow-up: Trial A finds dependency "hierarchies" such as a flag over the form type; their fixes stay steward proposals (trials/A/quality/RESULT-quality.md) (added 2026-10-05 22:23 ET)
- [ ] ~~A hierarchy check in the engine~~ deferred: new engine code, outside this program's ownership; listed as new code with what it would test (added 2026-10-05 22:23 ET)
- [ ] Review, PR, CI, merge on word
