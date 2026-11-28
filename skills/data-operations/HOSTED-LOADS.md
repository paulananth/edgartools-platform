# Hosted loads: what stops them, and how to resume

Read before starting or resuming a load on the hosted instance. Each item is a cause met on a real load and its rule.

## Prepare a fresh worktree for the local operations
Before running a hosted-store operation script from a fresh worktree, install the project's runtime dependencies with
`uv sync --extra s3 --extra mdm-runtime --extra mirror` (the last for the mirror's refresh after a load). `uv run` alone may create `.venv` without installing SQLAlchemy and the
other MDM dependencies, so a preflight can fail before it reaches the store. Run project Python commands with `uv run`;
source the private hosted environment file in the same shell without printing its values. This prepares local tooling;
the hosted load itself still runs from the CI-built loader image below.

## The gate: nothing loads until the infrastructure is ready and tested
`scripts/readiness.py` checks hosted readiness and writes `readiness.json` in the stores folder only on a full pass; `load_jobs.py`
refuses to start, resume or finish a load without it (the read-only `--plan`, `--list`, `--status` and `--catalog-status` still
run). A pass belongs to one store generation (a reset of the databases closes the gate), one commit (any new commit closes it)
and one day. Each check reads only what it asks (a capture is its folder's receipts file), never a plan of
the work. The gate that counts is the one the loader image runs as a load's first state: a pass on the Mac proves only the Mac. So
a check reads through a Python driver the image installs (Snowflake through `snowflake-connector-python`, the `mirror` extra),
never a command-line tool, the image carries every file a check reads (`destination/` holds the mirror's exposure list), and
the image's CI smoke step imports each driver. The checks: the code is committed and contains `main`;
`doctor` is ready; the loader holds its connection limit, memory ceiling
and timeouts; RDM holds its codes and silver a table per spec; every step has a capture; no load runs and the loader has no
session; disk and load average have room; the access audit of the database has no failing control; every duty file's login connects to the databases of its duty (names only, a
driver's text is never kept); the run's state file is this store's, or is shown as one that will be set aside, with its count of done
steps; and the merge policy, every Dataset Contract and every worker profile are registered and granted (init steps 5 to 7). The gate is not the init runbook: after a reset, walk every runbook step,
say in the report which ran and which did not, and never write a step off without reading why (a catalog step was once called
unconfigured when its file existed). A fact that cannot be
read is a failure. Fix what it names and run it again; there is no switch to skip it. `MIRRORED unreadable (Snowflake error
090073)` is Snowflake refusing the warehouse: a resource monitor (the platform's is the access root's `snowflake_resource_monitor`)
is over its quota. A monitor
set on the account stops every warehouse even when the warehouse shows none (`SHOW WAREHOUSES` says `null`): an account
administrator reads `SHOW RESOURCE MONITORS` (its `level` column) and raises that quota (`monthly_credit_quota` of the
Snowflake access root), or the load waits for the monthly reset. List the mirror once before clearing a store
(`mirror_sql.py status | mirror_run.py`): suspending it, resuming it and this check all need the warehouse. A rehearsal of the first lane on a
disposable store is the next check to add.

After truncating tables for a full reload, assign a new `RUN` label and use
it for readiness and every invocation of the hosted load pipeline. Confirm
the state is fresh with zero done steps, and take the step count from the
current loader's job list. Keep the previous run log as history. Start the
complete plan with `RUN=<new-label> bash infra/load-pipeline/load.sh` (no step
arguments). Use that label again only when resuming this same load.

## Where a load runs
- **On AWS (a whole load, and any large write):** `RUN=<label> infra/load-pipeline/aws-load.sh [--finish] [<step>...]` copies
  the image of `main`'s newest commit to ECR, the captures the load jobs file reads to `s3://<bronze>/load/`, and the logins
  to Secrets Manager; applies `infra/terraform/load-machine` (one Step Functions state machine, the same definition,
  and one 16 vCPU, 120 GB ARM Fargate task); runs one execution and stops the task when it ends; after an execution that succeeds it refreshes the mirror and waits for the apply (`mirror_refresh.py`, as the mirror operator), so Gold reads the load at once instead of at the mirror's next interval; `load.sh` does the same. `--plan <step>` runs readiness and plans those steps, read only, to prove a changed pipeline; `--prepare` stops before
  the task. The task holds no provider identity, so a load reads captured files only. Its state file, logs and run documents
  are in `s3://<bronze>/load/runs/<RUN>/` (copied every minute and at a stop), and a task started again with the same
  `RUN` takes them back and carries on. Grafana on the Mac shows the load: the task runs the load monitor's exporter, open
to the Mac's address only, and the script points the Mac's Prometheus at it (`load-monitoring`, "Where the exporter runs"). A task lost without a stop lacks the last minute or so of run documents: a run
  that then refuses a missing document is not driven again. The task costs about 1 USD an hour while it runs; it stops itself after the
  root's `max_hours` (24). The script keeps its machine awake, starts the execution and stops the task. A home uplink to the hosted store is slow and drops long
  writes; AWS sits beside it.

A load runs in the loader image, never in a checkout: a checkout's code can differ from its tested commit (an engine not
rebuilt, an edit), and a deleted worktree stops its load. `.github/workflows/loader-image.yml` builds the image only from a
`main` commit that passed CI (`loader-sha-<commit>` on ghcr.io) and writes that commit into it; in the image the gate and
CODE read it in place of git.
- **Start:** `infra/load-pipeline/load.sh [--plan]` pulls the image of `main`'s newest commit (it refuses while that image
  is not built), starts AWS Step Functions Local and one worker from the image, runs readiness, then every lane of the load jobs
  file at once and the finish. `load.sh [--plan] [--finish] <step>...` runs only those steps, in order. It waits and exits 0
  only on success. A load runs no plan: its first state is readiness, which refuses a load that cannot start. `--plan` is for a
  changed pipeline or a doubt about one step, never a standing step before a load (it repeats readiness). `--force` (never with `--plan`) is force
  publish for every load of the run; `LOAD_DEADLINE_HOURS` is the operator's window (default 2): a miss is reported once, never a stop.
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
- **A finish build that fails fails the load.** The state file then has `finish stopped: links rc=<n>` (or `lookups`) and no
  `chain done`, and the execution fails. The build's own log is `chain-<RUN>-links.log` (or `-lookups.log`). Once it is fixed,
  start `load.sh` again: done steps cost one call each, then the finish runs.
- **The catalog takes no part in a load.** Readiness has no catalog check, a finished step publishes nothing to it, and its server
  (OpenMetadata) stays stopped during a load: it holds memory the lanes need. Publish its text after a change under `rules/` and its
  step statuses after the load (`--catalog-status`), each on its own.
- **Force publish is a whole-run act with one time.** `load.sh --force` (never with `--plan`) gives every load job of the run
  `--force`, and the engine names a forced run by its time: `load_jobs.py` takes that time once, so an attempt stopped at its
  `minutes` bound carries on in the same run instead of starting another. Each job publishes its own revision (the time's digits, then its
  place in the file): a source's quarters carrying one revision stopped the second with "contradictory publications". Use a new `RUN`, say the estimate against the 2-hour window before
  starting.
- **Read hosted pipeline status inside its worker container.** Use
  `docker exec <worker> python /app/skills/data-operations/scripts/load_jobs.py --status --json --run <RUN>`; a host status cannot see worker processes. Use
  `docker exec <worker> ps` and `/proc/<pid>/io` for process details (bytes read and written between readings show work before the step log fills).
- **Lanes and workers follow the container's free memory, never a number fixed before the load.** Every lane starts (the state machine
  takes no computed value, and a lane queued in the worker times out on its heartbeat). Each step is admitted just before its load
  starts, after its waits (`admit` in `load_jobs.py`), and never while the CPU is pressed (the controller's own reading, which would
  take the workers back): one step at a time, the lock held through a settle window so the next reads the
  memory this one takes (a step that waits holds it only to read, so a step that fits starts meanwhile, and nothing is raised
  while one waits; a large step, such as one of one document, can so wait while other lanes keep starting steps, until the memory
  of all it asks is free or no other load runs), it waits until the container's free memory (cgroup limit less use, the file cache counted free) covers half
  its declared workers at their `worker_gb`, then starts with as many as fit, up to its declared workers. With no other load running
  it starts at that half whatever the memory, so a load never waits for ever. A step whose delivery is one document
  (`one_document: true` in the load jobs file) waits for all its workers instead of half, since a move would abandon it: the
  controller never moves it. A step with a measured `peak_gb`
  (a load's `done` and `stopped` lines end with the `sampled peak` its processes were seen to hold, read every 10 s; resident
  memory counts a shared page once a process, so it can be more than they take together: declare it from there) waits for at least that much, and while it runs the memory it has yet to reach of its peak is not free to the steps admitted
  after it. A container with no limit to read gives every step its
  declared workers. The step's log names the workers it got. If lanes wait while CPU idles, memory is the limit: more lanes need
  more of it (a larger container-runtime ceiling or compute). The gate exists because lanes started at once, each with its declared
  workers, overload the CPU and the heaviest merges are killed for memory (status -9).
