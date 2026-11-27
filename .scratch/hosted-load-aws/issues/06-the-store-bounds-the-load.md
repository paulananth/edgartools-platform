# The store bounds the load

Status: open
Type: bug
Owner: claude (operator, 2026-11-27: "find root cause, 5-whys and fix"; then "resize the instance and stop the load")

The AWS load `aws-20261127` lost `nport-security-silver` and `company-facts` (attempt 1 each) to PostgreSQL 53200, which the
loader reported as "a value is not its column's type or a storage constraint refused the delivery".

## 5 whys

1. The sessions of `ipo`, `nport-security-silver` and `company-facts` got "out of memory" within 23 s (16:19:16 to 16:19:39 ET).
2. The hosted instance (`m8g.medium`: 1 vCPU, 4,096 MiB, read from AWS; family `STANDARD_M`) was out of memory: pg_lake's
   query engine, where the mirror's change export runs, failed 80 MB allocations from 15:49 ET; the export's last flush was
   15:53 ET (15.4 GB behind at 16:43 ET); CPU idle 0% from 15:50 ET; 96 to 135 connections, about 26 active, each sort or
   hash allowed `work_mem` 384 MB.
3. The load ran 11 lanes at once, and the controller raised steps (openfigi-answers from 4 to 8 workers).
4. Lanes, admission and raises read the client only (the Fargate task: 16 vCPU, 120 GB, 20% CPU and 8% memory in use at
   16:40 ET), and the controller's database bound was a fixed 250 connections.
5. From the Mac, a 0.25 to 0.4 MB/s uplink held back what reached the store; from AWS it received 1.6 to 2.9 MB/s.

Root cause: the load's concurrency was sized by its compute, never by its database.

## Checklist

- [x] Stopped the load: execution ABORTED 16:46 ET, task stopped 16:48 ET (2026-11-27 16:55 ET)
- [x] `rules/load-jobs.yaml` `stores:`, named by `LOAD_STORE` (both pipelines name `hosted`; a load that names none has no store bound), each the instance's cores, memory, `work_mem`: four workers a core and half its memory in `work_mem` shares; admission waits for the store and takes no more than it has left; the controller and the local scheduler raise nothing into a full store and shed from one held past it; a load's workers count once though a launcher shows it twice; the lane budget names `store` when it is the limit: `test_a_step_waits_while_the_store_is_full_and_starts_with_no_more_than_it_has_left` (fails on main: `admit` takes no store), `test_the_controller_raises_nothing_into_a_full_store_and_sheds_from_one_held_past_it`, `test_the_lane_budget_names_the_store_when_the_database_carries_fewer_workers_than_the_compute`, `test_the_store_carries_four_workers_a_core_and_half_its_memory_in_work_mem_shares`, `test_the_workers_in_use_are_every_running_loads_own_count_and_a_plan_holds_none` (2026-11-27 16:55 ET)
- [x] The refusal says what its SQLSTATE class means; only 22 and 23 blame the delivery: `test_a_refusal_says_what_its_sqlstate_class_means_and_only_a_value_or_constraint_blames_the_delivery` (53200 fails on main: "a value is not its column's type or a storage constraint ...") (2026-11-27 16:55 ET)
- [x] Tests: load jobs, load monitoring, silver writer, 349 passed; `terraform validate` (2026-11-27 16:55 ET)
- [x] The operator resized the instance to `STANDARD_L` (2 cores, 8 GB): "upgraded to _L , _XL not supported"; `stores: hosted` names it, 8 workers across every step (four to a core) (2026-11-27 16:55 ET)
- [ ] The resize read back on the instance: at the first reading `db_monitor.py` still showed `m8g.medium`, shared buffers 948 MB
- [ ] The mirror restarted after the resize and read back exactly the record
- [ ] The load run again on the bound (same `RUN`), without 53200
- [x] `/code-review` (Standards, Spec, GoF) on `risky-reviewer`: fixed one global store bounding local runs too (now named per load), a load counted twice through its `uv` launcher, the local scheduler raising into a full store, every 40xxx code read as a deadlock, the untested raise clamp and no-other-load escape, and wording that said lanes are bounded (they start and queue at admission); left: a MySQL refusal (no SQLSTATE) reads "the database refused the delivery"; GoF: leave it (2026-11-27 16:55 ET)
- [x] Learning → skill: HOSTED-LOADS, "The store bounds the load, not only its compute" (2026-11-27 16:55 ET)
