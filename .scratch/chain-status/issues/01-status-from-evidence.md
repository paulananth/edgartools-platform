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
- [x] Flaws found by running it on the live load, each fixed and re-run live (2026-11-18 08:40 ET):
  - a lifetime CPU average showed 0% for working processes: CPU time is sampled over the window (`test_cpu_percent_comes_from_the_cpu_time_used_in_the_window_not_a_lifetime_average`; a first expectation was also wrong and was corrected by the test: `assert 62.75 == (62.75 + 0.5)`);
  - one waiting session was flagged as a lock problem on every step: locks count at three sessions, the scheduler's own threshold (`test_a_step_is_judged_by_the_store_it_writes_and_one_waiting_session_is_not_a_lock_problem`; the older verdict test failed on `'progressing'.startswith('waiting on database locks')` with two waiters until it said three);
  - every step was credited with the combined write rate: each step has its store's rate and names the steps that share it (`store_of` in the same test);
  - a step that needs 253 more minutes against 156 left in its attempts was not warned (`test_a_step_that_cannot_finish_in_the_attempts_it_has_left_says_so`: `outlook` did not exist, `AttributeError`)
- [x] The database sessions by store, working or waiting on the client, as the reader login and never a query: on the live
  load the store waited on the client (31 sessions waiting, none working), which says the Mac, not the database, is the
  limit (2026-11-18 08:38 ET)
- [x] The data-operations skill, "Report a running load from its evidence", and the daily-run runbook say a load is never
  reported as "running" (2026-11-18 08:38 ET)
- [x] Learning → skill: data-operations SKILL.md, "Report a running load from its evidence"; daily-run runbook, "Progress,
  failure and recovery" (2026-11-18 08:38 ET)
