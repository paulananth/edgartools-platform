# 03: The lanes at once and each step's workers follow the container's live memory

Status: resolved
Type: task
Blocked by: none
Blocks: none

Operator, 2026-11-25 15:13 ET: "we want to run more lanes", then "I want dynamic load balancing and memory optimization not a fixed setup".

Found 2026-11-25: the hosted load ran 2 lanes of 11 at once. The number is fixed before the load starts (the container's
memory over 0.4 GB a worker, over the widest first step of a lane, 4 workers) and baked into the Step Functions Map
(`MaxConcurrency`), whatever the steps then use. A step takes its declared workers whatever memory is free.

## Design (KISS and the seven wastes: operator, 2026-11-25 15:13 ET, "kiss and 7 wastes must be considered")

The GoF consult (risky-reviewer: no pattern, plain functions) proposed a ledger of reservations with pid pruning and a priority
queue; that is over-production (code for cases not seen) and was cut to the one thing that is needed:

- Every lane starts (`MaxConcurrency` = the lane count, `load_jobs.py --lane-count`): no lane waits in the state machine.
- `admit` in `load_jobs.py`, just before a step attempt's load starts (after its waits, per attempt): one step at a time under a
  `flock` held through a 30-second settle window (the lock is the whole ledger: a dead lane's lock goes with its process, no pid
  to prune), it waits until the free memory covers half the step's declared workers (at its `worker_gb`), then starts with as
  many as fit, up to its declared workers. Order is the lock's, no priority queue (the load jobs file's waits already order the
  steps that depend on each other).
- Free memory: the cgroup limit less use (file cache free) where the container has a limit (ECS), else `MemAvailable` (a container
  on a Docker VM has no limit of its own: measured `memory.max` = `max`, so the first version, which read only the cgroup, would
  have changed nothing). Unreadable: the declared workers, as before.
- Progress guarantee: with no other `edgar-warehouse load` running, a step starts at its half whatever the memory.
- Waste kept out: no ledger file, no priority queue, no reservations, no new module (a sibling import needs a path hack), no
  change to the local chain scheduler (`rescale` already follows the machine there).

## Checklist

- [x] Ticket, tests first: `test_a_step_takes_its_declared_workers_...`, `test_a_step_waits_for_the_memory_of_its_floor_...`, `test_a_container_with_no_memory_limit_...`, `test_the_free_memory_is_the_cgroup_limit_...`, `test_the_next_step_is_admitted_only_after_the_first_has_settled`, `test_a_step_says_once_...` and `test_a_load_of_another_lane_is_seen_by_its_command_line_in_either_form_the_loader_runs_it` failed first with `AttributeError: module 'load_jobs' has no attribute 'admit'` (the lane-count test replaced one that asserted `--lanes-at-once` in `load.sh`; on the old script `--lane-count` is an unknown argument, exit 2); 193 passed in `tests/unit/test_load_jobs.py` after (2026-11-25 15:13 ET)
- [x] `attempt_loop` admits each attempt and starts the load with the admitted workers (a copy of the step); its log line names them (2026-11-25 15:13 ET)
- [x] `load.sh`: `MaxConcurrency` = the number of lanes (`--lane-count`); the monitor's lane budget is the reference of the declared widths; HOSTED-LOADS.md, the load-monitoring skill and the board's legend say so (2026-11-25 15:13 ET)
- [x] Measured in the loader container, read only: free memory 1.46 GB with no load running; `admit` gives a step wanting 4 workers 3, wanting 8 gets 4, wanting 16 gets 8 (half) (2026-11-25 15:13 ET)
- [x] Found by the Spec review: `load_running` used `pgrep -f "edgar-warehouse load"`, which misses the loader image's command line (a python one-liner); it now uses `external_loads` (`LOAD_COMMAND`), and a step that waits says so once in its log (2026-11-25 15:15 ET)
- [x] The lane controller (operator, 2026-11-25: "yes build the controller"): `choose_move` taken out of `auto` (its 8 scheduler tests pass before and after, unchanged), `control_cycle`/`control` as a daemon thread of the activity worker, `ask_move` + `take_move` as the request file. Failed first with `AttributeError: module 'load_jobs' has no attribute ...`: the tests from `test_a_running_step_asked_to_move_...` on; that one runs a real engine process with a worker under it and asserts the counts `8 4` in one attempt and both processes ended (2026-11-25 15:50 ET)
- [x] GoF consult's finding "append the log on a move" not taken: an appended log counts a bundle twice (its `complete` line and the restart's `already loaded` line); the log starts again, as in `auto`, and a step with no bundle named yet is not moved (2026-11-25 15:50 ET)
- [x] GoF consult's finding "signal the engine pid only" changed: spawned pool workers outlive a killed driver, so a move ends the load's whole process set, the driver first (2026-11-25 15:50 ET)
- [x] Reviews (risky-reviewer): GoF leave it; Standards: tests patch with `checked` and wait on a FIFO, not a clock; Spec: driver pid found by its command line, a request cleared before each load and when the driver is gone, a shed resets the pressed count, a `--plan` is no load; each has a test (2026-11-25 15:53 ET)
- [x] Known limit: a raise can come back at its old count when a waiting lane takes the memory its restart frees; the restart waits out the old run's lease (120 s at most, read in code, not measured) (2026-11-25 15:53 ET)
- [x] Found on the hosted load `hosted-lanes-20261125`: the gate admitted steps on memory alone while the load average was 11.5 on 8 cores, and the controller then shed `company`, the step `gleif` waits on, from 2 workers to 1 (21:26 ET). The gate now waits while the CPU is pressed (`cpu_level`, the controller's own reading), unless no other load runs (operator, 2026-11-25: "yes build it and merge on green"). `test_a_step_waits_while_the_cpu_is_pressed_...` failed first with `TypeError: admit() got an unexpected keyword argument 'pressed'`; 271 passed after (2026-11-25 21:32 ET)
- [ ] ~~The gate's queue lets in first the step with the most work waiting behind it~~ deferred to a ticket of its own: lanes wait on one `flock`, and ordering them needs a shared queue with a check for waiters whose process has died; first read on the next load whether the CPU wait alone stops the shedding of long-chain steps
- [x] A hosted load shows a move of the controller in its state file, and the moved step finishes with the same documents: `hosted-lanes-20261125` (image `4bbeaefc`) logged 16 moves; the moved steps finished with the last run's document counts: `ownership` 5,356 (2,796 + 2,560 already loaded), `company` 76,380 (39,004 + 37,376), `openfigi-answers` 7,730 (50 + 7,680), read from both runs' state files (2026-11-26 07:48 ET)
- [ ] ~~The hosted reload reads: more than 2 lanes at once, no step killed for memory (status -9), each step's workers named in its log~~ moved to ticket 04: `hosted-lanes-20261125` ran up to 7 lanes at once and named each step's workers, but `openfigi-answers` was killed for memory once (status -9, the VM's `oom-kill` of its source reading, 22:51 ET)
- [x] Learning → skill: `skills/data-operations/HOSTED-LOADS.md`, "Lanes and workers follow the container's free memory" (2026-11-25 15:13 ET)
