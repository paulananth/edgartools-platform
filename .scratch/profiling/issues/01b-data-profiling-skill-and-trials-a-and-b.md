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
- [x] Wiring of data-onboarding (discover, plan-parts; profile reads findings; by-hand profile and the `rules profile` row dropped) and refining-rules (compare before a new delivery changes a live feed). Guard: no overlap; doctor 0 unresolved; `rules profile` removed from NOT_BUILT in bundle.py and its test, since no skill names it now (GoF consult on bundle.py: a one-entry constant change, Rule 0, nothing to settle); 2026-10-05 08:06 ET
- [ ] ~~data-platform/SKILL.md one line~~ deferred: still differs on Codex branches codex/bundled-data-guidance-20261004 and codex/raw-submissions-20261004 (guard rule); waits until they merge or close
- [x] Affected tests: tests/unit + tests/architecture with testmon: 725 passed; the 15 failures are pre-existing on main (`jq` not installed locally; CI has it); 2026-10-05 08:06 ET
- [x] doctor: 0 unresolved (bundle.unresolved over every skill); 2026-10-05 07:57 ET
- [x] Three-axis review (Standards, Spec, GoF): GoF no findings; Standards 2 hard (working copy kept raw values; hierarchy samples unmasked) and Spec 5 blocking (stale compare text; no input rows/sha256; placeholder key evidence; ticket text; large CSV not sampled, sampled composite keys unconfirmed, surrogate not durable, contact details unmasked outside people parts) all fixed with tests; Trial B re-run 52/52 both forms; 2026-10-05 08:32 ET
- [ ] ~~level_tables hierarchy evidence~~ deferred to row 01b follow-up: no trial data set has separate level tables (research note section 15); add with a data set that has them
- [ ] ~~DQ check and proposed fix for each invalid hierarchy row~~ deferred to 01c (data-quality skill turns `invalid_rows` into checks and fixes)
- [ ] ~~Distribution drift (PSI, KS, chi-square) and new code values in compare~~ deferred to 01c/refining-rules: compare reports schema, key, link, count and volume drift now
- [ ] ~~Snowflake profiled in place with SQL~~ deferred to phase B (row 6 adds the Snowflake sink); Postgres, SQLite and DuckDB work now
- [ ] ~~Quality items with rows and masked examples; silver links.kind and column definitions~~ deferred to 01c and row 6 (kinds are known only after onboarding)
- [ ] ~~Snapshot-or-changes, versions per key, refresh rate, key persistence~~ need two deliveries: reported unknown now; compare measures them in a follow-up
- [x] Name as the only unique key (operator, 2026-10-05: "names can become a unique key ... one option is to create a hash of the big long name"): research note .scratch/profiling/research/02-name-as-key.md; operator ruling "Same record: durable key"; names.py (one normalization, NFKC + case fold, Unicode version in the rule), a name is never a found key, a durable id in a key map looked up by sha256 of the normalized name with renames as aliases; findings.md notes the fields; tests/unit/test_profiling_names.py; 2026-10-05 17:21 ET
- [ ] PR, CI, merge on the operator's word