- **The lane controller moves the running steps' workers.** A thread of the activity worker (`control` in `load_jobs.py`) looks every 30
  seconds and moves at most one step, by the rules of the `--auto` scheduler (`choose_move`): with room it doubles the step with the
  longest chain behind it, pressed for four cycles it halves the one with the shortest. Room is two worker shares (`WORKER_GB`) of free memory, CPU load
  under three quarters of the cores and database connections below the target; pressed is under one share of memory, CPU load over
  one and a half times the cores, or sessions waiting on locks. A raise stays within the memory that is free with one share left
  over, waits ten minutes after the step's last start, comes just after a bundle completes, and is repeated only when the last one
  raised the measured rate. Nothing is raised while a step is being admitted. A move writes `<state>.move-<step>` with the count and
  ends the step's load (driver first, then the workers it started); the step's loop starts the load again in the same attempt,
  through the same admission. The state file says `controller moves <step> from N to M workers`. The ended load's log is
  kept as `chain-<RUN>-<step>.log.attempt-<n>.move-<m>`, and the step's `done:` line counts the whole attempt: each bundle as
  its first report in the attempt says, ending `over K processes (moved)`. A shed, like a raise, comes just
  after a bundle completes, so a move abandons next to nothing; a pressed machine whose running steps are all mid-bundle sheds
  nothing until one of them completes a bundle. A step of one bundle, one declared `one_document`, or one shed earlier
  in its attempt is never moved: a move abandons its run in flight, and a step shed, raised and shed again loses run after run.
