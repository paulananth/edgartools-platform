# Change Journal and Change Propagation

Change Propagation is the canonical name for diff processing. Historical
artifacts retain their original paths and terminology. Current ownership is:

| Owner | Durable responsibility |
| --- | --- |
| Bookkeeping | Root runs, configured work, scoped leases, checkpoints, retry/recovery and transaction-local delivery intent |
| Rules | Source/feed policies, versions, coverage, exact-digest proof/approval and activation evidence |
| Change Journal | Immutable decisions, transitions and verified outcome receipts |
| Source/destination stores | Source bytes, manifests, business attributes and committed business effects |

## Empty journal and receipts

Provision the new `change_journal_clean` database on PostgreSQL 16. The `journal`
schema contains exactly one append-only `event` table. Checksummed migrations
are recorded in its schema comment. Migration and runtime connections are
separate. Runtime has only schema usage and bounded append/read functions;
direct table/sequence privileges and mutation functions are refused.

Set `CHANGE_JOURNAL_DATABASE_URL` and
`CHANGE_JOURNAL_MIGRATION_DATABASE_URL`. Neither falls back to the legacy
ledger or MDM connection. Apply with:

```bash
uv run --extra mdm --extra s3 edgar-warehouse change-journal init --runtime-role <role>
```

The version 1 envelope contains `producer`, original `event_key`, root
`run_id`, `source`, `feed`, identifier-only `scope`, `event_type`, UTC
`occurred_at` and bounded exact URI/SHA-256 `evidence` references. It contains
no source records/business fields. UTF-8 sorted compact JSON defines the
canonical SHA-256. Receipt fields are `id`, `canonical_hash`, `recorded_at`,
and `event`. Uniqueness is `(producer,event_key)`: an identical retry returns
the original receipt; different content fails. `append`, `get`, bounded
`list` and `verify` are the shared Python interface.

`verify` checks canonical hash and exact durable read-back; it does not prove
the business contents of an artifact. Owner verifiers do that. The bounded
event-id inspection cursor is not a completion watermark: concurrent insert
transactions may commit out of order. Producer completeness comes from frozen
manifests and Bookkeeping checks, never absence in an event listing.

## Transaction and recovery boundaries

Bookkeeping completion, ordered checkpoint advancement and journal intent
commit together. Resource checkpoints use the same `checkpoint` table: their
leased resource is unique across runs, and each frozen unit names its expected
prior `revision` and `position` in `cursor.resource_checkpoint`. Advancement
is one position at a time, requires the current resource lease and cannot skip
earlier unverified work. Compare-and-swap rejection rolls completion and
intent back. There is no import of an old cursor; an explicit baseline begins
at position -1/revision 0 over verified source-owned input manifests.

The journal transaction is separate. Delivery reads back the exact receipt
before the owner acknowledges intent. A lost acknowledgement retries the same
key/envelope. No cross-database atomicity is claimed. Clean MDM retains its
local publication outbox, immutable batches and commit evidence. Its adapter
references the committed payload/hash instead of copying business attributes
into the shared journal. Only batches declared by a fresh root manifest may
enter the fresh journal.

Configured `provider.capture` commits a fenced authorization intent, verifies
its journal acknowledgement, then checks/renews Bookkeeping authority before
each provider request. Journal failure or lease takeover blocks the request.
Authorization and outcome use separate producers, `acquisition` and
`acquisition.outcome`, each retaining the original candidate id. Conditional 304 results
must link verified prior source bytes and pass current completeness; they
never fabricate an empty capture. Deferred requests remain pending. Captured
outcome manifests at their exact frozen URI reconcile after a lost completion
acknowledgement. No storage listing establishes success.

## Rules and source-owned evidence

The acquisition section and integration boundary are described in
[the Rules contract](../../.planning/workstreams/change-journal/RULES-INTEGRATION.md).
Source files and `rules.rule_version` are the only configuration owners.
Proof baseline manifest bytes are read back by hash before proving/activating
a version and during fresh submission/recovery.
Acquisition proof must qualify every declared feed and its required producer
counts. Approval covers the exact digest. Dataset registration can pin an
approved Rules envelope without querying legacy registry tables. Unchanged
source mappings retain their prior mapping versions/registration evidence.

