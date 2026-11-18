# A fresh run's projection uses the previous run's measured times

Status: open
Type: task

Seen 2026-11-18 on the second hosted load: the scheduler's first line read "projected end 03:54 ET (an estimate from the 0 steps done)"
against a deadline 3 hours out. With no step done it sums the step bounds, so a fresh run is told it will miss the deadline by hours
until its first step finishes, and its priorities (longest chain first) use bounds, not measured times.

## Parts

- [ ] Seed the estimate from the previous run's measured minutes (`measured` over the state file the run set aside or the last
  `chain-*.log` of the same chain file), with a test that fails first: a fresh state file and a prior file with measured steps
- [ ] The first projection says where its estimate came from (this run, the previous run, or the bounds)
- [ ] Learning → skill: data-operations (the scheduler's estimate)
