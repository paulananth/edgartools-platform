# 01b data-profiling skill and trials A and B

Type: task. Phase: A. Blocked by: 01a. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [x] GoF consult: one input step registers a DuckDB view per part (a dict of reader functions); modes are plain functions per module over views, returning findings.yaml dicts; no class hierarchy. Large inputs stay inside the input step; 2026-10-05 07:20 ET
- [ ] skills/data-profiling/SKILL.md (modes inventory → … → approve, compare)
- [ ] DuckDB helpers + unit tests on fixtures
- [ ] Genericity lint test (also run against the merged docs/specs/{rdm,agent-context,profiling}; fix hits)
- [ ] Trial A note: lei2 is 13.25 GB unzipped, 9.5 GB disk free: stream from the zip, sample, full passes for key candidates; never unzip in full
- [ ] link.sh, agents/openai.yaml
- [x] Trial B answer key written before the trial: trials/B/ANSWER-KEY.md, committed before any skill code (with trials/A/ANSWER-KEY.md and the SQLite build script); 2026-10-05 07:20 ET
- [ ] Trial A (SEC + GLEIF) matches its answer key
- [ ] Trial B matches with no domain-specific change
- [ ] Wiring of data-onboarding / refining-rules / data-platform SKILL.md (guard first; waits for a clear moment)
- [ ] doctor: 0 unresolved
- [ ] Three-axis review, PR, CI, merge on word
