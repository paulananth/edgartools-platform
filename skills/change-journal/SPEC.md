# Change Journal and Change Propagation

Current acquisition status (2026-09-29):
`sec.submissions.company/submissions` is the sole active feed. Its locally
qualified caller is described in the Company route (`docs/company-only-acquisition.md`).
Other SEC and GLEIF acquisition callers are retired; their historical audit
stores remain separate.

Change Propagation is the canonical name for diff processing. Historical
artifacts retain their original paths and terminology. Current ownership is:

| Owner | Durable responsibility |
| --- | --- |
| Bookkeeping | Root runs, configured work, scoped leases, checkpoints, retry/recovery and transaction-local delivery intent |
| Rules | Source/feed policies, versions, coverage, exact-digest proof/approval and activation evidence |
| Change Journal | Immutable decisions, transitions and verified outcome receipts |
| Source/destination stores | Source bytes, manifests, business attributes and committed business effects |

## Empty journal and receipts

### Independent implementation boundary (2026-10-02)

The journal core contains only `store.py`, `database.py`, `cli.py`, exports and
checksummed SQL migrations. Its warehouse dependency is the pure
`control_contract.py` module. It imports no Bookkeeping, Rules, MDM, acquisition,
Silver, loader or parser implementation. Standalone operations are available as
`edgar-warehouse change-journal` (or the journal wheel's own `edgar-change-journal`) with init/migrate/status/
events/verify; no domain registry or callback is constructed there.

Provider capture belongs to `acquisition.capture`; policy/registration authority
to `rules.acquisition_authority`; source inventories to
`application.source_evidence`; MDM delivery to `mdm.clean.journal_delivery`.
The application composes existing owner recovery routes through
`application.journal_recovery`, and producer workflow evidence through
`application.journal_evidence`. These integrations depend on the journal
interface; the journal does not depend on them.

Independent-package architecture and PostgreSQL acceptance tests prove this
boundary. `packages/change-journal` builds the independent journal wheel with
SQLAlchemy and the PostgreSQL driver as its only direct dependencies. Install
it in a dedicated virtual environment; its `edgar_warehouse` namespace overlaps
the full warehouse distribution. See the
[installation and verification boundary](INDEPENDENCE.md).
The full warehouse distribution still carries its other commands' dependencies.
No container rollout or package publication is included in this refactor.

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

For an already initialized, checksummed schema, use `change-journal migrate
--runtime-role <role>` with the same separate migration connection. Migrate
refuses to create a missing schema; neither command imports legacy events.

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
the Rules contract (`.planning/archive/codex/2026-10-02/change-journal/RULES-INTEGRATION.md`).
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

The `source-manifest-v2` capability requires a typed `scope.complete` document
with exact source, feed, scope and required producer identity. Its member
inventory declares artifact references, format (`bytes`, `json-array` or
`ndjson`), count, business key fields and the SHA256 of sorted canonical key
tuples. Verification reads the actual immutable members, checks counts and key
digests, and rejects repeated artifacts or business keys. Captured byte members
also satisfy the approved feed completeness policy. Full revisions include
their raw artifact in this inventory. Revision predecessors must match an
actual verified Bookkeeping receipt with acknowledged journal intent, the
exact leased resource, scope and preceding checkpoint comparison. Unverified
work declared for that scope in the predecessor root blocks advancement.
A zero scope requires a real typed empty
inventory; an opaque evidence object cannot certify zero work. Row inventories
describe source-owned records; the destination owner must verify committed
effects before issuing them. They do not replace destination read-back.

Changing this processing version invalidates old validation bundles; rebuild
and qualify the exact source/feed plan before deployment.

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

Producer workflow qualification in `edgar-warehouse plan workflow`
reads back the actual completed validation root, exact frozen
submission, verified work counts, checks, zero delivery backlog and journal
receipts. An edited validation report cannot replace that authority. When
deploying to different stores, retain the validation databases and explicitly
provide both `BOOKKEEPING_VALIDATION_DATABASE_URL` and
`CHANGE_JOURNAL_VALIDATION_DATABASE_URL` as read connections. With neither
set, the validation root must exist in the selected fresh target stores. There
is no legacy lookup or history import when validation authority is unavailable.

## Qualification and cutover status

Local acceptance covers actual PostgreSQL 16 restricted functions, duplicate
and conflicting delivery, lost acknowledgements, outages, lease authority,
resource CAS/holes and bounded capture fixtures across the acquisition
families. Fixture capture alone does not qualify family parsers, Snowflake
producer barriers, every legacy acquisition caller or AWS cutover.

The inventory (`.planning/archive/codex/2026-10-02/change-journal/LEGACY-INVENTORY.md`)
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

Separate `journal-large` and `mdm-journal-large` task families receive the three
runtime DSNs and an S3 `BOOKKEEPING_MANIFEST_ROOT`. They default to read-only
`change-journal status`, retain the current large CPU/memory envelope and do
not receive the legacy Bookkeeping connection. Original warehouse/MDM task
families ignore the fresh secrets and preserve their connections and commands.
No migration connection is injected.
Flags/retained application summary are the only resolution sources for fresh
connections; there is no legacy/MDM/name fallback. Fresh task ARNs are recorded
under `fresh_control.task_definitions`; existing state machines keep their
original task ARN bindings and commands. This is connection wiring, not feed
promotion. No workflow has been redirected by this implementation.

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
