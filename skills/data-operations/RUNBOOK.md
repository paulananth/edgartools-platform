# Recurring load decisions

Use this reference when operating a source, sizing its backlog or handing an
unfinished run to another agent. Keep the source's runbook current across runs;
write references to engine evidence rather than copying operational state into
a second ledger. Store private inventories and captured values outside Git.

## Configuration promotion

Final means a fixed, tested and approved version. Git retains the authoring
files; the destination Rules database retains execution authority. Approval is
recorded evidence on a version; activation selects that version in an environment.
Copying files into a folder named final establishes neither.

| Stage | Owner and completion evidence |
| --- | --- |
| Author | data-onboarding creates a source; refining-rules changes an existing source/domain. The exact configuration and generated documents are versioned. |
| Check | Validate only changed documents locally; CI checks the full Rules tree ([LOAD](../data-onboarding/LOAD.md)). |
| Deploy | The rules files ship with the image. `rules register` registers the merge rules and Dataset Contracts in the destination's MDM. |
| Operate | data-operations checks the completed delivery, capacity and dependencies, then submits/resumes and verifies through Bookkeeping and Change Journal. |

Keep a release record referencing the source configuration, dataset/matching/
merge versions, RDM/shared-input pins, runtime, test artifacts and approval.
Environment connection settings, credentials and operational state remain private
and separate from that record. A release record is an index into existing
evidence, not a second Rules database or a new status store.

Promote the same content and applicable evidence to the destination. Recheck
connectivity, roles, registered worker capabilities and delivery/dependency
availability there. A new environment alone does not require repeating unchanged
business-rule qualification. Exact hashes, retrievable genuine artifacts and
the supported destination lifecycle must still validate. An older source's
approval does not approve a changed policy, and a schema migration is separate
from configuration promotion.

The rules files ship with the code; `rules register` registers them in a destination's MDM.
If required evidence cannot be represented or a consumer still requires download
producer steps, report that runtime gap; do not forge proof, register through test
helpers or bypass activation. Keep source-specific readiness status in its
operational record. Publishing this skill does not resolve runtime gaps or
deploy any Rules version.

The skill's maintained source is `skills/data-operations/` in the repository;
the data-platform package ships it to the installed agent skill folders. A
source runbook references the release and its active environment/run IDs.

## Initialize a hosted store

A hosted PostgreSQL 16 instance (Snowflake Postgres) is initialized with the same commands as the local store, in this
order, by skills and their own commands only. Use
[Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment) for the private connection
files, roles and credential handling. The commands below are the whole procedure; each prints names and checksums, never
a connection value.

The stores folder is `~/.config/edgartools/hosted/`, one folder for the store: `connection.env` (the owner logins),
`worker.env` (the runtime logins and the manifest root), `governance.env` (the registration login). `load --stores`
takes it. A second copy of these files elsewhere goes stale, and a stale copy fails `doctor` with a login error.

1. **Instance.** [aws-snowflake-operations](../aws-snowflake-operations/SKILL.md) creates it (snowflake-postgres skill,
   `pg_connect.py --create`; its comment takes letters and spaces, a `;` is refused). Wait for `state` to read `READY`,
   then for its hostname to resolve on this machine. A lookup made before the name existed can stay cached as "not
   found" for up to an hour while a public resolver already answers (`dig +short @8.8.8.8 <host>`, count the lines,
   never print them): the operator flushes the cache (`sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`
   on macOS). A rotation of a login's password needs the operator's word, and nothing below needs one.
   Run every command below from a checkout of today's `main` with its environment built
   (`uv sync --extra mdm --extra s3`) or a bundle installed from it: an older `edgar-warehouse`
   creates older schemas.
