# Can GLEIF run 16 workers, or the same load on several lanes?

Status: resolved
Type: task

Operator, 2026-11-18: "Can you scale up to 16 workers or can you run the same load on multiple lanes: GLEIF". Answered from
measurements on the running hosted load.

## Findings

- GLEIF runs 8 worker processes. The status report missed them (a spawned worker's command line names no source), so it
  showed 0% CPU for a step that used 164%; the whole tree is 12 processes and 3.3 GB.
- Each worker uses 15 to 20% of a core and holds 324 to 421 MB. The store had one session working of 25 and no lock waiters:
  the workers wait on round trips to the database, so they are latency-bound, not CPU- or lock-bound.
- Sixteen workers would hold about 6 GB (plus the driver) and use about 3 cores. This Mac has 8 GB and was using 7 GB of swap,
  and an AWS large task has 2 vCPUs: neither carries 16.
- The same load cannot run on several lanes: two loads of one source and target would write the same outputs (the chain
  refuses it), and GLEIF is one document in one bundle, so its parallelism is the workers inside the merge.
- Restarting it to change the workers costs a re-read of about fifteen minutes (ticket 238's measured figure), and the merge
  was near the end of the 125 minutes its earlier measured rate (458 records a second over 3.4 million) gives: not worth it.
- A correction: I first reported 35 to 50 MB a worker, read from the three processes the status found, which left the workers
  out. The workers' own footprints were measured afterwards.

## Parts

- [x] The status finds a load's workers by parentage and shows the workers it was started with, not the chain file's
  (2026-11-18 09:54 ET; `test_a_loads_processes_include_the_workers_it_started_whose_command_lines_name_no_source`: a spawned worker was
  not matched, so a step at 164% CPU read 0%; `test_the_workers_a_load_runs_with_are_read_from_its_command_line_not_the_chain_file`)
- [x] A step can state its measured memory per worker, and its range follows it (`worker_gb`): GLEIF 0.4, so a machine with
  the memory carries more of them (2026-11-18 09:54 ET; `test_a_workers_range_can_use_a_steps_measured_memory_not_only_the_default_share`)
- [x] The status says its rows a minute are counted when a transaction commits: GLEIF's long transactions showed none for a
  minute and a burst the next (2026-11-18 09:54 ET; `test_the_status_header_says_writes_are_counted_at_commit`)
- [ ] ~~16 workers on a task with the memory and vCPUs, measured against 8~~ deferred to .scratch/gleif-scaling/issues/02-measure-16-workers.md: no
  compute here carries them (about 6 GB, 3 cores), and the AWS sizes are small, medium and large
- [x] Learning → skill: the data-operations skill, "Report a running load from its evidence", reads a step's workers by its
  process tree (2026-11-18 09:54 ET)
