# Retain and report load times

Status: open

- [x] Inspect loader timing calculation, catalog publication and monitoring configuration; confirmed endpoint limits, status-only publication and refresh intervals by code inspection (2026-11-26 07:47 ET).
- [x] Update data-operations timing procedure and invocation pointer with evidence discovery, per-step retention, timing semantics and catalog/monitor roles; checked against the implementation (2026-11-26 07:47 ET).
- [x] Publish documentation in PR #2187 (2026-11-26 08:21 ET).
- [x] Reproduce CI's naming failure: `test_the_load_jobs_are_named_load_jobs_everywhere_a_reader_looks` reported TIMING-REPORTS.md because its prose said `chain state`; use `load state`, preserving the literal retained log filename (2026-11-26 08:21 ET).
- [ ] Wait for final-head CI and merge PR #2187.
- [x] Learning → skill: data-operations/TIMING-REPORTS.md records the log lookup procedure, elapsed-time limits and the catalog timing publication gap (2026-11-26 07:47 ET).
