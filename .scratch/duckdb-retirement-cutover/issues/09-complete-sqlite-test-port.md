# 09 — Complete the Local Test-Suite Port to SQLite

**What to build:** DuckDB Retirement's Ticket 05 (wayfinder decision) found
56 DuckDB-touching test files and split them into four groups: ~8 need no
SQL engine at all (delete/repoint at the final object type), ~5-6 retire
along with the dbt gold cutover, ~4 rewrite against the MDM reader cutover,
and ~35-38 — the real decision — port to plain stdlib SQLite (no
ORM/SQLAlchemy), dialect-checked clean once [Ticket 01](
01-rewrite-daily-index-checkpoint-qualify-clause.md)'s `QUALIFY` rewrite
lands.

This ticket is the cleanup pass: after Tickets 01–03 and 05–07 and the
external `dbt-gold-silver-rewiring` chain land (each carrying its own test
changes as part of its own work), re-survey the DuckDB-touching test file
list and port whatever operational-bookkeeping coverage is still left
uncovered to SQLite. Don't re-port tests that another ticket already
rewrote as part of its own scope — this ticket closes the remainder, not
the whole 56. Does not need [Ticket 04](
04-provision-live-bookkeeping-postgres.md) — local SQLite tests don't touch
live Snowflake, only the store class and repointed callers Tickets 02/03
already land.

**Blocked by:** [Ticket 01](01-rewrite-daily-index-checkpoint-qualify-clause.md),
[Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md),
[Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md),
[Ticket 05](05-cutover-mdm-reader-to-snowflake.md),
[Ticket 06](06-retire-bootstrap-batch-sharding.md),
[Ticket 07](07-retire-ddl-generator-scripts.md), and the
`dbt-gold-silver-rewiring` map's full 7-ticket chain (`.scratch/
dbt-gold-silver-rewiring/issues/01`-`07`, all `ready-for-agent` as of this
writing) — each of those lands its own portion of the 56-file list as part
of its own scope; this ticket needs the accurate remainder, not a stale
count.

**Status:** blocked

- [ ] Re-survey the 56-file DuckDB-touching test list against what Tickets
      01–03, 05–07, and the `dbt-gold-silver-rewiring` chain already closed
- [ ] Every remaining operational-bookkeeping test file (leases,
      checkpoints, idempotency gates) ports to stdlib SQLite, no ORM
- [ ] Every ~8 no-SQL-engine-needed file has its DuckDB dependency removed
      or repointed at the final object type
- [ ] Full test suite green, zero `import duckdb` remaining in `tests/`
