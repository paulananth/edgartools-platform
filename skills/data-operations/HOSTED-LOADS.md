# Hosted loads: what stops them, and how to resume

Read before starting or resuming a load on the hosted instance. Each item is a cause met on a real load and its rule.

## The gate: nothing loads until the infrastructure is ready and tested
`scripts/readiness.py` reads thirteen facts and writes `readiness.json` in the stores folder only on a full pass; `load_jobs.py`
refuses to start, resume or finish a load without it (the read-only `--plan`, `--list`, `--status` and `--catalog-status` still
run). A pass belongs to one store generation (a reset of the databases closes the gate), one commit (any new commit closes it)
and one day. Each check reads only what it asks (a capture is its folder's receipts file), never a plan of
the work. The checks: the code is committed, contains `main` and its commit has green CI (tested means CI, never a local run
alone); the compiled engine was built from this checkout's source (`readiness.py --build-engine` rebuilds it and records a hash of what it was built from); `doctor` is ready; the loader holds its connection limit, memory ceiling
and timeouts; RDM holds its codes and silver a table per spec; every step has a capture; no load runs and the loader has no
session; disk and load average have room; the access audit of the database has no failing control; every duty file's login connects to the databases of its duty (names only, a
driver's text is never kept); the run's state file is this store's, or is shown as one that will be set aside, with its count of done
steps; the catalog, when one is configured, matches the rules; and the merge policy, every Dataset Contract and every worker profile are registered and granted (init steps 5 to 7). The gate is not the init runbook: after a reset, walk every runbook step,
say in the report which ran and which did not, and never write a step off without reading why (a catalog step was once called
unconfigured when its file existed). A fact that cannot be
read is a failure. Fix what it names and run it again; there is no switch to skip it. A rehearsal of the first lane on a
disposable store is the next check to add.

## Where a load runs
A load runs in the loader image, never in a checkout: a checkout's code can differ from its tested commit (an engine not
rebuilt, an edit), and a deleted worktree stops its load. `.github/workflows/loader-image.yml` builds the image only from a
`main` commit that passed CI (`loader-sha-<commit>` on ghcr.io) and writes that commit into it; in the image the gate and
CODE read it in place of git, and ENGINE does not apply (the image compiles its own engine).
- **Start:** `infra/load-pipeline/load.sh [--plan]` pulls the image of `main`'s newest commit (it refuses while that image
  is not built), starts AWS Step Functions Local and one worker from the image, runs readiness, then every lane of the load jobs
  file at once and the finish. `load.sh [--plan] [--finish] <step>...` runs only those steps, in order. It waits and exits 0
  only on success. Try a new image with `--plan` first: read-only, seconds a step. `--force` (never with `--plan`) is force
  publish for every load of the run; `LOAD_DEADLINE_HOURS` must cover a reload of everything, which takes hours.
- **The load jobs file alone decides what runs.** The state machine names no lane and no step: its first task asks the loader for
  the lanes, and each lane runs its steps in order, each with the workers the load jobs file gives it, each holding until the
  steps it needs (in any lane) are done. Every lane runs at once: a cap would let a lane hold a slot while it waits
  on a lane still queued. A failure belongs to its load: a stop before the load's start is not counted.
- **A load never waits on what cannot come.** Before the first step, `load_jobs.py --begin` refuses the load when a
  step waits on a step that does not exist, on lanes that cannot finish, or, for named steps, on a step neither done
  nor earlier in the run (name it first). A plan runs the same check. While running, a needed step that failed, or a
  lane that stopped, broke or was killed, stops what waits on it at once. A step this load runs is done only once this
  load finishes it; one it does not run counts as done by an earlier load.
- **A failure stops only what depends on it.** A step that fails stops its lane and records the lane's later steps as not
  started; a step of another lane that needs one of them stops at once, never waiting on work that cannot come. The other
  lanes go on, and the execution fails at the end, with no finish. Fix, merge, and start again: done steps cost one call each.
