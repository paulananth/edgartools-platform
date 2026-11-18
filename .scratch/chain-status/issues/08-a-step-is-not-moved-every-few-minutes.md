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

- [x] A step is raised (stopped and started again) at most once in ten minutes, from its start or its last move; a pressed machine sheds the shortest chain at once (2026-11-18 15:13 ET;
  `test_a_running_step_is_moved_at_most_once_in_ten_minutes_however_the_pressure_swings`: the old scheduler made 23 moves in 25
  minutes, `assert (24 - 1) <= 2`)
- [x] A pressed machine sheds the step with the shortest chain whenever it last moved; before, a step in cooldown shielded itself and the shed fell on a longer chain (2026-11-18 15:20 ET; `test_a_pressed_machine_sheds_the_step_with_the_shortest_chain_even_when_it_moved_lately`)
- [x] The live scheduler was swapped to this code with the four running loads untouched (2026-11-18 15:13 ET; 4 loads before and after)
- [ ] Measure IPO's rate over an hour with no moves, against the 1.2 bundles a minute
- [x] Learning → skill: the data-operations skill's "Bundles and readers" line (the `--auto` sentence) and the init runbook's `--auto` paragraph say a step is raised at most once in ten minutes and shed at once under pressure (2026-11-18 15:13 ET; both read in the PR)
