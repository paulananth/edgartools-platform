---
name: change-journal
description: Initialize or migrate the independent Change Journal, plan or validate journal event delivery, inspect receipts and coordinate owner-controlled delivery recovery. Enforce a journal-only dependency boundary; loaders, source interpretation, Rules approval, work execution and producer outboxes remain outside the journal.
---

# Change Journal

**Modes:** init, migrate, plan, validate, deploy, status, recover-delivery.
The journal records immutable events and verifies durable delivery. It owns no
loader, acquisition policy, work scheduler, business verifier or producer outbox.

## Required independence

The journal package and standalone CLI may depend only on their own code, pure
shared envelope primitives, the standard library, SQLAlchemy and the PostgreSQL
driver. They must start and operate without Bookkeeping, Rules, MDM, acquisition,
Silver, source loaders or parser libraries. No producer registry, callback or
source-specific branch belongs in the journal.

Read [INDEPENDENCE.md](INDEPENDENCE.md) before implementation, architecture
validation or selecting a delivery-recovery path. It describes module ownership,
the isolated-package tests and exactly what journal verification proves.
The [contract](../../docs/specs/change-journal.md) defines envelope and storage
semantics. Resolve the skill's physical path when following relative references.

## Inputs and commands

Init and migrate operate on the whole fresh store. Other modes use the provided
producer/event key, receipt, run id or bounded metadata filters as appropriate.
Source/feed are opaque event labels and optional inspection filters: the journal
does not resolve an active feed through Bookkeeping or query a Rules document.
A new producer/source/feed needs no journal code change when its envelope fits
the versioned contract. Source authority and completeness remain producer duties.

Use the independent wheel in a dedicated virtual environment as described in
[INDEPENDENCE.md](INDEPENDENCE.md). For repository development, the same CLI is:

```bash
edgar-warehouse change-journal --help
```

This CLI exposes only init, migrate, status, events and verify. Existing
`edgar-warehouse change-journal` routes compose the same core operations with
application-owned outbox recovery; the warehouse CLI itself imports other
platform modules and is not the independence proof.

## Init and migrate

Use init for an empty `change_journal_clean` PostgreSQL 16 database; migrate
only for its already initialized checksummed journal schema. Check the exact
database, version and separate migration/runtime roles without printing secrets.
Use `CHANGE_JOURNAL_MIGRATION_DATABASE_URL` for the migration owner and
`CHANGE_JOURNAL_DATABASE_URL` for restricted runtime append/read functions.
Neither falls back to Bookkeeping, legacy ledger, Rules or MDM connections.

```bash
edgar-warehouse change-journal init --runtime-role <role>
edgar-warehouse change-journal migrate --runtime-role <role>
```

Select the command matching store state. Read back migration checksums, the sole
`journal.event` table, restricted function grants and event count. Untracked
schemas, checksum drift, wrong databases or legacy/business tables must block.
Import no legacy events, checkpoints or pending delivery; preserve old archives.

## Plan

Record the requested journal scope: event schema version, producer keys,
metadata labels, exact envelope/evidence hashes, expected delivery count,
restricted journal connection and the owner of each local delivery intent.
Use bounded retained envelopes or fixtures. Plan mode performs no provider
request, Rules approval, Bookkeeping execution or live event append.

Producer workflow planning is outside the journal. The existing pipeline-evidence
helper is now `edgar-warehouse plan workflow` (in
`edgar_warehouse.application.journal_evidence`); it is not a journal operation or
proof that Bookkeeping itself is decoupled. Use it only for an explicitly
requested producer workflow under that workflow's authorization and qualification.

## Validate

Use disposable PostgreSQL 16 and restricted append/read roles. Run the actual
journal from the independent wheel in a clean environment with producer modules
and domain libraries absent and domain imports blocked. Required tests are:

```bash
uv run --extra mdm pytest tests/architecture/test_change_journal_independence.py
uv run --extra mdm pytest tests/integration/test_change_journal_independence_postgres.py tests/integration/test_change_journal_postgres.py
```

Missing prerequisites fail; no qualifying skips. Verify migration restrictions,
append-only storage, unseen labels, canonical hashing, identical/conflicting
keys, concurrent delivery, bounded inspection and exact receipt readback.

When integration changes, also run the affected acquisition, source-evidence,
MDM and Bookkeeping recovery suites. Those qualify owner behavior and delivery
across the journal interface; they are not dependencies of journal execution.
Record hashes, role/version evidence, expected/verified counts and failures.
Distinguish isolated core qualification from owner integration and deployment.

## Deploy

Apply only journal-store provisioning/migrations included in the user's scope
and qualified by the exact validation evidence. Use the existing separate-owner
init/migrate path. There is no current journal AWS rollout command; report that
gap if rollout is requested. This mode does not submit a feed, instantiate
Bookkeeping or MDM, change Rules approval or drain another owner's outbox.
An existing approval/authorization remains effective within its original scope.

## Status

```bash
edgar-warehouse change-journal status --source <source> --feed <feed>
edgar-warehouse change-journal events --run-id <root> --limit 20
edgar-warehouse change-journal verify <receipt.json>
```

Source/feed filters are optional. Event-id inspection cursors are not completion
watermarks; a sparse listing cannot prove producer scope completeness.

## Recover delivery

Inspect the exact retained receipt and the owning producer's committed intent.
The journal verifies its stored envelope; it cannot prove or repair source or
business effects. The owner reconciles and retries the original key/envelope,
acknowledges only durable readback and retains its own fence. Journal outage,
conflicting content or corrupt evidence must leave intent pending.

Existing application-composed delivery routes are:

```bash
edgar-warehouse change-journal recover bookkeeping <run-id> --limit <bound>
edgar-warehouse change-journal recover mdm <batch-id> --worker <worker>
```

These execute owner recovery in `application.journal_recovery`, outside the
journal core. They deliver committed intent only; never silently start provider
work or redirect historical backlog. Preserve original roots and evidence.
Do not add Bookkeeping/MDM imports back into the journal to enable recovery.

## Result

Report scope, exact envelopes/receipts, journal checks, owner backlog and
remaining gaps. Receipt delivery proves durable journal storage, not business
completion. Keep skill validation, isolated journal qualification, owner
integration and live deployment separate. Codex owns this work; no Claude
assignment exists without an explicit operator instruction.