- **A catalog that has moved fails readiness, so publish it first.** The CATALOG check compares the catalog's text with the
  `rules/` folder of the image's commit; any change under `rules/` (a file renamed, a rule edited) makes it `partial`, and
  the first task stops with `NOT READY`. Before `load.sh`, with the catalog's private file sourced: `edgar-warehouse rules
  catalog --root rules publish`, then `check` until it says `confirmed` (the init runbook's catalog step). A source's
  `inputs.yaml` is no rules version, so adding a delivery needs none.
- **Force publish is a whole-run act with one time.** `load.sh --force` (never with `--plan`) gives every load job of the run
  `--force`, and the engine names a forced run by its time: `load_jobs.py` takes that time once, so an attempt stopped at its
  `minutes` bound carries on in the same run instead of starting another. Use a new `RUN`, set `LOAD_DEADLINE_HOURS` from
  the sum of the longest path's bounds, and say the estimate before starting.
- **Read a load in the container, not on the host.** The load runs in the worker, so a host `ps` shows nothing of it: use
  `docker exec <worker> ps`, the worker's `/proc/<pid>/io` (bytes read and written between two readings show a step that
  works while its log is still empty), and the run's state file. The step's own log fills only when an attempt ends.
- **One task per poller.** The worker's `ps` sees only its container, so QUIET's process count no longer covers the Mac; the
  loader's database sessions still do. Never start `load_jobs.py` on the Mac beside it.
- **Mounts:** the logins and the captures are read-only; the stores folder and `LOGS` are written (the readiness record,
  the run's state). Host networking lets the worker reach the stores and the catalog as the Mac does.

## Before a load starts
- **Role guards first.** `infra/scripts/harden-hosted-roles.py --confirm` (owner login) gives every login a connection limit,
  statement and idle-transaction timeouts, a `work_mem` ceiling for the loader and the audit classes. A load with the
  instance's default `work_mem` (hundreds of MB per sort or hash step and session) ran the server out of memory with ten
  merge workers. The access-audit skill tests these guards.
- **The engine must match the code.** A Rust change reaches a load only after the engine is rebuilt into the environment that
  runs it: `readiness.py --build-engine`. A step that fails with a missing method or an unknown normalizer on today's `main` is
  a stale engine, not a data fault: rebuild, then run the gate again.
- **A load that ends at once after a reset has read a stale state file.** The state file's `chain store` line names the store and
  the database's generation; a line with no generation comes from before generations were recorded and cannot show the store was not
  made again, so it is set aside (kept, renamed). A load that ran no step and printed `chain done` is the sign: look at the file's
  marker, set a file with an old marker aside, and start again. Done steps cost one call each, so setting a file aside loses little.
- **`EDGAR_WAREHOUSE` names the executable** (`.venv/bin/edgar-warehouse`), never its folder: a folder fails with
  "Permission denied" on every step.

## While a load runs
- **One scheduler per run label.** A second `load_jobs.py --auto` on the same label doubles every step. Look for a running
  scheduler (`ps`) before starting one, and stop the scheduler before its steps.
- **A run label names the state and logs, never an input.** A new `RUN` gives a fresh state file and loads the same
  records: the capture runs are the load jobs file's `capture_label` and a fact is written as its value. Changing either is a
  new input of every record it reaches: the Change Journal processes those files again and the Stage refuses them under
  the same revision, so it needs `--revision` above the last load's.
- **Plan one step with `--plan --only <step>`** (or `--lane`): it prints the documents, the bundles, and the open runs a load
  would finish first and those it would leave. A plan of every step takes minutes.
- **Read the database with the database-monitoring skill**: `summary` and `locks` every check,
  `logs` after any step that stops with a database error.
- **Resizing a step is a decision with a price, never a reflex.** The scheduler resizes a running step by stopping it and starting it
  again, which abandons the bundle in flight, so each move is checked against the seven wastes:

  | Waste | The check before a move |
  |---|---|
  | Over-processing (work thrown away) | Only a step whose log names more than one bundle is moved, and only within a minute after one of its bundles completed, so next to nothing is abandoned. A step of one bundle, or one that has named none yet, keeps its workers |
  | Over-production (workers nothing uses) | A raise needs the last raise measured and its bundles a minute up by a fifth; otherwise the step waits on the same bottleneck and is held. More workers never speed a single bundle |
  | Motion (restarts for no gain) | Shedding needs the pressure to last four cycles; a spike moves nothing. One move a cycle, a step at most every ten minutes |
  | Waiting | A step with under thirty minutes left is left alone: its restart costs more than it saves |
  | Defects | The capacity's range, from the memory a worker is sized for, bounds every count; the machine's cores and memory are the limit, not the request |
  | Inventory, Transport | Start each step at its declared workers within the range so it needs no resizing to find its size |

  A step that shows `attempt 1 start` again and again with `scheduler moves` lines between is losing its work: stop the scheduler (not
  the steps), let the step finish, then run what follows with `--only` and `--finish`.
- **A step that shows no CPU, no session and no rows may be waiting, not stalled.** The mastering lease serializes steps that write the same
  masters: a step behind another source's merge sat silent for hours and wrote at full rate within minutes of that merge ending. Before stopping a step
  with no sign of work, read Bookkeeping's open runs and leases (`bookkeeping.pipeline_run` where the state is not complete, and `bookkeeping.lease`)
  and the sessions that are working (`db_monitor.py sessions`); stop a step only when nothing holds what it waits for. A stop abandons the
  bundle in flight.
- **Read a running load without printing where it connects.** `lsof`, `ps` and `sample` print the instance's hostname and addresses; mask them
  (`<ip>`, the hostname) in the same command, as the database-monitoring commands already do, and count sockets instead of listing them.
- **Run `readiness.py` beside a load only to read it**: it fails QUIET (a load runs) and nothing else, and then leaves the passing record of this
  store and this code in place, so the running scheduler keeps starting steps. Any other failure closes the gate, as it should.
- **The projected end counts a running step from its first attempt's start in the state file**, so a restarted scheduler does not reset it; a step with
  no per-bundle progress (one document) is still an upper bound until it ends.
- **A scheduler that "stopped" has usually finished everything it could**: it names the failed steps and what waits on them.
  Fix the cause (engine, memory, a login), then start it again; done steps cost one call each.
- **`mdm build-lookups` and `mdm clear` refuse while Bookkeeping holds a running run of a mastering target** (a worker between two merge transactions holds no
  lock, so the store's own check cannot see it). A run left open by a stopped attempt blocks them until it is finished: resume it, never skip the check.
- **Read how often a mastering merge went alone after a load**: `grep mastering_merge_alone <the step logs>`. A line names each reason and its
  count; no line in any step log means no part merged alone, and the kind lock was shared throughout. Lock waits are read the same
  way as every wait: sample `pg_stat_activity` and `pg_locks` (wait event and lock type) as the diagnostic login, and say each wait's share.

## The finish takes at most five minutes
`--finish` builds the links tables and `master_binding` from the stored records; `master_binding` is two statements inside the data database
(an upsert that writes only a changed row, and a delete), so no binding row reaches the client; no silver row is written with a master id. A finish that takes minutes more than five is the measure of the slowest phase still left (time each phase,
below), never a reason to skip it: Gold and the links read what it writes. It is bounded by the operator at five minutes, and a longer
one is a defect, not a wait. Time each part of a slow finish by phase
before changing it, and run the cheap check that can fail first. For a step that is one native call, sample the running process
(`sample <pid> 30`) before reading its code: the links build spent 265 s in a pairwise comparison of every link with every later link,
which no phase timing could name. **Measured phases of the finish on the hosted store** (`silver links`, 1,776 s to 238 s): a lookup of tens of thousands of keys is read by streaming the
table once (a 2,000-key probe costs 300 to 630 ms of random reads, a streamed table 150,000 rows a second), a predicate that matches almost nothing in a
large table (links in 13 GB of one source's bodies) is served by a partial index, a landing batch is one round trip so it carries 5,000 rows, and a
table rebuilt from rows already in the database is one join pass that writes only what changed. Time the phases before choosing a build: an incremental
build would not have shortened the first finish after a full load. A phase that moves a table between two schemas of one database through the client is the same defect: the binding
rebuild read 4.4 million rows into Python and wrote them back (18 of the finish's 30 minutes) until it became one statement. Count a landing's round trips
a batch before changing its size: the writer made three a batch (70 ms each) and now makes one.

## Stopping loads
- Stop the scheduler first (it would start the next step), then its step processes. The state file keeps every done step.
- Before a hosted reset, follow the quiesce and drain procedure in the repository's Edgar Intelligence initialize
  runbook: stop clients that can reconnect, confirm no open Bookkeeping runs or leases, resolve managed mirrors under
  their own approval, restart the PostgreSQL service, wait for `READY`, and rerun the read-only reset preflight. An
  empty load-jobs status alone does not prove that the databases have no sessions. The preflight must find no client
  sessions or active transactions. It reports idle PostgreSQL extension workers separately; the approved reset records
  and disconnects those with `DROP DATABASE ... WITH (FORCE)`. Stop for any client session or extension worker with an
  open transaction; never terminate internal sessions directly or bypass the reset script's classification.
- The reset script (`reset-hosted-databases.py --words "<the operator's words>"`, which records them) requires the
  operator's sign-off and refuses while a client session or transaction remains. The approval record includes counts of
  the idle extension worker sessions that `DROP DATABASE ... WITH (FORCE)` disconnects. After the reset, expect the
  previous run's done steps to be set aside as another store's state. It deletes the dropped stores' run files
  (`<manifest root>/load`) and keeps the extracts.

## Dropping objects nothing reads
A store's objects that no code reads (tables, functions, views) are dropped in place on the operator's words, never by a
reset. What a reader needs is first copied to where it is read and checked equal row by row, keeping each number a stored
id depends on (a reading's version is hashed into its records' ids). Then one owner script, refusing unless idle: in one
transaction it counts every other object and the main tables' rows, drops, counts again, and commits only when both are
unchanged and none of the dropped objects is left; it records the operator's words in the stores folder's approvals log.
Report the counts before and after.

## Run files
A load writes each bundle's prepared files under `<manifest root>/load/<source>/<target>/<run>/bundle-NNN` and deletes them
once that bundle's run is verified complete: Bookkeeping keeps the manifest's hash, the capture keeps the bytes. Only a run
that stopped keeps its files, so it can resume. Files kept with nothing that refers to them are inventory waste: they fill the disk until the
readiness disk check fails.
