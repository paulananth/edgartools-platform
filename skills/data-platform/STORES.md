# Apply store DDL and qualify Silver storage

Part of the `data-platform` skill: [SKILL.md](SKILL.md) says when to read this.

## Apply store DDL

**Only two skills create tables.** Data-platform creates every store's schema and
every committed silver table, when a store is set up. Data-onboarding creates a
new source's silver tables, once, before that source's first load
([TARGETS.md](../data-onboarding/TARGETS.md)). Nothing else does: a load, a run,
a worker, data-operations and every other skill create no table, in production
or anywhere else. A load that finds a table missing stops and names the command.
A temporary table of one session (a write's staging rows, a calculation's steps)
is not a table of the store and is allowed.

Data-profiling writes a logical silver spec and applies none. MDM engineering
writes the MDM migration files and does not apply a profile's silver spec.

Use the operator's selected engine for each store: PostgreSQL, MySQL or SQL
Server Express. Resolve the connection's dialect and verify it matches that
selection before writing. For an all-three request, track each engine's
schema and domain state separately. Connectivity alone proves no schema or
merge capability. Preserve the selected engine when a command refuses it;
route the missing implementation to its owning engineering work instead of
substituting PostgreSQL.

A hosted instance is initialized in the order of [the runbook](../data-operations/RUNBOOK.md#initialize-a-hosted-store); its schema and silver-table steps are this skill's.

Apply these five schemas into the databases [Setup](SKILL.md#0-setup) created: `mdm`, `rdm`,
`bookkeeping`, `change_journal`, and `silver`. Read each command's `--help` before the
first use. The required initialization path uses the same logical schema
and supported command interface with a storage adapter for the selected
engine. [sql-writer](../sql-writer/SKILL.md) compiles portable tables and
queries; the migration owns installation, grants, checksums and readback.
MDM's shared merge behavior and storage-adapter requirements belong to
[MDM engineering](../mdm-engineering/SKILL.md#database-agnostic-merge-logic).

**Check support per store and build.** Connection acceptance does not establish
initialization or normal-caller support. Silver implements PostgreSQL and MySQL;
SQL Server Silver remains deferred. For every store, verify its selected-engine
migration, restricted-role operations and populated recovery before claiming
readiness. Route a missing capability to engineering while leaving that target
incomplete; retain the selected engine instead of substituting PostgreSQL.

Use the owner connection and runtime-role arguments from
[Connection URLs and environment](SKILL.md#connection-urls-and-environment).
That section owns role provisioning and command-specific connection selection,
including the hosted Bookkeeping control group.

| Schema | Command |
|---|---|
| MDM | `edgar-warehouse mdm migrate --application-role <role>` |
| RDM | `edgar-warehouse rdm init --runtime-role <role>` |
| Bookkeeping | `edgar-warehouse bookkeeping init --runtime-role <role>`. The database name is `bookkeeping`. |
| Change Journal | `edgar-warehouse change-journal init --runtime-role <role>`. The database name is `change_journal`. |
| Silver | `edgar-warehouse silver init --runtime-role <role>` |

`init` is the whole step on a fresh store. `migrate` (each store has one) applies a schema file that arrives later and
prints the same checksums when nothing has.

**Where each table's shape is written.** Each store's definition sits beside the code that writes and migrates it, so
the two change in one commit; no second copy exists to drift. Read the table's columns there, or in the Data Catalog
for the published tables.

| Store | Definition |
|---|---|
| MDM | `edgar_warehouse/mdm/migrations/schema.sql`, and `registration_authority.sql` for the registration login |
| RDM | `edgar_warehouse/rdm/migrations/schema.sql`; one `mysql-*.sql` file per MySQL version |
| Rules | the `rules_used` table, written in Python (`edgar_warehouse/rules/db.py`) so one definition serves every dialect |
| Bookkeeping | `edgar_warehouse/bookkeeping/clean/migrations/schema.sql`, with `mysql-v1.sql` |
| Change Journal | `edgar_warehouse/change_journal/migrations/schema.sql`; `native/` holds one file per dialect |
| Silver, fixed part | `edgar_warehouse/silver_writer/migrations/schema.sql`, with `mysql-v1.sql` |
| Silver, one table per source | `rules/sources/<source>/silver-<table>.yaml` (and `rules/silver/`): a spec stewards review, registered as DDL by `deploy-silver.sh` for every dialect |

Then every committed silver table, with the silver owner's login:
`bash infra/scripts/deploy-silver.sh <local environment name | path to connection.env>`. It registers each
`rules/sources/*/silver-*.yaml` and `rules/silver/silver-*.yaml`; an unchanged spec changes nothing and a changed one
is refused (register it as a new table).

The runtime role exists, has no administrative privileges, and is not the
migration login. Done when the selected engine's migration history matches
the build, required objects and grants read back correctly, and restricted
runtime operations work. `edgar-warehouse doctor` shows the stores that
answer; it does not prove complete schemas or database-agnostic merging.

## Qualify Silver storage

Use retained applicable evidence and the normal installed caller on each selected
engine. Check owner-only initialization and registration, interrupted DDL repair,
configured partition indexes, populated reruns and restricted runtime rights.
Prove append/upsert/snapshot, quality, rollback, unchanged replay and actual master
lookup/refresh; an ID callback alone is not the real master-link boundary.

Test exact values through file parsing, binding **and readback**. An exact database
column cannot repair decimal digits already lost to a JSON float decoder. Include
nested JSON decimals, integer bounds and decimal-scale refusal independent of
Python's arithmetic context. Keep original key distinctions when an index uses a
prefix or digest; the full value remains authoritative.

Elapsed durations and calendar intervals are different contracts. MySQL Silver
currently preserves elapsed microseconds and does not support calendar-month/year
storage. Refuse unsupported forms atomically, retain source evidence and record
that engine's gap. Never silently turn a calendar month into a fixed day count.
Complete other independent qualification while that capability is deferred.