`source.evidence` verifies immutable source-owned revision, conflict,
resolution, exclusion, import, producer and explicit empty-scope manifests.
Original producer keys are frozen in work-unit keys. Revision manifests pin
raw/canonical/domain evidence and parser/schema/configuration versions; full
snapshots require scope-completeness evidence. Imports verify foreign bytes
before local immutable writes; resolutions and exclusions require operator
role, reason and authorization evidence. A producer's zero count still needs
verified scope-completeness evidence. These are artifact contracts, not a
claim that every legacy caller has migrated.

## Commands and shared skill

```bash
uv run --extra mdm --extra s3 edgar-warehouse change-journal status --source <source> --feed <feed>
uv run --extra mdm --extra s3 edgar-warehouse change-journal events --run-id <root> --limit 100
uv run --extra mdm --extra s3 edgar-warehouse change-journal verify <receipt.json>
uv run --extra mdm --extra s3 edgar-warehouse change-journal recover bookkeeping <root> --limit 100
uv run --extra mdm --extra s3 edgar-warehouse change-journal recover mdm <batch> --worker <worker>
```

Recovery delegates to the owning Bookkeeping/outbox interface. Journal recovery
delivers committed intent; it does not silently request new source data.
Recovery returns 3 when deliveries remain pending or authority/evidence fails.
Configured Rules submission supports an exact `--feed` binding. Install the
shared source/feed skill with `bash skills/change-journal/link.sh` (or a
temporary `--home` for installation tests). Both runtimes use one skill file.

## Qualification and cutover status

Local acceptance covers actual PostgreSQL 16 restricted functions, duplicate
and conflicting delivery, lost acknowledgements, outages, lease authority,
resource CAS/holes and bounded capture fixtures across the acquisition
families. Fixture capture alone does not qualify family parsers, Snowflake
producer barriers, every legacy acquisition caller or AWS cutover.

[The inventory](../../.planning/workstreams/change-journal/LEGACY-INVENTORY.md)
tracks remaining active uses and replacement tests. Keep old stacks available
for their runs/backlog; fresh roots are marked `change-journal-v1` and reject
historical roots. Do not import historical decisions, checkpoints or pending
delivery. Fresh provisioning never creates legacy source/mirror tables.
`provision-local-postgres-stores.sh` now provisions only the three fresh
control stores, with separate NOLOGIN owners and restricted runtime logins;
it imports nothing and removes nothing. Original acquisition connection
helpers reject a runtime with `CHANGE_JOURNAL_DATABASE_URL` configured.
That marker also restricts the CLI to `rules`, `bookkeeping` and
`change-journal`, and refuses ungated SEC transport. Legacy scheduled commands
cannot be run with the fresh connections; keep their original task revisions
until their complete replacement feed qualifies.

Deploy through the existing AWS application workflow only after all affected
feeds pass counts, authorization, durable receipts, completeness, destination
parity, backlog and recovery gates. Physical deletion is a separate reviewed
retirement step; retain the legacy audit archive indefinitely by default.


## AWS connection wiring and promotion gates

The application script accepts these three runtime secret ARN flags together:

```text
--bookkeeping-clean-postgres-dsn-secret-arn
--rules-postgres-dsn-secret-arn
--change-journal-postgres-dsn-secret-arn
```

Warehouse and MDM task definitions receive the three separate runtime DSNs
and an S3 `BOOKKEEPING_MANIFEST_ROOT`. No migration connection is injected.
Flags/retained application summary are the only resolution sources for fresh
connections; there is no legacy/MDM/name fallback. This is connection wiring,
not feed promotion. The AWS state machines retain their original commands.

Before rollout, provision the three isolated PostgreSQL 16 databases with
separate owners/runtime roles, apply checksummed migrations via owner
connections, create/populate empty Secrets Manager containers out of band,
and review execution-role access to exactly those runtime secret ARNs. No
wildcard IAM expansion or Terraform apply is part of this workstream.

Freeze bounded source/feed baseline manifests and the exact approved Rules
body, finish complete replacement stages and qualify destination/count parity,
producer completeness, authorization, duplicate/conflicting receipts, missing
acknowledgements, lease takeover, configuration drift and zero backlog. Keep
original task revisions and database archives for rollback. Finish or retain
legacy runs there and drain historical delivery there; never replay it to the
fresh journal. Then use the existing application rollout to promote each
qualified feed with matching retained validation evidence. Revoke old runtime
access only after the new feed passes its live checks. Physical deletion
remains separate and legacy audit retention is indefinite by default.