2. **Databases.** An instance that holds an old store keeps its logins and gets its databases made again: with the
   operator's word, list them, then drop and create them with the owner and the grants each had:
   ```bash
   set -a; . ~/.config/edgartools/hosted/connection.env; set +a
   python infra/scripts/reset-hosted-databases.py             # lists sizes; refuses while any session is connected
   python infra/scripts/reset-hosted-databases.py --confirm
   ```
   A fresh instance gets its six databases (`mdm`, `rdm`, `rules`, `bookkeeping`, `change_journal`, `silver`) and their
   restricted logins from the stores folder's own files, each login with the password its URL already holds (no login
   is rotated); every URL then names the new instance, and the administrator's URLs its new password:
   ```bash
   python <data-platform skill>/scripts/provision_hosted_store.py --service <the instance's saved service>            # lists
   python <data-platform skill>/scripts/provision_hosted_store.py --service <the instance's saved service> --confirm
   ```
   The service is the one the instance's creation saved (snowflake-postgres skill, `pg_connect.py --create`). Wait for
   its hostname to resolve first. Done when the second run prints that every URL names the new instance.
3. **Schemas** (data-platform's step, [STORES.md](../data-platform/STORES.md)), each with its owner login, in one shell that holds `connection.env`. MDM and Bookkeeping read the owner
   from their ordinary variable, for that command only; the others read their `*_MIGRATION_DATABASE_URL`:
   ```bash
   env MDM_DATABASE_URL="$MDM_MIGRATION_DATABASE_URL" edgar-warehouse mdm migrate --application-role mdm_runtime
   edgar-warehouse rdm init --runtime-role rdm_runtime
   env BOOKKEEPING_DATABASE_URL="$BOOKKEEPING_MIGRATION_DATABASE_URL" edgar-warehouse bookkeeping init --runtime-role bookkeeping_control
   edgar-warehouse change-journal init --runtime-role change_journal_runtime
   edgar-warehouse silver init --runtime-role silver_runtime
   edgar-warehouse rules init --agent-role rules_agent
   ```
   `init` is the whole step on a fresh store; `migrate` follows an `init` only when a later schema file arrives. Done when
   each prints its schema file's checksum.
4. **RDM codes.** With `worker.env` sourced, `python <this skill>/scripts/rdm_restore_published.py --by <name>
   --words "<their exact words>"` (the operator's words go in the approval record). Done when every pin reads `pin ok`.
5. **Registration login.** With the owner connection, `env MDM_DATABASE_URL="$MDM_MIGRATION_DATABASE_URL" edgar-warehouse
   mdm grant-registration --role mdm_governance`. It lets the restricted login read the stored records and write the
   policy and dataset tables, and nothing else.
6. **Source configurations.** `edgar-warehouse rules check` (every source, offline), then, with `governance.env`
   sourced, `edgar-warehouse rules register`. Done when it prints a digest for the merge rules and every Dataset Contract.
   Then the silver tables (data-platform's step; a load creates none and stops when one is missing):
   `bash infra/scripts/deploy-silver.sh ~/.config/edgartools/hosted/connection.env`.
7. **Worker grants**, with `connection.env` sourced, one per worker profile:
   ```bash
   for p in $(python -c "from edgar_warehouse.workers import PROFILES; print(*PROFILES)"); do
     env BOOKKEEPING_DATABASE_URL="$BOOKKEEPING_MIGRATION_DATABASE_URL" edgar-warehouse bookkeeping grant-profile --profile "$p" --worker bookkeeping_runtime
   done
   ```
   Done when `doctor` prints `"ok": true` under `worker.env` (it checks MDM, Rules, Bookkeeping and the Change Journal; steps
   4 and 6 prove RDM and Silver) and `load --plan` reads a capture.

A missing grant or login that a command names is a gap to fix through the central connection section, not to work around.

## Load a fresh store

`rules/load-chain.yaml` holds the order of every source and target, each one's capture, workers and the facts and revision no capture states, and
`scripts/load_chain.py` runs it, so a store is loaded the same way every time and nobody rewrites the list:

```bash
python <this skill>/scripts/load_chain.py --plan     # documents and bundles per step; writes nothing
python <this skill>/scripts/load_chain.py            # the chain; stays awake; each step runs until it reports Done
python <this skill>/scripts/load_chain.py --from <step>   # carry on; a step that is done costs one call
```

Masters come first and each source's silver target last, so silver rows find their masters as they land. A source's later
delivery is a new publication and carries the next `--revision`. The chain stops at the first step that does not finish
in its attempts and names why in that step's log. After the last step it builds the lookups and the links table, once
each, and fills each silver table's master ids (`--finish` runs only those). Check a running chain every 30 minutes; a step that stops reports at its
check, never on a tighter loop.

### The links table is built once

The links table is built whole from every stored record (`edgar-warehouse silver links`), so no target carries a step
for it. A `load` run alone builds it after its last bundle when it mastered anything; a load that is one of several
passes `--no-links` and the last step builds it (the chain's `--finish`). A newly mastered record can be the end a
stored link waited for, so any load that masters builds, whatever its source states.

### Dependencies between loads

Loads depend on each other only as the rules say, and `python <this skill>/scripts/infer_dependencies.py` prints it from
the rules files: nothing here comes from a machine's size. No source needs another loaded first: the Merge Stage holds a
record that finds no master and releases it when a later file gives one, so a load that runs early is never wrong. The
rules state three kinds of ordering:

- **Must** (a load leaves something out otherwise). A target that publishes a second batch of its source's records follows the
  target that publishes the first. The lookups, the links table and each silver table's master ids follow every load (`--finish`).
- **Prefer** (records wait until the other load is done; never wrong, only later). A source with a
  matching rule that waits follows the source the rule names (`holder_source`), else the sources whose minting rules use the
  same identifier namespace, else the sources that mint its kind. Links set no order. Two sources that each prefer the
  other have no order to keep.
- **Alone** (these take turns; they are not dependencies). Merges of one kind of master data that merge golden records or create them by exact name (one that joins stored ones, or creates by an identifier, runs beside the others), and two loads of one source and target (their outputs would collide).

Everything else runs at the same time. The chain file turns that into lanes: `lane` marks steps that may run together,
`waits_for` is exactly the edges above that cross lanes, and a test holds the chain equal to the inference, so a rule change
that adds a dependency fails the test until the chain follows it.

```bash
for lane in A P S C L O D F; do python <this skill>/scripts/load_chain.py --lane $lane & done   # eight lanes, one process each
python <this skill>/scripts/load_chain.py --finish          # once every lane reports its last step done
```

A step waits for the steps of other lanes it needs, and for any other load of its own source and target to end.

#### Examples: this store's dependencies

From the shipped rules: no source is a must for another, and a source that only finds (never mints) is GLEIF, which
follows the SEC Company masters its rule names. The links table is built by the N-PORT fund, N-PORT security, N-CEN
fund, N-CEN class and GLEIF targets, and its contracts are stated by those and by Form ADV and ownership, so GLEIF, the
last build, follows Form ADV and ownership. Form ADV follows the Company registrants (SEC Company, N-PORT and N-CEN),
ownership follows SEC Company, and ownership's ticker symbols follow OpenFIGI, 13F and N-PORT securities. OpenFIGI,
13F securities and N-PORT security each prefer the others: either order. SEC persons, the silver-only sources and each
quarter's N-CEN registrants and advisers have nothing to follow, so they start at once.


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
store with statement logging (`log_statement = 'all'`, the log streamed to a file while the load runs, since Docker keeps only its last few log files; `<this skill>/scripts/count_statements.py --log` groups them by shape and by database). At `unit` grain most of a bundle's statements are Bookkeeping's (a claim, status
read and report for each unit); a target at `grain: run` pays none of them ([bookkeeping](../bookkeeping/SKILL.md#grain-how-much-bookkeeping-a-target-uses)).

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

## Progress, failure and recovery

Use current CLI help and [Bookkeeping recovery](../bookkeeping/RECOVERY.md).
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
[data-platform setup](../data-platform/SKILL.md#0-setup). Select its connections through
[Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment),
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
