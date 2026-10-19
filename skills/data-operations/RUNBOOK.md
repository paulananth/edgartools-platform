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
| Qualify | Those skills attach genuine matching test/qualification results to the exact content and input evidence. Reuse existing matching evidence; test changed or uncovered behavior. |
| Approve for release | Follow the shared [approval procedure](../data-onboarding/APPROVE.md), retaining actual approval evidence and applicable operator authorization. A different configuration is a new version. |
| Deploy | data-operations coordinates saving missing exact versions, recording their evidence/approval through the supported lifecycle, activating the merge policy and then the source, and reading back destination registration/active state. |
| Operate | data-operations checks the completed delivery, capacity and dependencies, then submits/resumes and verifies through Bookkeeping and Change Journal. |

Keep a release record referencing the source configuration, dataset/matching/
merge versions, RDM/shared-input pins, runtime, test artifacts and approval.
Environment connection settings, credentials and operational state remain private
and separate from that record. A release record is an index into existing
evidence, not a second Rules database or a new status store.

Promote the same content and applicable evidence to the destination. Recheck
connectivity, roles, registered worker/verifier capabilities and delivery/dependency
availability there. A new environment alone does not require repeating unchanged
business-rule qualification. Exact hashes, retrievable genuine artifacts and
the supported destination lifecycle must still validate. An older source's
approval does not approve a changed policy, and a schema migration is separate
from configuration promotion.

The shared lifecycle already supplies save, record-proof, approve and activate
operations. There is no single automated release-transfer/import command today.
If required evidence cannot be represented or a consumer still requires download
producer steps, report that runtime gap; do not forge proof, register through test
helpers or bypass activation. Keep source-specific readiness status in its
operational record. Publishing this skill does not resolve runtime gaps or
deploy any Rules version.

The skill's maintained source is `skills/data-operations/` in the repository;
the data-platform package ships it to the installed agent skill folders. A
source runbook references the release and its active environment/run IDs.

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

## Resource sizing

Size at the execution boundary: a Mac host's CPU/RAM does not describe a
container's allocation, and server connection limits do not describe its free
budget. Read available resources and active runs before each new dispatch.

Record the ready backlog's file count and compressed/expanded byte estimates,
measured peak memory per unit, worker and verifier throughput, temporary/output
disk needs, connection consumption and other agents' reservations/current work.
Use source/stage measurements from comparable verified runs; distinguish a
measurement, estimate and unknown. Existing qualified early-unit measurements
may refine the estimate; an invented speedup or unqualified sample is not proof.

Choose concurrency no larger than the tightest CPU, usable-memory,
database-connection and declared-worker budget, including verification and
parallelism inside each worker. Choose bundle sizes within the existing supported
contract bounds. Keep headroom based on observed pressure and shared use. When
measurements are unavailable but one unit can safely fit, begin with one worker
and conservative bundles, then measure. If even one unit cannot fit or fit is
unknown, wait/report the missing estimate; do not force it or reject the source.

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

| Observation | Decision |
| --- | --- |
| Work reported but not admitted | Run the separate verifier under the current lease; after expiry use supported reclaim/reconciliation. Worker success is not completion. |
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
[data-platform setup](../data-platform/SKILL.md#0-setup). It uses that
instance's private connection file. It does not use a production container.

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
