# 01 — Fix migration 010's DuckDB commit-conflict crash

Type: task

**What to build:** stop `daily-incremental` (and every other warehouse
command that hydrates a fresh local Silver DuckDB) from crashing while
applying schema migration `010_company_facts_retirement_columns`
(Ticket 33) against prod's real, populated `sec_financial_fact` table.

**Blocked by:** None — can start immediately.

**Status:** resolved

## Answer

Root cause, confirmed via a deterministic repro (1-row table, isolated in
under a second): DuckDB 1.5.2's `ALTER TABLE ADD COLUMN ... DEFAULT <expr>`
against a table with existing rows triggers an internal row-backfill
rewrite that bumps the table's version. A second `ALTER TABLE` against that
same table, inside the same explicit transaction, then trips DuckDB's
commit-time conflict check against that bump —
`_duckdb.TransactionException: ... another transaction has altered this
table`. Migration 010 issues exactly this shape (3 `ADD COLUMN` statements
per table, two default-bearing) inside `_apply_schema_migration`'s shared
transactional wrapper. No existing test caught it because every prior test
opened this migration against an empty pre-migration table (0 rows never
triggers the row-backfill path — confirmed empirically).

Fix: `_schema_migrations()`'s tuples gained a 4th field,
`requires_transaction` (`True` everywhere except migration 010's entry).
`_apply_schema_migration` only wraps `migrate()` in `BEGIN`/`COMMIT`/
`ROLLBACK` when `True`; migration 010 runs in autocommit mode instead —
safe because every statement it issues is `ADD COLUMN IF NOT EXISTS`,
already idempotent under interrupt-and-retry. Deliberately **not** applied
globally: `_backup_and_recreate_table`-based migrations (001/002/007)
genuinely need the shared transactional envelope for their
RENAME→CREATE→INSERT sequence, which isn't safely retriable without it.

New regression test,
`test_migration_010_adds_retirement_columns_to_populated_tables`
(`tests/unit/test_silver_store_schema_migration.py`) — builds a
pre-Ticket-33 store with a populated row in each affected table, confirmed
to reproduce the crash before the fix and pass after (verified both ways).
Full repo suite green.

Full write-up: CLAUDE.md's "Migration 010 DuckDB commit-conflict 5-whys."

**Merged:** PR [#482](https://github.com/paulananth/edgartools-platform/pull/482).
