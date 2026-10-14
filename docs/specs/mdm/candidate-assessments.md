# Durable identity candidate assessments

Company Q13 requires a retained assessment before each proposed new source
binding or published-ID consolidation. Migration 028 and the shared Merge Stage
implement this persistence/recovery foundation. They do not implement GLEIF
candidate generation, fuzzy scoring or automatic-rule qualification.

## Execution contract

`MergeStage.apply(**command)` preserves its existing command arguments. For a
new `bind` or `merge`, it computes the bounded batch once and commits an
immutable assessment of it in its own transaction, then applies that same
batch through the master transaction (no rollback preview and no second
computation, 2026-10-11). No human pause is added. Field-only refreshes retain
the existing path. `MergeStage.assess` alone, for inspection before
application, still checks the batch through a rollback preview.

The assessment includes the proposed command, policy digest, validation rule
version, retained assertion and decision IDs, component identities, affected
keys, a dependency snapshot, prior projections and proposed entity/field/relationship/review
effects. Source assertion bodies retain publication identity and provenance.
Rejected well-formed proposals retain their command, available replay context
and veto. Invalid/unbounded input is still rejected at the API boundary.

The final transaction holds the existing advisory lock, checks the
assessment's dependency snapshot and each rule proposal against concurrent
runs, saves at the current generation, and has PostgreSQL check that the batch
equals the assessed effects (by their hash) and fence its dependencies. A batch
PostgreSQL refuses at this point keeps a rejected assessment beside the ready
one, which stays open until its batch is saved. Master changes, the applied event, journal effects,
checkpoint and publication intent commit together. The SQL capability rejects
an assessment created in that same transaction: the assessment must already
be durable. Installed migrations 023–027 remain unchanged.

Dependency checks cover retained and newly arrived source assertions, relevant
identity decisions (including source retirement), component identities, affected
projections and the command's consumer checkpoint. An unrelated generation
alone does not invalidate a proposal. Source registry attestations and policies
remain immutable. Future matching qualification registries must extend the
snapshot before automatic rules can be enabled.

A stale proposal is superseded, never copied into the master. `apply()` retries
assessment up to three times when affected state races with application. A
checkpoint conflict or continued contention fails safely for the existing
bounded run retry mechanism. It does not silently change the frozen command.

## Inspect and resume

For explicit pre-application inspection, use the Python API with the same
command used by the existing Merge Stage (at most 1,000 identity decisions, as
mdm.prepare cuts a batch; no cap on the assessment's size, migration 019):

```python
prepared = stage.assess(**command)
# The assessment is committed and queryable; master state is unchanged.
result = stage.apply_assessment(
    prepared["assessment_id"], run_id=command["run_id"]
)
```

`stage` is a `MergeStage(Store(application_engine))`. The application engine
uses the restricted role installed by `clean.store.migrate`; it has table SELECT
and narrowly granted function execution, with no direct writes. Use the existing
Bookkeeping root UUID for `run_id`. A new process can resume by assessment ID;
no in-memory state, open transaction or held lock is required while it waits.

Read recent assessments without scanning an unbounded candidate set:

```sql
SELECT a.assessment_id, a.body->>'outcome' AS initial_outcome,
       a.body->'command'->>'batch_id' AS batch_id,
       e.event AS current_status, e.batch_id AS applied_batch
FROM mdm.match_proposal a
LEFT JOIN LATERAL (
    SELECT event, batch_id FROM mdm.match_proposal_event e
    WHERE e.assessment_id = a.assessment_id AND event <> 'observed'
    ORDER BY event_id DESC LIMIT 1
) e ON true
ORDER BY a.created_at DESC, a.assessment_id
LIMIT 50;
```

`ready` means validated against the recorded state, not qualification of a
matching algorithm or publication completion. `rejected` retains a veto;
`superseded` requires reassessment; `applied` links to the committed batch.
Events retain the root run UUID. Both assessment bodies and event history are
append-only. Observations of duplicate proposals are idempotent per run.

A lost acknowledgement after master commit replays the retained batch and adds
its normal run observation, without duplicate decisions or publication effects.
A crash before master commit leaves the ready assessment. No incomplete
publication is declared complete by an assessment status.

## Preview and verification boundary

`apply(preview=True, ...)` remains side-effect free. The SQL `preview_batch`
capability validates through the existing commit implementation inside an
exception subtransaction, then rolls it back even if its caller commits. This
uses PostgreSQL's documented [exception rollback semantics](https://www.postgresql.org/docs/16/plpgsql-control-structures.html#PLPGSQL-ERROR-TRAPPING).
The underlying commit implementations are not executable by the runtime role.

Tests run on disposable PostgreSQL 16 with real migrations and the restricted
application role. They cover separate persistence, rejected evidence, stale
and unrelated changes, concurrent duplicate delivery, atomic rollback, same-
transaction bypass attempts, modified effects, preview rollback and immutable
history. The persistent local database and hosted environments are not migrated
by these tests.

The Company milestone still requires approved pinned SEC/GLEIF publications,
candidate/scoring implementation, independent precision qualification, link
suspension/replay, audited deferred-match outcomes and full consumer recovery.
