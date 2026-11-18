# A running step is moved at most once in ten minutes

Status: open
Type: task

Operator, 2026-11-18, seeing IPO at "about 2 hours left" after it had been optimized to load four bundles at once: "We had optimized
before, check".

## Findings (five whys, from the scheduler's own log)

- IPO was started with `--bundles 4` (four bundles at once, as set from the first load's measurement) but ran at about 1.2 bundles a
  minute, a third of what four at once should give.
- The scheduler had moved it between 1 and 2 workers at least five times in twenty minutes: "low load" raised it, the next cycle's
  "high load" lowered it. The load average crosses the line both ways within a minute while several loads start and stop.
- A move stops the step's load and starts it again: the four bundles in flight are abandoned and a start is paid each time. The
  workers a step has matter far less than the bundles it keeps running.

## Parts

- [x] A step is moved (stopped and started again) at most once in ten minutes, from its start or its last move (2026-11-18 15:13 ET;
  `test_a_running_step_is_moved_at_most_once_in_ten_minutes_however_the_pressure_swings`: the old scheduler made 23 moves in 25
  minutes, `assert (24 - 1) <= 2`)
- [x] The live scheduler was swapped to this code with the four running loads untouched (2026-11-18 15:13 ET; 4 loads before and after)
- [ ] Measure IPO's rate over an hour with no moves, against the 1.2 bundles a minute
- [x] Learning → skill: the init runbook's `--auto` paragraph says a step is moved at most once in ten minutes (2026-11-18 15:13 ET; read in the PR)
