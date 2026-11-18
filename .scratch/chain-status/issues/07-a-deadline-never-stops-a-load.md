# A deadline never stops a load

Status: resolved
Type: task

Operator, 2026-11-18, after the scheduler stopped four running steps at its two-hour deadline: "Deadline must not stop loading".

## Findings

- `--deadline` and `--hours` held the run to a schedule, and at the deadline the scheduler stopped every step it had started and
  returned. GLEIF, N-PORT security's silver, company facts and IPO were stopped with up to 90 minutes of work in their attempts.
- The operator had already chosen, for the first load, to keep loading and report the miss. A deadline is a measure of the schedule
  (it relaxes the machine limits for a run that is behind), not a reason to throw work away.

## Parts

- [x] At the deadline the scheduler reports the miss once, naming what is left, and every load goes on; when the last step is done it
  says how long after the deadline (2026-11-18 14:30 ET; `test_a_deadline_is_reported_as_missed_once_and_never_stops_a_load`:
  `assert 2 is None`, the old scheduler stopped everything and returned 2;
  `test_a_run_that_finishes_after_its_deadline_says_by_how_much`: `assert 2 == 0`)
- [x] The usage text, the argument help, the `auto` docstring and the init runbook say a deadline reports and never stops (2026-11-18 14:30 ET; read in the PR)
- [x] The scheduler tests end by cycles, not by the deadline (2026-11-18 14:30 ET; the chain tests, passing)
- [x] Learning → skill: the init runbook's scheduler paragraph (the data-operations skill holds no deadline rule for the scheduler) (2026-11-18 14:30 ET; this ticket)
