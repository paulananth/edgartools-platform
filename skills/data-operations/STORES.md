# Apply store DDL and qualify Silver storage

Part of the `data-operations` skill: [SKILL.md](SKILL.md) says when to read this.

## Apply store DDL

This skill applies DDL. Data-profiling writes a logical silver spec and does
not. MDM engineering writes the MDM migration files and does not apply a
profile's silver spec.

Use the operator's selected engine for each store: PostgreSQL, MySQL or SQL
Server Express. Resolve the connection's dialect and verify it matches that
selection before writing. For an all-three request, track each engine's
schema and domain state separately. Connectivity alone proves no schema or
merge capability. Preserve the selected engine when a command refuses it;
route the missing implementation to its owning engineering work instead of
substituting PostgreSQL.

A hosted instance is initialized by [the runbook](RUNBOOK.md#initialize-a-hosted-store).

Apply these five schemas into databases that
[data-platform](../data-platform/SKILL.md) already created: `mdm`, `rdm`,
`bookkeeping`, `change_journal`, and `silver`. This skill does not create
the databases or the engines. Read each command's `--help` before the
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

| Schema | Command | Owner connection |
|---|---|---|
| MDM | `edgar-warehouse mdm migrate --application-role <role>` | `MDM_DATABASE_URL` |
| RDM | `edgar-warehouse rdm init --runtime-role <role>`, then `rdm migrate` | `RDM_MIGRATION_DATABASE_URL` |
| Bookkeeping | `edgar-warehouse bookkeeping init --runtime-role bookkeeping_runtime`, then `bookkeeping migrate`. The database name is `bookkeeping`. | `BOOKKEEPING_DATABASE_URL` |
| Change Journal | `edgar-warehouse change-journal init --runtime-role <role>`, then `change-journal migrate`. The database name is `change_journal`. | `CHANGE_JOURNAL_MIGRATION_DATABASE_URL` |
| Silver | `edgar-warehouse silver init --runtime-role <role>`, then `silver migrate` | `SILVER_MIGRATION_DATABASE_URL` |

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
