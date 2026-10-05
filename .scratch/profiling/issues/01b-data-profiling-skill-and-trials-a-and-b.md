# 01b data-profiling skill and trials A and B

Type: task. Phase: A. Blocked by: 01a. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [x] GoF consult: one input step registers a DuckDB view per part (a dict of reader functions); modes are plain functions per module over views, returning findings.yaml dicts; no class hierarchy. Large inputs stay inside the input step; 2026-10-05 07:20 ET
- [x] skills/data-profiling/SKILL.md (modes inventory → … → approve, compare): written; doctor finds 0 unresolved; 2026-10-05 07:57 ET
- [x] DuckDB helpers + unit tests on fixtures: scripts/profiling/*.py, 75 tests in tests/unit/test_profiling_*.py on a synthetic set; check digits agree with python-stdnum on 120,000 values; 2026-10-05 07:57 ET
- [x] Genericity lint test (also run against the merged docs/specs/{rdm,agent-context,profiling}; no hits): tests/unit/test_profiling_genericity.py; 2026-10-05 07:57 ET
- [ ] Trial A note: lei2 is 13.25 GB unzipped, 9.5 GB disk free: stream from the zip, sample, full passes for key candidates; never unzip in full
- [x] link.sh, agents/openai.yaml (data-onboarding pattern); 2026-10-05 07:57 ET
- [x] compare mode (drift.yaml, each item names its skill); tested; 2026-10-05 07:57 ET
- [x] Trial B answer key written before the trial: trials/B/ANSWER-KEY.md, committed before any skill code (with trials/A/ANSWER-KEY.md and the SQLite build script); 2026-10-05 07:20 ET
- [ ] Trial A (SEC + GLEIF) matches its answer key
- [x] Trial B matches with no domain-specific change: 52/52 as CSV and as SQLite, identical findings; run 1 was 48/52, four generic fixes listed in trials/B/RESULT.md; 2026-10-05 07:57 ET
- [x] Wiring of data-onboarding (discover, plan-parts; profile reads findings; by-hand profile and the `rules profile` row dropped) and refining-rules (compare before a new delivery changes a live feed). Guard: no overlap; doctor 0 unresolved; `rules profile` left NOT_BUILT in bundle.py and its test (GoF consult on bundle.py: a one-entry constant change, Rule 0, nothing to settle); 2026-10-05 08:06 ET
- [ ] ~~data-platform/SKILL.md one line~~ deferred: still differs on Codex branches codex/bundled-data-guidance-20261004 and codex/raw-submissions-20261004 (guard rule); waits until they merge or close
- [x] Affected tests: tests/unit + tests/architecture with testmon: 725 passed; the 15 failures are pre-existing on main (`jq` not installed locally; CI has it); 2026-10-05 08:06 ET
- [x] doctor: 0 unresolved (bundle.unresolved over every skill); 2026-10-05 07:57 ET
- [ ] Three-axis review, PR, CI, merge on word