- **The store bounds the load, not only its compute.** Every step's worker holds a session on the one database, and one sort or
  hash of a session may take `work_mem`: the load jobs file's `stores:` entry the load names (`LOAD_STORE`; both pipelines
  name `hosted`, the instance's cores, memory and `work_mem`) carries four workers to a core and half its memory in `work_mem`
  shares, across every running step. A step waits until the store carries its floor and starts with no more than it has left
  (`waits for the store`); the controller and the local scheduler raise nothing into a full store and shed from one held past
  it; the lane budget names `store` when it is the limit. Every lane still starts and queues at admission. A large compute
  with an idle CPU is no sign of room: the database is where the load runs out. A resize of the instance is a changed line. The
  refusal `the database server ran short of a resource (53200: memory ...)` is the store full; read the instance's server log
  and metrics (`database-monitoring`: `logs`, `telemetry`) for what took the memory.
- **One task per poller.** The worker's `ps` sees only its container, so QUIET's process count no longer covers the Mac; the
  loader's database sessions still do. Never start `load_jobs.py` on the Mac beside it.
- **Mounts:** the logins and the captures are read-only; the stores folder, `LOGS` and the run documents' folder
  (`BOOKKEEPING_MANIFEST_ROOT` in `worker.env`, read by `load.sh`) are written (the readiness record, the run's state, each run's
  frozen rules and input manifests; a folder the worker does not mount reads as a missing file, and a run driven again stops). Host networking lets the worker reach the stores and the catalog as the Mac does.

