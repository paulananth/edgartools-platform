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
- [x] A step is `locked` when the store has three or more sessions waiting on locks and at least one of the step's own sessions waits on a lock (`lock_waiting` of its session summary, counted per session, not the commonest wait); otherwise its CPU, log and sessions decide (`progressing` or `stalled`). The board's legend says so (2026-11-25 14:58 ET)
- [x] Test first: `test_a_step_is_progressing_waiting_on_locks_or_possibly_stalled_by_its_own_evidence`, `test_a_step_is_judged_by_the_store_it_writes_and_one_waiting_session_is_not_a_lock_problem`, `test_a_verdict_has_one_kind_the_words_follow` and `test_a_step_with_a_working_session_is_progressing_at_no_cpu_and_never_unclear` fail on the code before and pass after, by `AssertionError: assert 'locked' == 'progressing'` on `verdict_kind(lock_waiters=3)` for a busy step with no session of its own and for a step whose own sessions work; `tests/unit/test_load_jobs.py` and `test_load_monitoring.py`: 204 passed (2026-11-25 14:58 ET)
- [x] Found by the Spec review: the commonest wait of a step's sessions is not whether one waits on a lock (one lock-waiting session among client-waiting ones read `progressing`); `lock_waiting` counts them, and `test_a_step_with_one_session_waiting_on_a_lock_among_sessions_waiting_on_the_client_is_locked` pins it (205 passed) (2026-11-25 15:00 ET)
- [ ] The board read on a running load with lock waiters (none now: 0 waiters, no step running at the last reading): no step locked unless its own sessions wait
- [x] Learning → skill: `skills/data-operations/scripts/load_jobs.py` `verdict_kind` docstring and the `locked` line of `skills/load-monitoring/scripts/design.py` say `locked` is a step's own evidence and the store's waiter count is the pressure signal only (2026-11-25 14:58 ET)
