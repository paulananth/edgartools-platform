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
- [x] Spec review of the status report, five findings fixed (2026-11-18 08:45 ET; 56 tests): bundles an earlier attempt already loaded count as done (`test_bundles_already_loaded_by_an_earlier_attempt_count_as_done`: `bundle_progress` returned 1, not 3, on a resumed log, so a resumed step was told to raise its workers); a store is client-bound when more than half its sessions wait on the client, as the skill says (`test_a_store_is_client_bound_when_more_than_half_its_sessions_wait_on_the_client`: 11 waiting against 10 working printed no note); only the platform's own processes are matched and only those present in both readings count toward CPU (`window_cpu`, `is_load_process`); a step sharing a store whose own processes are idle is "unclear", not "progressing" (`test_a_step_sharing_a_store_whose_own_processes_are_idle_is_unclear_not_progressing`); `--status` runs before the loader login, the log folder and the wake lock, so it is read-only and uses the reader login alone
- [x] The database sessions by store, working or waiting on the client, as the reader login and never a query: on the live
  load the store waited on the client (31 sessions waiting, none working), which says the Mac, not the database, is the
  limit (2026-11-18 08:38 ET)
- [x] The data-operations skill, "Report a running load from its evidence", and the daily-run runbook say a load is never
  reported as "running" (2026-11-18 08:38 ET)
- [x] Learning → skill: data-operations SKILL.md, "Report a running load from its evidence"; daily-run runbook, "Progress,
  failure and recovery" (2026-11-18 08:38 ET)
