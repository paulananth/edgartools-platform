# MDM Enrichment Shared Foundation

Owning workstream: [Shared enrichment foundation](../../../.scratch/mdm-enrichment-program/workstreams/00-shared-enrichment-foundation.md)
(workstream 00 of the [MDM Enrichment Program](../../../.scratch/mdm-enrichment-program/map.md)).
Decision record: [MDM Enrichment Shared Foundation map](../../../.scratch/mdm-enrichment-shared-foundation/map.md),
nine resolved tickets, 2026-09-19. Prior design input: the
[GoF design review of 2026-09-13](../../design-reports/mdm-enrichment-shared-foundation-gof-review-2026-09-13.md).

Status: **decision-complete for the GoF review's seven open items; not yet
decision-complete for every heading of the program's specification
contract.** Sections marked *Open* below name what the map did not decide.
No implementation, migration, or runtime change is authorized by this
document; the [release gates](#release-gates) say what must be true first.

Read against: `origin/main` `7467b114` and Clean MDM's
`origin/codex/clean-mdm-integration` `a19463be9be7` (read-only). Where this
spec cites a Clean MDM migration it pins the sha256 that
`edgar_warehouse/mdm/clean/store.py` records in `mdm_v2.migration.checksum`,
so drift between this text and the installed table is visible by one
`SELECT`.

## Governing directive

Legacy MDM (`edgar_warehouse/mdm/` outside `clean/`, ADR 0007's
`mdm_change_log`/`mdm_relationship_instance`/`mdm_entity`) is being
decommissioned. **Nothing in this specification targets legacy MDM.** There
is one MDM and one set of MDM tables: Clean MDM's `mdm_v2` schema
(`edgar_warehouse/mdm/clean/`, `docs/specs/clean-mdm/`). This spec points at
those tables by name and defining migration and never restates their DDL.
`mdm_v2` is Clean MDM's schema name, chosen to sit beside legacy until legacy
is dropped; it is not a second MDM.

## Vocabulary

Terms are as defined in [`CONTEXT.md`](../../../CONTEXT.md): Source Capture,
Bronze Persist, Bronze Artifact, Temporary Bronze Stage, Source Artifact
Archive, Logical Source Revision, Change Ledger, Source Family Registry,
Consumer Checkpoint, MDM Commit Evidence, Enrichment Stewardship Decision,
Deferred Domain Evidence, and the seven actor names locked by this
foundation: Fetch Planner, Source Capturer, Revision Claimer, Publication
Verifier, Ledger Repairer, MDM Committer, Steward.

## Source authority

One external source is one or more **publication families**. A publication
family is the unit that is captured, verified complete, checkpointed, and
recovered independently. It is a `source_family` value in the Change Ledger
and a `source_code` row in `mdm_v2.dataset`.

GLEIF, the first source, is these families
([ticket 02](../../../.scratch/mdm-enrichment-shared-foundation/issues/02-decide-gleif-publication-family-taxonomy.md)):

| Publication family | Members | Cadence |
| --- | --- | --- |
| Golden Copy | Level 1 + Relationship Records + Reporting Exceptions, verified together | daily |
| ISIN mapping | one pair snapshot | daily |
| OpenCorporates mapping | one pair snapshot | bi-weekly |
| BIC, MIC, QCC, GEM mappings | one pair snapshot each | monthly |
| S&P CIQ mapping | deferred; a Conditional Enrichment Source | — |

Relationship Records and Reporting Exceptions are one family because a
missing parent row is ambiguous until the same publication's exception file
is present ("missing parent is not proof of no parent"). Level 1 and each
mapping are independent.

A source never becomes MDM authority by being captured. Capture is
source-wide; publication into a domain is consumer-owned (ADR 0010).

## Accepted identity evidence

Owned per consumer, not here. This foundation guarantees only that every
consumer receives the same shape of evidence: immutable, hash-identified,
publication-bound source records with observed and effective time, and that
no consumer can read a record from an incomplete publication.

## Source and MDM schemas

**No new tables.** The GoF review's seven-record boundary resolves entirely
to existing rows
([ticket 05](../../../.scratch/mdm-enrichment-shared-foundation/issues/05-define-publication-aggregate-schema.md)):

| Record | Lives in | Defined by |
| --- | --- | --- |
| Root run | `bookkeeping.pipeline_run` | existing Bookkeeping schema |
| Source publication | **derived**: the `change_ledger.source_revision` rows sharing `(source_family, source_native_revision)`, manifest file included | migration `013_acquisition_ledger.sql` |
| Publication artifact | one `change_ledger.source_revision` row per file | `013_acquisition_ledger.sql` |
| Source record version | `mdm_v2.assertion` | `023_clean_mdm.sql` `44374b8b47061dd4aa8fc3b600a76bb2c5a28870f044f5f6834e4a701ca942a1` |
| Consumer candidate | not persisted today; the [pre-merge staging proposal](../../../.scratch/clean-mdm-premerge-staging-proposal/map.md) — *proposed, awaiting Clean MDM review* | — |
| Stewardship decision | `mdm_v2.decision` | `023` as above |
| Accepted binding / version | `mdm_v2.identity` (history) + `mdm_v2.projection` (current) | `023` as above |
| Deferred evidence | `mdm_v2.deferred_record` | `027_clean_mdm_deferred.sql` `d34641669802a44924dde46c48239432927eaeb899bb03325a185075cd594c0e` |
| Consumer checkpoint | `mdm_v2.checkpoint` — see dependency below | `023` as above |
| Phase attempt | `mdm_v2.attempt_event` | `026_clean_mdm_attempts.sql` `1b8ce3ac39f71aadd985d1f3fe6ae9c3fa236b084d828461d4f3a0749b1060a3` |

**Root run.** `bookkeeping.pipeline_run` is the persistent root run
([ticket 01](../../../.scratch/mdm-enrichment-shared-foundation/issues/01-decide-root-run-location.md)).
A new source is a new `command_name` value and new `source_family` values;
no table changes. `mdm_v2.batch.run_id` and `mdm_v2.attempt_event.run_id`
are that `pipeline_run_id` — Clean MDM's `023` header states this itself.
Bookkeeping is updated by observation after the MDM commit; it is not a
participant in any transaction.

**Publication completeness is a query, not a status.** A publication is
complete when its manifest file's `source_revision` row exists and every
member the manifest lists has a verified `source_revision` row. A consumer
checks this immediately before opening its MDM transaction. Checking outside
the transaction is safe because `source_revision` rows are immutable:
complete cannot later become incomplete. Supersession is the newer
`source_native_revision`.

**Dependency — per-family checkpoint key.** `mdm_v2.checkpoint` as installed
is `(consumer PRIMARY KEY, position, batch_id)`: one scalar position per
consumer. That cannot hold "Company is at Golden Copy 2026-09-19 but ISIN
2026-09-18," and cannot honor "never advance a sibling family." The
foundation requires the key `(consumer, source_family, publication_family)`
with the consumed publication identity and continuity proof on the row.
This is [proposed to Clean MDM](../../../.scratch/clean-mdm-checkpoint-key-proposal/map.md)
(their `recovery.md` already describes the checkpoint as carrying
"family/epoch and source position"; the DDL lags it) — *status: proposed,
awaiting review.* Until accepted, a consumer of more than one family cannot
be released; see [release gates](#release-gates).

**Generic legal-entity registry** (International Organization route; this
spec owns it per the program's spec-index,
[ticket 09](../../../.scratch/mdm-enrichment-shared-foundation/issues/09-confirm-generic-legal-entity-registry-representation.md)).
There is no separate registry. `mdm_v2.identity.kind` already admits
`international_organization`; such an entity is one `identity` row, its
bound `assertion` rows (names, addresses, legal form, status, identifiers,
lifecycle, relationships), and one `projection` row — the same shape as
Company. Source-classification history is the assertion chain: a
reclassification is a new assertion under a new `publication_key`, never an
overwrite. No `mdm_international_organization` table and no dedicated
consumer, per program ticket 12.

## Temporal behavior

As Clean MDM's `source-evidence.md` defines and this foundation adopts:
source effective time, publication time, observation time, and recorded
time are separate; a missing effective time is explicit under a versioned
dataset rule, never replaced by load time; publication order comes from the
source contract, never from filename sort. `mdm_v2.assertion` carries
`effective_at`, `publication_key`, and `revision`; supersession within a
source record/field chain is a new assertion.

## Conflict and review states

Owned by Clean MDM's accepted Q1–Q16 policy (`docs/specs/clean-mdm/merge-stage.md`)
and its `decision.operation` set (`bind`, `merge`, `reverse`, `override`,
`revoke`, `exclude`, `retire_source`). This foundation adds none and reopens
none. Two states it relies on:

- **Deferred**: an unsupported or unresolvable record is a
  `mdm_v2.deferred_record` with an open blocking review, enforced by
  `commit_batch` (`027`). It stays evidence; it is never coerced into a
  domain.
- **Candidate under review**: the pre-merge staging state, *proposed*. Until
  it exists, a Steward reviews before `commit_batch` only through the
  consumer's own preview path.

## Transaction boundary

Two transactions, fixed order, nothing spans databases
([ticket 06](../../../.scratch/mdm-enrichment-shared-foundation/issues/06-define-consumer-checkpoint-transaction-boundary.md)):

1. **Capture** — database `change_ledger`. Source Capturer verifies each
   file's hash and commits one Logical Source Revision row per file,
   manifest included.
2. **Completeness precondition** — no transaction. The consumer reads
   `change_ledger` and confirms the publication is complete. Not complete
   ⇒ step 3 does not open.
3. **Consume** — database `mdm`. One `mdm_v2.commit_batch` call writes
   assertions, decisions, projection, MDM Commit Evidence, Consumer
   Checkpoint, and every publication intent, or nothing. This is Clean
   MDM's boundary (`recovery.md`, "Transaction boundary"), adopted verbatim.
   The checkpoint row records the consumed publication
   `(source_family, source_native_revision)`; with today's DDL that
   identity travels in the batch request's `effects`, and moves onto the
   checkpoint row when the per-family key is accepted.
4. **Observe** — Bookkeeping's `pipeline_run` status is set afterward from
   the committed batch and receipts.

`commit_batch` checks write safety only — bounded batch; same batch key
returns the prior result and different content is an error; generation not
stale; checkpoint expected and advancing; policy frozen; each assertion's
dataset pinned and active at the right schema; assertion identity not
reused with different content; deferred records carry an open blocking
review. It does not judge whether a match was right; that is the Steward's,
before the commit.

## Replay and recovery

[Ticket 03](../../../.scratch/mdm-enrichment-shared-foundation/issues/03-decide-delta-continuity-and-recovery-order.md),
generalized from GLEIF Company ticket 14:

- Every publication family proves continuity through its own sequence/hash
  chain. Continuity-proof fields are declared per family in
  `change_ledger.source_registry_coverage`, not hardcoded.
- Recovery order: **(1)** the smallest delta span that closes the gap and
  still proves continuity; **(2)** if none does, a full
  Golden-Copy-equivalent reconciliation for that family only. A sibling
  family's checkpoint never moves.
- Missing, late, corrupt, discontinuous, or partially applied input fails
  closed.
- Replay: frozen publication artifacts must reproduce identical record
  inventory, hashes, candidates, decisions, and checkpoint proposal.
  Immutable batch keys return the prior committed result after a lost
  acknowledgement; changed content under the same key is a conflict.

Clean MDM's failure matrix (`recovery.md`) governs interruptions inside
step 3 and publication; nothing here overrides it.

## Storage and paths

[Ticket 04](../../../.scratch/mdm-enrichment-shared-foundation/issues/04-decide-s3-path-and-snowflake-manifest-conventions.md):
new families register in `edgar_warehouse/infrastructure/dataset_path_catalog.py`
and follow the existing `infra/snowflake/sql/bootstrap/` native-pull
pattern. One manifest artifact per publication enumerates its members'
catalog entries; that manifest is itself a captured file with its own
`source_revision` row.

Byte retention follows the `CONTEXT.md` contracts for **Temporary Bronze
Stage** and **Source Artifact Archive**: a complete publication's bytes
remain in the stage until the archive write is verified; a delta's bytes
remain until every required consumer checkpoint and downstream verification
passes, then are deleted without an archive copy. Existing SEC pipelines
keep ADR 0006's durable Bronze contract. The Change Ledger records every
physical storage transition. *Open*: the storage class, transition
schedule, and deletion-evidence row shape were not decided by this map.

## Observability

Every enrichment fact resolves to one `pipeline_run_id`: fetch decisions,
revisions, assertions, decisions, checkpoints, publication receipts. MDM
Commit Evidence counts committed outputs by type per run. "Master
committed," "export verified," "graph verified/active," and "end-to-end
verified" are separate observations (Clean MDM `recovery.md`). *Open*:
metric names, alert thresholds, and the staleness SLO for enrichment
publication were not decided.

## Security

No new Postgres roles
([ticket 07](../../../.scratch/mdm-enrichment-shared-foundation/issues/07-define-role-grants.md)).

| Actor | Technical alias | Does |
| --- | --- | --- |
| Fetch Planner | `edgartools_acquisition_coordinator` | Decides which source files to get; records the Change Ledger Fetch Decision |
| Source Capturer | `edgartools_acquisition_worker` | Downloads a file, verifies its hash, records the capture |
| Revision Claimer | `edgartools_acquisition_processor` | Marks a verified revision "being processed" so it is processed once |
| Publication Verifier | `edgartools_acquisition_silver_finalizer` | Records that a publication's expected outputs were produced and verified, or failed; gates the consumer starting |
| Ledger Repairer | `edgartools_acquisition_operator` | Human-driven quarantine, exclusion, superseded-artifact deletion evidence |
| MDM Committer | Clean MDM runtime role via `commit_batch` | The only path that writes master tables; the application holds no direct table write |
| Steward | `actor` in the decision body | The person or deterministic rule behind a decision; `commit_batch` rejects a decision without actor and reason |

Release Owner is a person approving a consumer's release evidence, not a
runtime role. The S3 delete behind Ledger Repairer is an IAM permission,
not a Postgres grant. Publication Verifier is file-grained and precedes the
consumer; the pre-merge candidate (record → entity) sits inside the
consumer, after matching and before the MDM Committer.

*Open*: IAM policy for the Temporary Bronze Stage and Source Artifact
Archive buckets; secret placement for new source credentials, if any.

## Retention

Normalized evidence, Change Ledger and Bookkeeping history, stewardship
decisions, temporal MDM history, manifests, hashes, run lineage, MDM Commit
Evidence, and deletion records are permanent (**Enrichment Evidence
Retention**, `CONTEXT.md`). Only superseded raw source bytes are deletable,
and only after a verified accepted replacement, with deletion evidence in
the Change Ledger.

## Costs

*Open.* No budget, storage-class economics, or cost-per-validated-output
target was decided by this map. The program's retention-and-cost workstream
owns it; this foundation must expose the counts that workstream needs
(bytes staged, bytes archived, bytes deleted, publications verified, batches
committed) per run.

## Migration and rollback

- No data migration: nothing new is created, and existing tables are unchanged.
- Rollback of a consumer batch is Clean MDM's reversal contract
  (`recovery.md`, `decision.operation = 'reverse'`): projections and
  checkpoint restored, source evidence, decisions, and run lineage preserved.
- Rollback of capture is unnecessary: a captured revision is immutable
  evidence; an unwanted publication is simply never consumed.
- *Open*: the migration path for `mdm_v2.checkpoint` rows written under
  Clean MDM's current per-batch-consumer workaround, if the per-family key
  is accepted — listed as an open question on that proposal.

## Tests

Required before any consumer implementation opens:

| Level | Proves |
| --- | --- |
| Unit | Publication completeness query: manifest present + every member verified ⇒ complete; any member missing or unverified ⇒ not complete; immutability means no flapping |
| Unit | Continuity-proof evaluation per family: smallest covering delta chosen; none ⇒ full reconciliation for that family only |
| Integration (Postgres 16) | A consumer of two families advances one without the other; a failed batch in step 3 leaves step-1 rows intact and no checkpoint moved |
| Integration | Duplicate and reordered capture of the same publication yields one derived publication and identical hashes |
| Offline fixture | Frozen GLEIF artifacts reproduce identical inventories, state changes, and evidence hashes **without publishing a domain record** |

SQLite-backed tests do not count for the transaction-boundary claims.

## Release gates

The foundation is *verified* — and a consumer specification may open
implementation — only when all hold:

1. The offline fixture above passes: identical inventories, state changes,
   and evidence hashes, zero domain records published (workstream 00's exit
   gate, verbatim).
2. Both Clean MDM proposals have a recorded outcome — accepted, adapted, or
   declined — and this spec has been revised to match. A consumer of a
   single family may proceed on today's checkpoint DDL; a consumer of more
   than one family may not until the per-family key exists.
3. Every *Open* item above is either decided or explicitly assigned to a
   named cross-cutting workstream with a link.
4. The parent program and GLEIF Company maps have been re-audited against
   the legacy-decommission directive (flagged there, not yet done).

## Non-goals

- Domain meaning, survivorship, accepted relationship semantics, or release
  approval for any consumer — each consumer's own spec.
- Any change to Clean MDM's tables, functions, policy, or files. Requests go
  through handover proposals, never edits.
- A new schema, database, registry, or Postgres role.
- Automatic matching or consolidation: disabled in Clean MDM this release
  behind Q11's calibration bar; not re-enabled here.
- Applying the Temporary Bronze Stage contract to existing SEC pipelines.
- Legacy MDM in any form.

## Downstream

This spec unblocks
[GLEIF MDM enrichment evidence ticket 17](../../../.scratch/gleif-company-augmentation/issues/17-write-and-verify-gleif-mdm-spec.md)
(the Company/GLEIF consumer spec at `.scratch/gleif-company-augmentation/spec.md`).
Only after that spec exists is GLEIF loader implementation in scope.
