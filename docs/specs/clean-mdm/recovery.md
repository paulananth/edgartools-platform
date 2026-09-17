# Change Journal, Bookkeeping, and recovery

Status: proposed implementation contract, preserving accepted ownership.

## Ownership

“Change Journal” in the user's plan means the MDM evidence/decision/transition
surface of the existing Change Ledger, not a second root-run or acquisition
authority. Extend existing ledger records where their meaning fits; add typed
MDM decision/effect records where it does not. Acquisition byte-conflict rows
must not be overloaded to mean conflicting selected master fields.

| Owner | Durable responsibility |
| --- | --- |
| Bookkeeping `pipeline_run` | Root run, invocation arguments/scope, timing, operational attempts and verification summary; existing primary key is `pipeline_run_id` |
| Change Ledger / MDM Change Journal | Append-only source and merge decisions, policy versions, attempts, transitions, reasons, recovery and publication outcomes |
| MDM Commit Evidence | Exact committed entity/profile/relationship effects and originating `run_id` |
| Consumer Checkpoint | Committed bounded progress for one consumer, contract/policy version, family/epoch and source position |
| Publication intent and receipts | Required consumer/version, immutable generation/payload hash, idempotency key, fenced lease and verified downstream effect |

The same root run value joins these records; retries have separate attempt IDs
but never manufacture another root to conceal incomplete work. Batch
deduplication keys are business identities independent of the run. A redelivery
in a new run records observation/no-op lineage to the original effect.

## Transaction boundary

Use one PostgreSQL connection/transaction for accepted ledger decision,
historical source assertions or bindings to previously captured assertions,
identity/profile/relationship projection, MDM Commit Evidence, Consumer
Checkpoint and all required publication intents. No nested helper commits.

Capture evidence can precede this transaction. A failed projection batch leaves
captured evidence available, while rolling back every attempted business
effect and checkpoint advancement. A rejected/conflicting record may commit a
terminal evidence disposition without a master change; this does not satisfy
mandatory publication completeness when that consumer requires a resolution.

Bookkeeping currently uses `BOOKKEEPING_DATABASE_URL` and independent sessions;
do not claim its status update is in the MDM transaction across databases. It
observes durable committed batches and receipts and can repair a stale status.
The local environment may colocate databases for convenience, but must test a
lost Bookkeeping acknowledgement. If ledger and MDM are not on one transactional
database in the chosen target, reject configuration before processing; never
simulate atomicity with two successful commits.

Lock/check the expected checkpoint and affected identity closure. Commit
against the expected predecessor and policy version; stale workers cannot
advance a checkpoint or mutate the new generation. Deterministic lock order
and bounded retries handle deadlocks/serialization failures. Immutable batch
keys return prior committed results after a lost acknowledgement. Changed
payload under the same batch key is a conflict, not a retry.

The runtime currently commits entity work in separate worker sessions and
requests publication late in `MDMPipeline.run_all()`. The new intent belongs
in every committing batch; no successful master commit may rely on the final
orchestrator step to remember it.

## Publication

An outbox worker claims an intent with an expiring lease and fencing token.
Network calls occur after the master transaction. The consumer receives a
versioned immutable payload, generation, content digest and idempotency key.

- Export uses existing S3 / Snowflake native-pull infrastructure with a new
  explicitly versioned MDM contract. Payload/manifest retries use the same
  content identity. Verify downstream keys, values, provenance and generation.
- Graph stages an immutable generation, validates nodes/edges/endpoints and
  exact parity, then activates it through the existing generation mechanism.
- An expired worker may observe success but cannot acknowledge with a stale
  fence. Its replacement reconciles the external idempotency key before retry.
- If the external destination has no receipt API, verify the materialized
  generation/hash and keys. An uncertain outcome stays pending, not complete.
- Old generation delivery cannot overwrite a newer accepted projection.
  Compensating reversal/retirement events are ordered and versioned too.

The ledger records each transition and receipt. Mutable lease/status rows are
operational projections, not replacements for the append-only history.
“Master committed,” “export verified,” “graph verified/active,” and “end-to-end
verified” remain separate observations. Bookkeeping reports completion only
when every required bounded batch, source disposition and consumer receipt
passes the run's frozen contract. Optional consumers must be declared before
execution; a failed required consumer cannot be downgraded after the fact.

## Failure matrix

| Interruption | Required recovery |
| --- | --- |
| Before batch transaction | Resume the same pinned evidence and checkpoint |
| After projection write but before commit | Roll back all effects, decision bindings, checkpoint and intent |
| Commit succeeds; process/acknowledgement lost | Read the prior durable batch result; no second business effect |
| Master committed; exporter never starts | Durable intent remains claimable |
| External write succeeds; receipt lost | Query/verify the same generation/key; record receipt or repeat idempotently |
| Worker lease expires during publication | New fenced worker reconciles; old fence cannot acknowledge |
| Export verified; graph fails | Resume graph for the same generation; run remains incomplete |
| Policy changes while batch is running | Reject stale activation/commit; new policy requires explicit work identity |
| Source publication correction arrives out of order | Preserve all evidence; project by native version/effective-time rules |
| Two workers merge overlapping subjects | Serialize/revalidate the affected closure, retaining all conflict evidence |
| Bookkeeping completion update is lost | Reconstruct status from committed batches and verified receipts |
| Reversal crashes partway through building replacement | Prior generation stays active; resume staged generation without exposing partial state |

## Application permissions

Use migration owner and restricted runtime identities. Runtime cannot create
objects, truncate/drop tables, change policy activation, or update/delete
immutable assertions and journal events. Govern mutable projections separately
and limit writes to reviewed merge/publication operations. Verify effective
permissions including inherited roles, not only direct grants. Existing
acquisition role fencing and Snowflake `snowflake_write` inheritance lessons
apply. Never weaken the existing acquisition permissions to enable Clean MDM.
