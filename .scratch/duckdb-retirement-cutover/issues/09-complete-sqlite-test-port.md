# 09 — Complete the Local Test-Suite Port to SQLite

**What to build:** DuckDB Retirement's Ticket 05 (wayfinder decision) found
56 DuckDB-touching test files and split them into four groups: ~8 need no
SQL engine at all (delete/repoint at the final object type), ~5-6 retire
along with the dbt gold cutover, ~4 rewrite against the MDM reader cutover,
and ~35-38 — the real decision — port to plain stdlib SQLite (no
ORM/SQLAlchemy), dialect-checked clean once [Ticket 01](
01-rewrite-daily-index-checkpoint-qualify-clause.md)'s `QUALIFY` rewrite
lands.

This ticket is the cleanup pass: after Tickets 01–03/13–15 and 05–07 and the
external `dbt-gold-silver-rewiring` chain land (each carrying its own test
changes as part of its own work), re-survey the DuckDB-touching test file
list and port whatever operational-bookkeeping coverage is still left
uncovered to SQLite. Don't re-port tests that another ticket already
rewrote as part of its own scope — this ticket closes the remainder, not
the whole 56. Does not need [Ticket 04](
04-provision-live-bookkeeping-postgres.md) — local SQLite tests don't touch
live Snowflake, only the store class and repointed callers Tickets
02/03/13/14/15 already land.

**Blocked by:** [Ticket 01](01-rewrite-daily-index-checkpoint-qualify-clause.md),
[Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md),
[Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md),
[Ticket 13](13-rewrite-cross-store-join-sites.md),
[Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md),
[Ticket 15](15-repoint-remaining-bookkeeping-callers.md),
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
      01–03/13–15, 05–07, and the `dbt-gold-silver-rewiring` chain already
      closed
- [ ] Every remaining operational-bookkeeping test file (leases,
      checkpoints, idempotency gates) ports to stdlib SQLite, no ORM
- [ ] Every ~8 no-SQL-engine-needed file has its DuckDB dependency removed
      or repointed at the final object type
- [ ] Full test suite green, zero `import duckdb` remaining in `tests/`

**Addendum (2026-09-06): re-survey done, and this ticket's original premise
no longer holds as written.**

- **File count shrank sharply already, before any SQLite-port work started.**
  A fresh survey found ~39 DuckDB-touching test files remaining, down from
  the original 56 — not from porting, but from two rounds of dead-code
  deletion this session found and removed: 25 `SilverDatabase` bookkeeping
  methods (`get_discovery_checkpoint`, `claim_discovery_ciks`,
  `acquire_pipeline_run_lease`/`release_pipeline_run_lease`/
  `get_pipeline_run_lease`, `start_sync_run`/`complete_sync_run`,
  `start_pipeline_run`/`complete_pipeline_run`, `get_pipeline_run`,
  `record_gold_manifest`/`get_gold_manifest`, `upsert_source_checkpoint`/
  `get_source_checkpoint`, `upsert_company_sync_state`/`get_company_sync_state`,
  `seed_company_sync_state_bulk`, `get_active_ciks`, `get_tracked_ciks`, plus
  6 more found in a second sweep: `merge_daily_index_filings`,
  `get_daily_index_filings`, `upsert_daily_index_checkpoint`,
  `get_daily_index_checkpoint`, `get_last_successful_checkpoint_date`,
  `get_ciks_with_bronze`) — every one superseded by Tickets 02/03/13/14/15's
  Postgres-backed `BookkeepingStore`, with zero remaining external callers
  and a confirmed live `bookkeeping.X(...)` equivalent at every real
  production call site (PRs #552 and the follow-up deleting the 6). Their
  test files (whole files, or individual dead test functions) were deleted
  or fixed alongside — this is exactly the "port whatever coverage is still
  left uncovered" work this ticket describes, just arriving as dead-code
  removal rather than a SQLite rewrite, since the coverage in question no
  longer needs porting anywhere — it's gone, and its real behavior is
  already covered by `tests/bookkeeping/test_store.py`.
- **A real architectural blocker exists for whatever remains.**
  `merge_daily_index_filings`'s shared bulk-write helper pattern (used by
  several still-alive content-merge methods, e.g. `merge_filings`,
  `merge_adv_filings`) relies on `self._conn.register("_table_name",
  arrow_table)` — a DuckDB-only API for registering an in-memory PyArrow
  table as a queryable object, with no `sqlite3` equivalent. Any surviving
  test that exercises one of these bulk-write methods cannot be ported to
  SQLite as a test-only change; it would require refactoring
  `SilverDatabase`'s bulk-write internals to be backend-agnostic first — a
  production-code decision outside this ticket's original "just port the
  tests" framing, and arguably within [Ticket 10](
  10-atomic-write-path-cutover.md)'s scope instead, since Ticket 10 deletes
  these methods wholesale anyway rather than porting them.
- **Net effect:** this ticket's real remaining scope is smaller and
  differently shaped than its original text describes — likely closer to
  "confirm the remaining ~39 files are either already-dead-and-deletable,
  already covered by `BookkeepingStore` tests, or blocked on Ticket 10's
  wholesale deletion" than "port ~35-38 files to SQLite." Re-scoping this
  ticket's own checklist against the current file list is the next step
  before resuming it, not resuming the SQLite-port work as originally
  scoped.
