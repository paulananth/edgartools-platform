# 02: A step is `locked` only when its own sessions wait on locks

Status: open
Type: bug
Blocked by: none
Blocks: none

Found 2026-11-25 on the hosted reset's reload: the load board showed `person` and `openfigi-answers` locked, and earlier
2 stalled and 11 locked. Neither locked step had a database session of its own (the Why column said so), and `person`
had finished; the store had 7 sessions waiting on locks. `verdict_kind` judged `locked` from the store-wide count of
waiting sessions alone (`lock_waiters >= 3`), before any evidence of the step, so every running step read locked while
three sessions anywhere waited. Its docstring said the opposite: a step's state by its own evidence, never a neighbour's.

## Checklist

- [x] Operator, 2026-11-25 14:58 ET: "yes fix it once #2141 merges"; #2141 merged first (the same file)
- [x] A step is `locked` when the store has three or more sessions waiting on locks and the step's own sessions' commonest wait is a lock (`evidence["wait"]` starts with `Lock:`); otherwise its CPU, log and sessions decide (`progressing` or `stalled`). The board's legend says so (2026-11-25 14:58 ET)
- [x] Test first: `test_a_step_is_progressing_waiting_on_locks_or_possibly_stalled_by_its_own_evidence`, `test_a_step_is_judged_by_the_store_it_writes_and_one_waiting_session_is_not_a_lock_problem`, `test_a_verdict_has_one_kind_the_words_follow` and `test_a_step_with_a_working_session_is_progressing_at_no_cpu_and_never_unclear` fail on the code before (a step with no session of its own, or working sessions, read `locked` at three store waiters) and pass after; `tests/unit/test_load_jobs.py` and `test_load_monitoring.py`: 204 passed (2026-11-25 14:58 ET)
- [ ] The board read on a running load with lock waiters (none now: 0 waiters, no step running at the last reading): no step locked unless its own sessions wait
- [x] Learning → skill: `locked` is a step's own evidence; the store's waiter count is the pressure signal only (2026-11-25 14:58 ET)
