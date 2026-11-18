# Report a running load from its evidence

Status: resolved
Type: task

Operator, 2026-11-18: "Provide more intelligence on 'the lanes are unchanged, still running...' instead of just saying
it's running, check the log, make this part of the data operations skill".

## Parts

- [x] `load_chain.py --status`: per running step its time against its bound, bundles done and the minutes left at the
  rate so far, rows written a minute in its store and who shares it, its processes' CPU (sampled over the window, since
  `ps` shows a lifetime average) and memory, the age of its log, and a verdict (2026-11-18 08:38 ET; live run on the hosted load; 51
  tests, each failing first: `bundle_progress`, `minutes_left`, `verdict`, `writes_per_minute`, `cpu_seconds`,
  `cpu_percent`, `store_of`, `outlook`, `session_summary` did not exist)
- [x] Flaws found by running it on the live load and fixed: a lifetime CPU average showed 0% for working processes; one
  waiting session was flagged as a lock problem on every step; every step was credited with the combined write rate; a
  step that needs 253 more minutes against 156 left in its attempts was not warned
- [x] The database sessions by store, working or waiting on the client, as the reader login and never a query: on the live
  load the store waited on the client (31 sessions waiting, none working), which says the Mac, not the database, is the
  limit (2026-11-18 08:38 ET)
- [x] The data-operations skill, "Report a running load from its evidence", and the daily-run runbook say a load is never
  reported as "running" (2026-11-18 08:38 ET)
- [x] Learning → skill: data-operations SKILL.md, "Report a running load from its evidence"; daily-run runbook, "Progress,
  failure and recovery" (2026-11-18 08:38 ET)
