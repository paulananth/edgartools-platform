# Edgar Intelligence runbook: daily run

Operating a loaded store: a delivery's arrival, file and rule changes, sizing, progress, failure and recovery, and testing a source. The order loads run in, and what a load needs beside its capture, are in [initialize](init.md#dependencies-between-loads). Index: [README](README.md).

## Delivery availability

AWS acquisition or Step Functions supplies the files and completion evidence.
Local operations verifies the handoff; it does not download or trigger acquisition.
Bind the source/feed, delivery/publication, complete expected inventory, producer
completion evidence, observed time and content receipts. Verify the required
files exist and match those receipts before accepting a ready handoff. Keep the
verified evidence references fixed for a run and resume. Published time, observed
time and local file modification time describe different facts.

| Observation | Decision |
| --- | --- |
| Expected delivery is absent, incomplete or still downloading | Record unavailable/partial with missing counts; defer this source and its genuine dependants. Independent ready work proceeds. |
| File exists but success evidence or expected inventory is missing | Readiness is unproven. Inspect genuine retained evidence; report the missing contract if it cannot express completion. |
| Required file differs from its receipt | Block affected work and preserve the mismatch. Recover the original bytes/evidence through the existing owner or create a newly qualified delivery. |
| Approved upstream input can be produced from a ready local delivery | Run the declared local dependency through its supported path, verify it, then freeze the consumer's resulting references. |
| Relationship endpoint has not arrived | Retain the unresolved relationship with evidence; process independent facts when their required inputs are ready. |
| A run already owns this work | Resume or observe that run under its original pins. Respect current leases; do not start competing work. |

## File and rule changes

Inventory every delivery, including unchanged files. Match stable source-defined
delivery/member identities where those contracts exist; keep physical names and
hashes as separate evidence. Compare schema/profile evidence when a delivery's
shape may differ. Do not infer business identity or deletion from filenames.

The current file selector uses **source + file key + content hash + processing
identity**. A content hash alone is not its deduplication key.

| Observation | Decision |
| --- | --- |
| Same key, bytes and processing identity, verified processing receipt exists | Count it as already processed. If every file is covered, report a no-op without an empty mastering run. |
| Same key, changed bytes | Select it through normal Journal filtering; keep source publication/revision semantics. A new file timestamp alone is not a new revision. |
| New name/key, same bytes | Flag a suspected rename after checking source/member identity and ambiguity. Under today's selector the new key remains eligible. Process normally unless an implemented, tested alias contract proves reuse; never forge an old key or processed receipt to skip it. |
| New name/key, changed bytes | Treat as newly selected input; use actual contract evidence to decide revision or replacement, not name similarity. |
| File vanished from a later inventory | Record the coverage difference. Apply retirement only when the source contract supplies authoritative complete-scope/deletion semantics. |
| Rule, policy, RDM or relevant shared input changed | Determine affected processing identity and coverage. Reuse matching evidence; route actual changes through the normal rule lifecycle. Preserve older running pins. Missing dependency-invalidation support is a runtime gap. |
| Columns, keys, types or meaning drifted | Profile the difference and route to onboarding/refining-rules/data-quality as appropriate. Hold affected processing rather than silently repairing its mapping. |

Normal runs leave forced replay off. The selector is per file; reprocessing a
changed multi-record file does not imply every row became a new identity.

**Prove an unchanged rerun.** Count the rows of every table of every store (MDM, Bookkeeping, Change Journal, silver,
RDM, Rules) and the highest golden record change number, run the same chain again with its own log folder (the chain's
state file is read for `waits_for`, so copy it there), and count again. Every step should print `0 documents loaded`,
and no table should change. Read a difference by what wrote it: a Bookkeeping run and its unit rows mean a step loaded
files, so find why the Journal did not skip them. Counts show inserts and deletes only, not an update to a stored
row, so the change number covers golden records. Do not include `--finish`: it rebuilds lookups on purpose.

## Resource sizing

Size at the execution boundary: a Mac host's CPU/RAM does not describe a
container's allocation, and server connection limits do not describe its free
budget. Read available resources and active runs before each new dispatch.

Read the machine before adding a load: a load average above one and a half times the cores, or swap over three
quarters used, means every running load slows (`load_chain.py --auto` checks both before each start). Memory is the
limit on a small machine, not the cores.

Record the ready backlog's file count and compressed/expanded byte estimates,
measured peak memory per unit, worker throughput, temporary/output
disk needs, connection consumption and other agents' reservations/current work.
Use source/stage measurements from comparable verified runs; distinguish a
measurement, estimate and unknown. Existing qualified early-unit measurements
may refine the estimate; an invented speedup or unqualified sample is not proof.

