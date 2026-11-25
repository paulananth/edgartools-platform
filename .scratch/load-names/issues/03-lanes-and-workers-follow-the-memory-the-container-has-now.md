# 03: The lanes at once and each step's workers follow the container's live memory

Status: open
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

- [x] Ticket, tests first: `test_a_step_takes_its_declared_workers_...`, `test_a_step_waits_for_the_memory_of_its_floor_...`, `test_a_container_with_no_memory_limit_...`, `test_the_free_memory_is_the_cgroup_limit_...`, `test_one_step_is_admitted_at_a_time_...` failed first (no `admit`); 193 passed in `tests/unit/test_load_jobs.py` after (2026-11-25 15:13 ET)
- [x] `attempt_loop` admits each attempt and starts the load with the admitted workers (a copy of the step); its log line names them (2026-11-25 15:13 ET)
- [x] `load.sh`: `MaxConcurrency` = the number of lanes (`--lane-count`); the monitor's lane budget is the reference of the declared widths; HOSTED-LOADS.md, the load-monitoring skill and the board's legend say so (2026-11-25 15:13 ET)
- [x] Measured in the loader container, read only: free memory 1.46 GB with no load running; `admit` gives a step wanting 4 workers 3, wanting 8 gets 4, wanting 16 gets 8 (half) (2026-11-25 15:13 ET)
- [ ] The hosted reload reads: more than 2 lanes at once, no step killed for memory (status -9), each step's workers named in its log. The reload now running was started before this merges
- [x] Learning → skill: `skills/data-operations/HOSTED-LOADS.md`, "Lanes and workers follow the container's memory now" (2026-11-25 15:13 ET)
