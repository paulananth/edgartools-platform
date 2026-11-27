# The monitor reads a load from its copied logs

Status: open
Type: task
Owner: claude (operator, 2026-11-27: "add the switch on its own branch")

The operator asked "why there are no lane data". Grafana on the Mac read the AWS load `aws-20261127` from its logs copied
from S3. A step counts as running only when its load's processes are seen on the machine the exporter runs on, and
this load's processes are on AWS: every started step showed as waiting, `load_lanes_running` read 0, and the per-step
panels had no rows.

## Checklist

- [x] `LOAD_ELSEWHERE=1`: a step whose latest line is an attempt's start is running, from the state file alone (one between attempts is waiting); its CPU and memory are None, the text report says "processes on another machine", the five whys say "not measured here": `test_a_load_whose_processes_run_elsewhere_shows_each_started_step_running_from_its_copied_logs` (2026-11-27 16:35 ET)
- [x] The exporter publishes no CPU or memory for such a step, never a zero: `test_a_step_whose_processes_run_elsewhere_publishes_no_cpu_or_memory_rather_than_a_zero` (2026-11-27 16:35 ET)
- [x] Tests: load jobs and load monitoring, 277 passed (2026-11-27 16:35 ET)
- [ ] Live: Grafana shows the running steps of `aws-20261127` from its copied logs
- [x] `/code-review` (Standards, Spec, GoF) on `reviewer`: fixed a step between attempts read as running, a stalled verdict saying "no CPU" from the Mac's zero, the test patching without `checked`, the repeated None; GoF: leave it (2026-11-27 16:35 ET)
- [x] Learning → skill: load-monitoring, "Where the exporter runs" (`LOAD_ELSEWHERE=1` for copied logs) (2026-11-27 16:35 ET)