Choose concurrency no larger than the tightest CPU, usable-memory,
database-connection and declared-worker budget, including verification and
parallelism inside each worker. Choose bundle sizes within the existing supported
contract bounds. Keep headroom based on observed pressure and shared use. When
measurements are unavailable but one unit can safely fit, begin with 2 workers
and conservative bundles, then scale a long load to 8. If even one unit cannot fit or fit is
unknown, wait/report the missing estimate; do not force it or reject the source.

A slow bundle on a hosted store is waiting on a lock, paying round trips (tens of milliseconds a statement) or computing.
Find which before adding parallelism, in this order: sample the sessions (who waits on a lock, and how old the holder's
transaction is); time one batch alone in a transaction rolled back; count one bundle's statements on a disposable local
store with statement logging (`log_statement = 'all'`, the log streamed to a file while the load runs, since Docker keeps only its last few log files; `<data-operations skill>/scripts/count_statements.py --log` groups them by shape and by database). At `unit` grain most of a bundle's statements are Bookkeeping's (a claim, status
read and report for each unit); a target at `grain: run` pays none of them ([bookkeeping](../../../skills/bookkeeping/SKILL.md#grain-how-much-bookkeeping-a-target-uses)).

`--workers` is the processes on each step, at either grain. A step's units run that many at once; a step with fewer
units than workers hands each unit its share, and a merge deals its batches out to that share (a one-file
publication merges on all of them). `--bundles` runs several bundles at once. A merge that joins stored golden
records or creates one by an identifier runs beside the others of its kind; one that merges two, or creates by an exact name,
holds the kind lock alone, so before scaling a merge, sample its sessions: processes waiting on the lock gain nothing from
more of them. Time one batch alone before blaming a lock: its statements inside a transaction rolled back (nothing is
written), then the same batches beside each other; a load far slower than the batches alone is contention, not work.

Increasing `workers work --limit` changes the work bound of that invocation; it
does not itself create parallel workers. A frozen source execution setting cannot
be silently edited to increase parallelism. If a supported path cannot divide
an oversized file/unit safely, report that capability gap for implementation.

When memory, disk or connection pressure rises, reduce new dispatch, let current
transactions finish or follow supported recovery, and re-evaluate. Preserve all
remaining input in the backlog. Do not stop the shared server, reset another
agent's state, create another permanent server or change platform limits to hide
contention. Resource planning creates no new scheduler or resource-lease store;
Bookkeeping/destination leases remain authoritative.

## Contention: find the tier, then change the design or the scale

A slow load has one saturated tier. Throttling hides which, so it comes last.

1. **Measure each tier** (`load_chain.py --auto` reads the first two every cycle and acts on them):
   - the machine running the loads: load average against its cores, and swap;
   - the database, as the reader login: sessions active, sessions waiting on locks and the longest wait, connections
     against the limit;
   - the source: how fast one reader opens a file.
2. **Remove a shared hot spot by design** when the database is the tier that waits on locks:
   - merges of one kind of master data that join stored records take turns, so they share a lane; merges that only
     create by an identifier run side by side, since each new identifier value is claimed under its own lock and read
     again;
   - a lock held for a step instead of a transaction, or one lock taken where a lock per value would do, is a defect in
     the engine: fix it there, not by running fewer loads;
   - keep a unit of work (a bundle) small and committed in order, so a lock lasts one transaction.
3. **Scale the tier that is saturated:**
   - the machine running the loads: run them where the capacity is (production runs the same loader on AWS, so a laptop's
     rate is a local figure);
   - the database, when its CPU or connections are the limit and its lock waits are not: resize the hosted instance
     (an approved, billable change; see aws-snowflake-operations). More compute does not shorten a lock queue;
   - connections: fewer, wider workers, or a pool.
4. **Throttle last:** workers go from 2 to 8 with the readings, and fall when the database is locking or the machine is
   pressed.
5. Record the readings, the change and its effect in the ticket.

## Progress, failure and recovery

Diagnose as the reader login (`reader.env`): it shows sessions, locks and waits and reads no table. A step that needs the
owner or a runtime login to be understood is a gap in the reader, to fix there.

Use current CLI help and [Bookkeeping recovery](../../../skills/bookkeeping/RECOVERY.md).
Representative inspection commands are:

```bash
edgar-warehouse bookkeeping runs --limit 20
edgar-warehouse bookkeeping status <run-id> --limit 100
edgar-warehouse bookkeeping leases <run-id> --limit 100
edgar-warehouse change-journal events --run-id <run-id> --limit 20
```

These queries have bounded listings; a short listing does not account for the
whole source. Use full state counts and delivery inventories for reconciliation.

### Find the last run

For a last-run question, resolve source, target and environment. Inspect
source-specific load logs and manifest evidence, preferring successful completion
summaries over modification times. Report times in local ET. Verify with
`bookkeeping status` in the load's private store: complete, every unit verified,
no pending delivery. `bookkeeping runs` is unfiltered and bounded; absence is
not proof. If a historical log ID is unknown to the current store, report only
the logged result, not current verification. Do not replay or force to answer
when a run last completed.

#### Examples: SEC Company

- The target is `sec.company` / `mastering` in hosted MDM (Snowflake Postgres),
  not Gold or `sec.company-facts`.
- Search `~/.local/share/edgartools/load-logs/` and
  `~/.local/share/edgartools/hosted-prod/manifests/load/sec.company/mastering/`.
- Use the same private store environment as the load; never print connection URLs.

| Observation | Decision |
| --- | --- |
| A worker's report is refused | The lease lapsed while it worked, so the unit waits again. Run the worker again; after expiry use supported reclaim/reconciliation. |
| Worker failed, interrupted, or lost an acknowledgement | Inspect the retained run and destination effects; resume through the existing engine with original pins and idempotency keys. |
| All work verified, Journal delivery pending | Recover delivery through its owning producer; retry the same event/envelope and verify the receipt. Do not rerun completed merges or declare the run complete. |
| Explicitly invalidated required input | Stop affected work, preserve history/progress, and use the approved correction path. Ordinary supersession is different. Missing live enforcement is reported, never assumed. |
| Nothing changed | Reconcile considered = selected + already processed; selected = 0 starts no new mastering run. |
| Monitor window expired or user stopped the operation | End the watcher, retain resumable evidence and state the remaining work and next invocation. Do not abandon a hidden watcher. |

Completion requires full declared work verified, required deliveries acknowledged,
and source input outcomes reconciled, including pending/deferred/rejected records
and waiting relationships. Counts and destination readback establish completion;
CLI exit zero alone does not. Required destination publication is included when
the selected target declares it; no omitted stage is silently treated as done.

## Test and clear a source run

A test proves **Install and enable one source** on the **test** instance from
[data-platform setup](../../../skills/data-platform/SKILL.md#0-setup). Select its connections through
[Connection URLs and environment](../../../skills/data-platform/SKILL.md#connection-urls-and-environment),
not a production container.

Run one source through install, enable and its wired `rules run`. The test
passes only when `edgar-warehouse bookkeeping status <run_id>` shows
`run.state` `complete` and every declared unit verified. Record the source,
feed, target, version and run id in the source runbook. Counts only.

Clear the test only after that run is finished, or when the operator asks to
abandon it. Read `edgar-warehouse bookkeeping leases <run_id> --limit 100`
first. A live lease held by another run is not yours to clear: stop and
report it.

Clear-out removes the **test** container and its volume, the volume name
being the container name plus `-data`, as data-platform setup allows. Then
create the missing databases again and apply store DDL. The next test
installs and enables the source on that empty test instance. Captured files
stay. A production container, its volume and its data stay. Stopping a
container to clear a worktree is not this clear-out.

## Keep the source runbook current

Maintain the following operational record, updating observations in ET:

- Scope: environment, source/feed, target and delivery, destination, current
  authorization, complete inventory/evidence references and source cadence.
- Version references: deployed Rules, dataset/matching/merge configuration,
  reference/shared inputs, runtime and the evidence supporting their use.
- Current work: run IDs, counts, last verified progress, active ownership/leases
  referenced from Bookkeeping, pending deliveries and last successful inventory.
- Resource plan: actual allocation, competing work, measured unit costs,
  chosen concurrency/bundles, estimate range and reason for any adjustment.
- Reconciliation: considered/selected/already-processed files; outcome counts;
  detected renames/drift, pending links, verification and Journal receipts.
- Recovery: blocker, retained pins, deadline, next safe action and its owner.

Prefer an existing source's operational record. If none exists, create one in
the task's private evidence area and retain its path in the workstream handoff.
The record is a readable index; a Markdown checkbox never grants a lease,
approves a rule or marks a Journal event delivered. A resident operations agent,
notification channel or future scheduling hook requires its own implementation
and authorization; this skill only directs the agent while it is invoked.
