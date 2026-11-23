# Hosted loads: what stops them, and how to resume

Read before starting or resuming a load on the hosted instance. Each item is a cause met on a real load and its rule.

## The gate: nothing loads until the infrastructure is ready and tested
`scripts/readiness.py` reads thirteen facts and writes `readiness.json` in the stores folder only on a full pass; `load_chain.py`
refuses to start, resume or finish a load without it (the read-only `--plan`, `--list`, `--status` and `--catalog-status` still
run). A pass belongs to one store generation (a reset of the databases closes the gate), one commit (any new commit closes it)
and one day. The checks: the code is committed, contains `main` and its commit has green CI (tested means CI, never a local run
alone); the compiled engine was built from this checkout's source (`readiness.py --build-engine` rebuilds it and records a hash of what it was built from); `doctor` is ready; the loader holds its connection limit, memory ceiling
and timeouts; RDM holds its codes and silver a table per spec; every step has a capture; no load runs and the loader has no
session; disk and load average have room; the access audit of the database has no failing control; every duty file's login connects to the databases of its duty (names only, a
driver's text is never kept); the chain's state file is this store's, or is shown as one that will be set aside, with its count of done
steps; the catalog, when one is configured, matches the rules; and the merge policy, every Dataset Contract and every worker profile are registered and granted (init steps 5 to 7). The gate is not the init runbook: after a reset, walk every runbook step,
say in the report which ran and which did not, and never write a step off without reading why (a catalog step was once called
unconfigured when its file existed). A fact that cannot be
read is a failure. Fix what it names and run it again; there is no switch to skip it. A rehearsal of the first lane on a
disposable store is the next check to add.

## Before a load starts
- **Role guards first.** `infra/scripts/harden-hosted-roles.py --confirm` (owner login) gives every login a connection limit,
  statement and idle-transaction timeouts, a `work_mem` ceiling for the loader and the audit classes. A load with the
  instance's default `work_mem` (hundreds of MB per sort or hash step and session) ran the server out of memory with ten
  merge workers. The access-audit skill tests these guards.
- **The engine must match the code.** A Rust change reaches a load only after the engine is rebuilt into the environment that
  runs it: `readiness.py --build-engine`. A step that fails with a missing method or an unknown normalizer on today's `main` is
  a stale engine, not a data fault: rebuild, then run the gate again.
- **A chain that ends at once after a reset has read a stale state file.** The state file's `chain store` line names the store and
  the database's generation; a line with no generation comes from before generations were recorded and cannot show the store was not
  made again, so it is set aside (kept, renamed). A chain that ran no step and printed `chain done` is the sign: look at the file's
  marker, set a file with an old marker aside, and start again. Done steps cost one call each, so setting a file aside loses little.
- **`EDGAR_WAREHOUSE` names the executable** (`.venv/bin/edgar-warehouse`), never its folder: a folder fails with
  "Permission denied" on every step.

## While a load runs
- **One scheduler per run label.** A second `load_chain.py --auto` on the same label doubles every step. Look for a running
  scheduler (`ps`) before starting one, and stop the scheduler before its steps.
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
- **A scheduler that "stopped" has usually finished everything it could**: it names the failed steps and what waits on them.
  Fix the cause (engine, memory, a login), then start it again; done steps cost one call each.

## The finish takes at most five minutes
On a fresh store every master id is empty, so the first finish is the full-size one: the links build reads every master, and the refresh of the
largest silver table reads and writes every one of its rows. A finish that takes minutes more than five is the measure of the slowest phase
still left (time each phase, below), never a reason to skip it: Gold and the links read what it writes.
`--finish` builds the links table once and fills each silver table's empty master ids. It is bounded by the operator at five minutes, and
a longer one is a defect, not a wait. `silver refresh-ids` reads and writes only rows whose id is empty: a row that has an id is never read
or written again (an id whose master merged away still resolves to the survivor through `mastering.reads.master`). A refresh that looks up
every key of every row, in batches, costs about one random disk read a row on the master store. Time each part of a slow finish by phase
before changing it, and run the cheap check that can fail first. For a step that is one native call, sample the running process
(`sample <pid> 30`) before reading its code: the links build spent 265 s in a pairwise comparison of every link with every later link,
which no phase timing could name.

## Stopping loads
- Stop the scheduler first (it would start the next step), then its step processes. The state file keeps every done step.
- A hosted reset uses the full quiesce and drain procedure in the
  [initialize runbook](../../docs/runbooks/edgar-intelligence/init.md#initialize-a-hosted-store): stop clients that can
  reconnect, confirm no open Bookkeeping runs or leases, resolve managed mirrors under their own approval, restart the
  PostgreSQL service, wait for `READY`, and rerun the read-only reset preflight. An empty load-chain status alone does
  not prove that the databases have no sessions. If Snowflake-managed `pg_lake` sessions remain or return, stop; never
  terminate those sessions or bypass the reset script's guard.
- The reset script (`reset-hosted-databases.py --words "<the operator's words>"`, which records them) also requires the
  operator's sign-off and refuses while any session is connected. After the reset, expect the previous run's done steps
  to be set aside as another store's state. It deletes the dropped stores' run files (`<manifest root>/load`) and keeps
  the extracts.

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