## Balancing a load: one worker limit, three skills

The load is balanced by one number, the worker limit: the workers every lane together may hold, set by the store
(`stores:` in the load jobs file) or by the compute, whichever carries fewer (`worker_budget`, its `limit` naming which).
Three skills keep it right, each with one duty, in this loop:

| Step | Skill | What it does |
|---|---|---|
| Set and hold the limit | data-operations | The `stores:` line; admission (`waits for the store`), the controller's raises and sheds inside it |
| Show it working | [load-monitoring](../load-monitoring/SKILL.md) | Grafana's "Workers running" against "Worker limit", the store's rows a minute; the state file's `store <name>:` line every ten minutes |
| Read what the task cannot | [database-monitoring](../database-monitoring/SKILL.md) | The database's CPU, memory and server log (`telemetry`, `memory`, `logs`): the one place an out-of-memory or a saturated core shows |
| Change the limit | data-operations | From those readings only, a changed `stores:` line on its own branch: never from the compute's idle CPU |

The verdicts, each from readings at the limit (every worker in use, steps waiting): database CPU saturated and rows a minute
flat is the right limit; CPU to spare is a limit to raise; an out-of-memory line or lock waiters climbing is a limit to lower,
or an instance to resize (the operator's approval; [HOSTED-MIRRORING](../data-platform/HOSTED-MIRRORING.md), "Readiness before
changes"). A resize is followed by a changed `stores:` line in the same change.

**The store counts what a step uses, not what it declares.** Each controller cycle reads every step's sessions at work (active
or in a transaction, `application_name` `chain-<step>`) and keeps its peak in its current start beside the state file
(`<state>.sessions`); a peak counts only for the start it was read in. Admitting a step and raising one charge a running step
that peak once read twice; shedding charges it once read once, so it acts on the sessions the store holds. Until then, or when
the database cannot be read, a step is charged its declared `--workers`. A step's `workers` is so a cap and a first guess, never the measure: a step reading one file on one core
holds no store workers. A step of one document (never moved) waits for one free store worker, not all of its own, and starts
with all of them; when its sessions take the store over the limit, the controller sheds the movable steps, never it. The store's half of memory
kept spare (`stores:`) covers the cycle between a step opening sessions and the next reading.

## The shortest time to load everything
The goal is every document loaded in the least wall-clock time. Each rule below removed a wait or a restart.
- **The longest chain of steps sets the time, so every lane starts at once.** The lane count is the workers the compute carries over the
  widest first step's workers: more lanes than that were killed by memory and cost a rerun.
- **Nothing runs beside a load that it does not need.** The catalog (OpenMetadata) takes no part in a load: no readiness check, no
  per-step publish, and its stack stays stopped, because its memory starves the container runtime. A plan or smoke run before a
  load repeats readiness and is skipped.
- **A container runtime that stops answering freezes the worker and its load.** Test it every two minutes with a bounded
  `docker version` while a load runs, and restart the runtime the moment it stops answering: waiting on a hung engine costs more
  than any step, and a restart loses only the step in flight (done steps cost one call each). Check the VM's memory ceiling against
  what runs in it, and turn off pausing the VM on sleep. A slow image pull is rarely the cause: pull the image ahead (it takes seconds
  once the runtime is healthy).
- **Mount every folder a run's documents live in.** A run driven again reads its frozen rules and input manifests from the manifest
  root; unmounted, the file is missing and the engine says "Corrupt control document". On that message, check the mounts first.
- **A forced or killed load leaves unfinished runs, and the next default load drives them first.** They need the same mounts.
- **One load at a time is Step Functions' own record** (`load.sh` refuses while an execution is running) and no lock file: a lock a dead run left
  refused the next start. A dead run's wrapper that is still alive keeps waiting on the old execution: stop it before starting again.
