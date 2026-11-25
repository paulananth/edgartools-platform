# Hosted loads: what stops them, and how to resume

Read before starting or resuming a load on the hosted instance. Each item is a cause met on a real load and its rule.

## Prepare a fresh worktree for the local operations
Before running a hosted-store operation script from a fresh worktree, install the project's runtime dependencies with
`uv sync --extra s3 --extra mdm-runtime`. `uv run` alone may create `.venv` without installing SQLAlchemy and the
other MDM dependencies, so a preflight can fail before it reaches the store. Run project Python commands with `uv run`;
source the private hosted environment file in the same shell without printing its values. This prepares local tooling;
the hosted load itself still runs from the CI-built loader image below.

## The gate: nothing loads until the infrastructure is ready and tested
`scripts/readiness.py` checks hosted readiness and writes `readiness.json` in the stores folder only on a full pass; `load_jobs.py`
refuses to start, resume or finish a load without it (the read-only `--plan`, `--list`, `--status` and `--catalog-status` still
run). A pass belongs to one store generation (a reset of the databases closes the gate), one commit (any new commit closes it)
and one day. Each check reads only what it asks (a capture is its folder's receipts file), never a plan of
the work. The checks: the code is committed and contains `main`;
`doctor` is ready; the loader holds its connection limit, memory ceiling
and timeouts; RDM holds its codes and silver a table per spec; every step has a capture; no load runs and the loader has no
session; disk and load average have room; the access audit of the database has no failing control; every duty file's login connects to the databases of its duty (names only, a
driver's text is never kept); the run's state file is this store's, or is shown as one that will be set aside, with its count of done
steps; and the merge policy, every Dataset Contract and every worker profile are registered and granted (init steps 5 to 7). The gate is not the init runbook: after a reset, walk every runbook step,
say in the report which ran and which did not, and never write a step off without reading why (a catalog step was once called
unconfigured when its file existed). A fact that cannot be
read is a failure. Fix what it names and run it again; there is no switch to skip it. A rehearsal of the first lane on a
disposable store is the next check to add.

## Where a load runs
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
- **The catalog takes no part in a load.** Readiness has no catalog check, a finished step publishes nothing to it, and its server
  (OpenMetadata) stays stopped during a load: it holds memory the lanes need. Publish its text after a change under `rules/` and its
  step statuses after the load (`--catalog-status`), each on its own.
- **Force publish is a whole-run act with one time.** `load.sh --force` (never with `--plan`) gives every load job of the run
  `--force`, and the engine names a forced run by its time: `load_jobs.py` takes that time once, so an attempt stopped at its
  `minutes` bound carries on in the same run instead of starting another. Each job publishes its own revision (the time's digits, then its
  place in the file): a source's quarters carrying one revision stopped the second with "contradictory publications". Use a new `RUN`, say the estimate against the 2-hour window before
  starting.
- **Read a load in the container, not on the host.** The load runs in the worker, so a host `ps` shows nothing of it: use
  `docker exec <worker> ps`, the worker's `/proc/<pid>/io` (bytes read and written between two readings show a step that
  works while its log is still empty), and the run's state file. The step's own log fills only when an attempt ends.
- **One budget: the workers a compute carries over a job's workers, in no platform's terms.** A job's size is its `workers` (the load
  jobs file) and how many lanes run at once is the workers the compute carries (`--capacity`: `local`, this machine, or a profile of the
  file such as `aws-large`; its memory in worker-sized shares, at most four to a vCPU, the range a job's workers follow) over the
  widest first job of a lane (`load_jobs.py --lanes-at-once`; `lane_budget` adds what limits it, memory or vcpu, for the load monitor,
  which shows lanes and workers running against the same numbers). If lanes wait while CPU idles, memory is the limit: more lanes need
  more of it (a larger container-runtime ceiling or compute), never a larger number in the state machine. The number lives in the loader; whatever starts the lanes only
  applies it: `load.sh` sets it as the state machine's lanes `MaxConcurrency` (`CAPACITY=<profile>` for another compute), the
  local scheduler (`--auto`) uses the same capacity, and the rest of the lanes queue. Two knobs for one limit is waste, and the state machine takes
  no computed value (`MaxConcurrencyPath` is refused by the emulator), while a lane queued in the worker times out on its
  heartbeat. Without it every lane starts at once: on 8 cores the first jobs asked for 26 workers, the load average passed 20
  and the heaviest merges were killed (status -9).
- **One task per poller.** The worker's `ps` sees only its container, so QUIET's process count no longer covers the Mac; the
  loader's database sessions still do. Never start `load_jobs.py` on the Mac beside it.
- **Mounts:** the logins and the captures are read-only; the stores folder, `LOGS` and the run documents' folder
  (`BOOKKEEPING_MANIFEST_ROOT` in `worker.env`, read by `load.sh`) are written (the readiness record, the run's state, each run's
  frozen rules and input manifests; a folder the worker does not mount reads as a missing file, and a run driven again stops). Host networking lets the worker reach the stores and the catalog as the Mac does.

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
- Aborting the Step Functions execution does not stop work already handed to the worker: the lane process
  (`load_jobs.py`), the engine process of the running step and its pool workers keep running. After the abort, list
  the worker container's processes, end the lane process and the engine process (`kill -9` when `TERM` is ignored),
  and check the list is empty apart from the activity worker and exporter. Stop the watchers too. A step stopped
  mid-bundle redoes that bundle on restart; keep the run's bundle folders, since the restart resumes from them.
- Before a hosted table reset, stop clients that can reconnect and check `load_jobs.py --status`. Independently inspect
  Bookkeeping with `edgar-warehouse bookkeeping runs --state running`, `--state waiting` and `--state blocked`; for each
  returned run, read `bookkeeping status <run-id>` and `bookkeeping leases <run-id>`. A load-jobs status with no active
  steps does not establish that Bookkeeping has no open runs or leases. Let the default `load.sh` pipeline finish
  retained load runs; use the Bookkeeping recovery procedure only when that pipeline cannot resolve one. Never call
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

Prepare a separate manifest for each store. List every resettable table from its
inventory with `action: truncate`. Use `--require-all-tables` when planning
and applying each manifest. The script checks the complete inventory during
planning and again under the reset locks, and verifies all selected tables are
empty before commit. Preserve `mdm.migration` and `silver.table_spec`:
they record the installed migration and registered specifications that
initialization checks. The script rejects either table in a reset manifest.
Recover missing metadata from a verified backup or evidence of the installed
schema and specifications. Keep RDM reference data and Rules configuration for this
reload. Run the hosted initialization and readiness checks before loading.

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

### Preserve Rules configuration

Keep the Rules store out of hosted data reset manifests. It holds configuration
needed for reload, including dataset readings and policies. A request to clear
all hosted data tables does not include the Rules store. Change Rules only
through its configuration deployment or a separately requested Rules migration.

### Resetting the control stores

A reset that includes Bookkeeping and Change Journal needs a backup of both
stores and a verified way to rebuild the intended state. Bookkeeping retains
run and checkpoint evidence. Change Journal retains publication receipts used
to decide what to replay. Check the reload scope against retained captures
before clearing either store. A run at run grain has no work items or leases,
so zero leases does not establish that its run has finished. Record the run
state separately and follow the recovery procedure for unresolved runs.

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
