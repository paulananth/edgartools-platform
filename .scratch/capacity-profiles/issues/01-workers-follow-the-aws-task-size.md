# Workers follow the compute, not a fixed two to eight

Status: open
Type: task

Operator, 2026-11-18: "make workers scale to AWS step function configuration, it is no longer fixed to 2 to 8". Asked
how to get the configuration, the operator chose "Read them from AWS, read-only".

## What AWS says (read-only: `describe-task-definition`, `list-state-machines`, `describe-state-machine`; account
690839588395, us-east-1; sizes and concurrency only)

- The dev task definitions are gone (dev was decommissioned); the production ones are `edgartools-prod-small` 0.5 vCPU / 1 GB,
  `-medium:307` 1 vCPU / 4 GB, `-large:305` 2 vCPU / 8 GB, `-mdm-small:274` 0.5 / 1, `-mdm-medium:272` 1 / 4.
- The production state machines (`load-history`, `daily-incremental`, `mdm`) run steps on those sizes; their Map states
  have `MaxConcurrency` 1 and a tolerated failure of 0 to 15 percent.

## Parts

- [x] The chain file names the compute as capacity profiles (`aws-small`, `aws-medium`, `aws-large`: vCPU and memory), and
  `--capacity local` measures the machine (2026-11-18 08:59 ET; `test_the_chain_file_names_the_aws_task_sizes_the_state_machines_run_on`)
- [x] A step's workers range comes from the profile: a worker is sized at half a gigabyte and four share a vCPU, so small
  1 to 2, medium 1 to 4, large 1 to 8, and a bigger task more with no code change; the scheduler's rescale, its start
  count and `--workers` all use it (2026-11-18 08:59 ET; `test_a_workers_range_follows_the_tasks_memory_and_vcpus_not_a_fixed_two_to_eight`:
  `workers_range` did not exist; `test_a_started_step_is_held_to_the_profiles_range`; `rescale` takes the bounds; 61 tests)
- [x] Every run mode holds a step's workers to the capacity, not only `--auto` (`--only <step> --capacity aws-small` once
  started the chain file's 8 workers on a 1 GB task): `clamped` (2026-11-18 09:01 ET; `test_every_run_mode_holds_a_steps_workers_to_the_capacity_not_only_the_scheduler`:
  `clamped` did not exist). The floor is now the profile's, 1, where the fixed range had 2: a 0.5 vCPU, 1 GB task carries
  one or two workers
- [x] The scheduler passes the capacity to each step it starts, so the step's own `--workers` check uses the same range
  (2026-11-18 09:03 ET; `test_a_started_step_is_told_the_capacity_it_runs_on_so_its_own_check_uses_the_same_range`: no `--capacity` in the
  child's command; a `--auto --capacity aws-large` run on a 4 GB machine would have failed its steps at start)
- [x] The skill and the runbooks say it: data-operations (the workers a step can carry), daily-run "Capacity: the workers
  follow the compute" with the table of profiles (2026-11-18 08:59 ET)
- [ ] How many steps run at once in AWS is the Map state's `MaxConcurrency`, one in today's state machines: set it with the
  lanes of the chain when the load runs there, within the 500 connections of the hosted instance (`--slots` does this on a
  machine)
- [ ] A load running in AWS reads its profile from the task it runs in (the ECS task metadata) instead of a flag
- [x] Learning → skill: data-operations SKILL.md and daily-run runbook, "Capacity: the workers follow the compute" (2026-11-18 08:59 ET)