- **Restart a forced load with `load.sh --force --in-lanes <the steps left>`.** A forced load ignores the Change Journal, so a start that
  names no step repeats every job in full (one job alone took a quarter of an hour), and named steps without `--in-lanes` run one at a time.
  `--in-lanes` runs only the named steps, each in its lane, the lanes at once; the steps already done are named by no one.
- **Restart the runtime with `orbctl stop`, then `orbctl start`** (`orbctl restart` restarts Linux machines, not the Docker engine). A
  restart clears the emulator's executions: start the load again with the same run label, and its done steps cost one call each.
- **A forced load reprocesses every document of every job**, so its time is the whole of the lanes, not the changed part: start it
  only when the operator names it, plan its window from the last forced run's longest chain, and give each forced load its own run label.

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
- **A mastering step's progress is read from MDM, since the engine logs its count only when the run ends.** As the worker login
  (`worker.env`; `ops_reader` sees statistics, never MDM's rows), in a read-only transaction with a statement timeout, schema `mdm`:
  `mastering_delivery` gives the pieces finished and their `records` and `deferred` per `source_code`; `mastering_record` the records
  stored, `mastering_deferred` those held for a later pass. Records plus deferred against the file's `record_count` (the step log's
  `publication`) is the share done. Rows written a minute is no measure of it: one record writes several rows.
- **A scheduler that "stopped" has usually finished everything it could**: it names the failed steps and what waits on them.
  Fix the cause (engine, memory, a login), then start it again; done steps cost one call each.
- **`mdm build-lookups` and `mdm clear` refuse while Bookkeeping holds a running run of a mastering target** (a worker between two merge transactions holds no
  lock, so the store's own check cannot see it). A run left open by a stopped attempt blocks them until it is finished: resume it, never skip the check.
- **Read how often a mastering merge went alone after a load**: `grep mastering_merge_alone <the step logs>`. A line names each reason and its
  count; no line in any step log means no part merged alone, and the kind lock was shared throughout. Lock waits are read the same
  way as every wait: sample `pg_stat_activity` and `pg_locks` (wait event and lock type) as the diagnostic login, and say each wait's share.

- **A silver step that looks stalled or locked may be uploading.** PostgreSQL shows a session `idle in transaction` (`ClientRead`) until a
  statement's last byte arrives, and the client meanwhile sits in `ppoll` with little CPU. Read the writer's timeline before blaming a lock or the
  database: sample its sessions every half second (connection, transaction, statement start and last change) and compare the store's time per
  statement with the gap before the next one.
  - Problem: a silver-only step (no mastering, one document) runs for hours, shown stalled or locked, its session idle in a transaction nearly always.
  - Root cause: each insert is quick on the store, and the next batch, sent as SQL text, waits on the upload from the loading machine. The step lands
    one document's deliveries one after another over one connection, and a rerun uploads every row again for the store to discard those already landed.
  - Fix, the direction: send fewer bytes (no row a rerun already landed; a denser format than SQL text), send them side by side up to the line's
    rate, and run the loader beside the store.
  - Lesson: measure both ends (the store's statement times and the client's gaps, and the upload rate on one connection and on several) before adding
    workers or connections: the connection limit is not the limit, the upload is.
- **A step stopped at its deadline leaves no worker running.** A command's merge workers are processes of their own, and one left running merges
  beside the next attempt: both write the same file, and every retry stops on `UniqueViolation` on `mastering_file_pkey`. Each platform command runs
  in its own process group, and a deadline or an interrupt stops the group. After any stopped step, look for workers whose parent is gone
  (`ps -eo pid,ppid,etime,args` in the worker container, parent 1) before starting the step again.

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
table rebuilt from rows already in the database is one join pass that writes only what changed. A build that holds every record whole needs many times
the text of its records and is killed by the container (status -9, an empty log): keep of each record what the result reads, spool the rest to disk and calculate in
parts that share no result. Measure the process's footprint, not its resident size, which stays low while the machine swaps. Time the phases before choosing a build: an incremental
build would not have shortened the first finish after a full load. A phase that moves a table between two schemas of one database through the client is the same defect: the binding
rebuild read 4.4 million rows into Python and wrote them back (18 of the finish's 30 minutes) until it became one statement. Count a landing's round trips
a batch before changing its size: the writer made three a batch (70 ms each) and now makes one.

## Stopping loads
- Stop the scheduler first (it would start the next step), then its step processes. The state file keeps every done step.
- Aborting the Step Functions execution does not stop work already handed to the worker: the lane process
  (`load_jobs.py`), the engine process of the running step and its pool workers keep running. After the abort, list
  the worker container's processes, end the lane process and the engine process (`kill -9` when `TERM` is ignored),
  and check the list is empty apart from the activity worker and exporter. Stop the watchers too. A step stopped
  mid-bundle redoes that bundle on restart; keep the run's bundle folders, since the restart resumes from them.
- Before a hosted table reset, stop clients that can reconnect and read the active run's status inside its worker container
  (see "While a load runs"). Independently inspect Bookkeeping with `edgar-warehouse bookkeeping runs --state running`,
  `--state waiting` and `--state blocked`; for each returned run, read `bookkeeping status <run-id>` and
  `bookkeeping leases <run-id>`. A container status with no active steps does not establish that Bookkeeping has no open runs
  or leases. Let the default `load.sh` pipeline finish retained load runs; use Bookkeeping recovery only when that pipeline
  cannot resolve one. Never call
  `bookkeeping finalize` to bypass the loader, edit run state or delete leases by hand. Stop if any run or lease remains
  unresolved. The table-reset command checks for blocking sessions before and after taking
  exclusive locks. It allows managed `pg base extension worker` sessions only
  when PostgreSQL reports no session state and no open transaction. Client
  sessions, WAL senders and any other backends on the selected database block
  the reset. Leave internal workers under Snowflake management.
- **A hosted table reset keeps the databases, schemas, roles and source extracts.** Inventory one store with
  `uv run python infra/scripts/reset-hosted-tables.py --store <store> --inventory`; the listed row counts are catalog
  estimates. Put the approved table names and their `drop` or `truncate` actions in one explicit manifest for that
  store, then run the same command with `--manifest <file>` to read exact scope, actions, row estimates and the plan
  digest. The manifest must contain only tables that the platform can rebuild or reload. Check the managed-mirror
  record before dropping a mirrored table; any mirror lifecycle or membership change has its own approval.
- Apply only the reviewed plan:
  `uv run python infra/scripts/reset-hosted-tables.py --store <store> --manifest <file> --apply --words "<the operator's exact words>" --plan-sha256 <reviewed digest>`.
  The script locks and changes only listed ordinary tables, in one store transaction. `DROP TABLE` has no `CASCADE`;
  `TRUNCATE TABLE` has no `CASCADE`. A dependency, session, stale digest or database refusal rolls the transaction
  back. It records the approval and result in the private stores folder. Each store is a separate transaction, so stop
  after any failure and reconcile the completed receipts before continuing. Run the affected store's normal
  `init`/table-deployment command after a drop; truncation retains the schema. Keep the captured extracts for reload.

### Clear all MDM and Silver tables for a full reload

The clear, in order (the mirror commands are the data-platform skill's `scripts/exposure/mirror_sql.py` and `mirror_run.py`):

1. `mirror_sql.py status | mirror_run.py`: the mirror lists (the warehouse answers); the gate's QUIET check passes (no load runs, the
   loader has no session).
2. Back up the control database and RDM (below); plan each store's manifest and keep its digest.
3. `mirror_sql.py suspend | mirror_run.py`, then `status` reads `SUSPENDED`.
4. Apply each store's plan with `--with-suspended-mirror`: a suspended mirror keeps its walsender and a managed worker
   connected, and the reset lets those two stay; any other session refuses it, named. Stop at the first store that fails.
5. Restore RDM's published codes (`rdm_restore_published.py`), then restart the mirror (`mirror_sql.py restart | mirror_run.py`, a new snapshot
   of the emptied tables) and read it back (HOSTED-MIRRORING, "Done is read back").

Prepare a separate manifest for each store. List every resettable table from its
inventory with `action: truncate`. Use `--require-all-tables` when planning
and applying each manifest. The script checks the complete inventory during
planning and again under the reset locks, and verifies all selected tables are
empty before commit. Preserve `mdm.migration` and `silver.table_spec`:
they record the installed migration and registered specifications that
initialization checks. The script rejects either table in a reset manifest.
Recover missing metadata from a verified backup or evidence of the installed
schema and specifications. Keep RDM reference data and Rules configuration for this
reload. A full hosted data-store clear may also reset RDM when named in scope; verify its published sources and restore
them with `rdm_restore_published.py` before readiness or mirror creation. Rules configuration remains in config and is never
reset. Run the hosted initialization and readiness checks before loading.

### Recover missing deployment metadata

Restore metadata from a verified backup when available. For Silver, the
registration command writes the spec SHA-256 in each physical table's
comment. If the registry is empty, compare the full deployed table inventory
and its comment hashes with the configured specs. Restore registry entries
only when the inventories and hashes agree, then verify every restored entry
through Silver's spec check.

For MDM, the migration checksum records what was installed. Verify the
installed schema against deployment evidence before restoring a missing
record. A checksum calculated from a checkout alone is insufficient proof.
If the operator explicitly overrides that verification, record the override
and checksum, take the migration locks for the repair, and run `mdm init`.
A successful init after an override confirms the initializer accepted the
record. Run hosted readiness before loading.

### Rules configuration is never reset

The Rules store lives in the config database, which no reset names: `reset-hosted-databases.py` drops the data and
control databases only, and `reset-hosted-tables.py` offers no `rules` store. It holds configuration a reload needs
(dataset readings and policies). Change Rules only through its configuration deployment or a separately requested Rules
migration.

### Resetting the control stores

A reset that includes Bookkeeping and Change Journal needs a backup of both
stores and a verified way to rebuild the intended state. Bookkeeping retains
run and checkpoint evidence. Change Journal retains publication receipts used
to decide what to replay. Check the reload scope against retained captures
before clearing either store. A run at run grain has no work items or leases,
so zero leases does not establish that its run has finished. Record the run
state separately and follow the recovery procedure for unresolved runs.

Back up the control database whole and the RDM store by schema: `pg_dump` of
the whole data database also carries MDM and Silver, which a reset does not
restore from git. A dump of one schema is `pg_dump --schema=rdm`; list the
dump with `pg_restore --list` and read it before the clear.

### A reset leaves the run's state file naming the old generation

A table reset empties the store without making its database again, so the
database's generation is unchanged and the run's state file still reads as this
store's: the gate's STATE check says `same` and passes, while the file's `done`
lines name steps whose records are gone. Set the file aside (rename it; never
delete it) before the next load starts. A load that runs every step ignores the
earlier `done` lines, but a load that names steps in lanes counts an earlier
load's `done` lines for the steps it does not run, and after a reset those
steps' records do not exist. `fresh` is the verdict a cleared store wants.

### Truncate an append-only table

Use the same manifest workflow for a table with a retention trigger. Before
applying, verify a readable backup and confirm the plan names the exact trigger
it will pause. The script checks the trigger and its function in PostgreSQL,
locks the table, disables that trigger, truncates the table and restores the
trigger in one transaction. It checks that the table is empty and the trigger
is enabled before committing. A missing, changed or disabled expected trigger
stops the plan. Other triggers remain enabled.

The reset script recognizes `no_truncate_version` on `rdm.code_set_version`
and `immutable_event` on `journal.event`. Back up RDM history and verify the
source for restoring reference codes before applying the RDM plan.

### Example: table reset manifest

This invented example truncates one table while preserving its schema. A real manifest must list the exact tables chosen
for the reset and must be reviewed before `--apply`:

```yaml
version: 1
store: mdm
tables:
  - schema: mdm
    table: example_table
    action: truncate
```

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
