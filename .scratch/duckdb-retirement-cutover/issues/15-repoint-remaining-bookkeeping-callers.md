# 15 — Repoint Every Remaining Bookkeeping-Table Caller

**Split from the original Ticket 03 during implementation (2026-08-29)** —
see [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)'s own
split note for the full context. Everything touching the 11 bookkeeping
tables that isn't a cross-store join site ([Ticket 13](
13-rewrite-cross-store-join-sites.md)) or `warehouse_orchestrator.py`
([Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md)).
Genuinely mixed in mechanical-ness — confirm each site actually is the
shape described below before assuming; a prior recon pass verified this
list but did not treat every claim as self-evidently correct.

**Addendum (2026-08-30, found while implementing [Ticket 14](
14-repoint-warehouse-orchestrator-bookkeeping-callers.md), not previously
listed here):** `edgar_warehouse/acquisition/capture_parity.py:333` —
`db.get_daily_index_filings(business_date)`. Surfaced via
`tests/application/test_dual_path_capture_parity.py`'s live-SEC-gated test
(`WAREHOUSE_LIVE_SEC=1`, skipped in normal CI), which calls both this
function and `warehouse_orchestrator._load_daily_index_for_date` against
the same business date — the latter is now fixed (Ticket 14, reads/writes
the bookkeeping store), but this one still reads `stg_daily_index_filing`
via its own `db: SilverDatabase` parameter. Once daily-index writes move
fully to the bookkeeping store, this call reads increasingly stale/empty
DuckDB data — a real latent gap, not a false positive, but left unfixed
here since it's outside Ticket 14's explicit `warehouse_orchestrator.py`
scope and this recon pass didn't originally catch it. Needs the same
`bookkeeping: BookkeepingStore` param treatment as
`drive_filing_discovery.py` below.

**Genuinely mechanical (repoint the method call, no new store method or
logic change):**

- `edgar_warehouse/application/commands/verify_pipeline_run.py` —
  `db.get_pipeline_run(run_id)` (:61), `db.record_pipeline_verification(...)`
  (:68). `db` is a small dedicated instance for this one command; confirm
  before editing, but this looks like the straightforward case.
- `edgar_warehouse/application/workflows/drive_filing_discovery.py` —
  `db.get_daily_index_checkpoint(business_date)` (:376),
  `db.get_daily_index_filings(business_date)` (:384). Confirm what `db` is
  in this scope (likely a small dedicated instance, same shape as
  `verify_pipeline_run.py`).

**Need a new store method plus a raw-SQL rewrite (methods land in
[Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md), used
here):**

- `edgar_warehouse/application/commands/validate_data_quality.py` —
  `_latest_previous_table_counts(db)` at :152 runs raw SQL: `SELECT
  pipeline_run_id, metrics_json FROM pipeline_run WHERE status IN
  ('succeeded','ok') AND metrics_json IS NOT NULL ORDER BY completed_at
  DESC NULLS LAST, started_at DESC LIMIT 10` via `db.fetch(...)` (`db: Any`,
  duck-typed). Repoint to
  `bookkeeping.get_recent_successful_pipeline_runs(limit=10)`.
- `edgar_warehouse/infrastructure/silver_once.py` —
  `has_successful_ownership_parse(db, ...)` runs raw SQL: `SELECT 1 AS ok
  FROM sec_parse_run WHERE accession_number=? AND parser_name=? AND
  parser_version=? AND status='succeeded' LIMIT 1` via generic
  `db.fetch(...)` (`db: Any`, also used with a plain `.fetch()`-having stub
  in tests — check those tests still make sense against the real store
  shape, not just the stub). Repoint to
  `bookkeeping.has_successful_parse_run(accession_number=..., parser_name=...,
  parser_version=...)`.

**Needs its own review, not a straight repoint:**

- `edgar_warehouse/application/commands/migrate_silver_shards.py` — the 11
  bookkeeping table names appear in what looks like a per-shard-migration
  handling list (~lines 44-102). Once these tables are never written to any
  DuckDB shard, this file's list of them needs its own review (does the
  whole per-table entry get removed, or does the file need a different kind
  of change?) — read the actual current logic before deciding, don't assume
  a straight repoint applies here.

**Needs a net-new dependency, not a repoint (biggest single-file item):**

- `edgar_warehouse/scripts/build_relationship_release_manifest.py` — opens
  its own bare `duckdb.connect(silver_db, read_only=True)`, no
  `SilverDatabase`/`ShardedSilverReader` at all. Raw SQL: `SELECT cik,
  last_main_sha256 FROM sec_company_sync_state [WHERE tracking_status IN
  (...)] ORDER BY cik`. This isn't "repoint an existing call" — it's adding
  an entirely new `BookkeepingStore` connection (and the credential/config
  it needs, e.g. `BOOKKEEPING_DATABASE_URL`) to a script that has never
  talked to Postgres before. Confirm how this script is actually invoked
  (CLI args, env vars available in its runtime context) before wiring the
  new dependency in, since its current invocation path may not already
  carry Postgres credentials the way `warehouse_orchestrator.py`'s ECS
  tasks do.

**Not real call sites (comment/docstring/false-positive-grep only — no
action needed, confirmed during the original recon pass):**
`edgar_warehouse/mdm/silver_parity.py` (comment only),
`edgar_warehouse/infrastructure/dataset_path_catalog.py` (comment only),
`edgar_warehouse/acquisition/discovery.py` (docstring only),
`edgar_warehouse/application/commands/__init__.py` and
`edgar_warehouse/cli.py` (matched the table-name grep only via the
unrelated `verify_pipeline_run` command/module name).

**Explicitly out of scope, per an earlier operator decision (not this
ticket, not [Ticket 08](08-build-table-specific-reconciliation-tooling.md)
either unless that ticket's own scoping picks them up):**
`scripts/ops/check-neo4j-e2e.py`, `scripts/ops/diagnose-silver-anomalies.py`,
`scripts/ops/verify-counts.py` — standalone operator diagnostic scripts
outside `edgar_warehouse/` that open a raw DuckDB connection for ad hoc,
human-run SQL against `sec_parse_run`, `sec_company_sync_state`,
`sec_sync_run`. Not part of the automated pipeline or test suite; deferred
per the operator's own answer during this ticket set's split discussion.

**Blocked by:** [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)

**Status:** blocked

- [ ] `verify_pipeline_run.py` and `drive_filing_discovery.py` repointed at
      `BookkeepingStore`, confirmed mechanical (no logic change needed)
- [ ] `validate_data_quality.py` and `silver_once.py` repointed using
      [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)'s
      two new methods, raw SQL removed, existing test stubs updated or
      confirmed still valid against the real store shape
- [ ] `migrate_silver_shards.py`'s handling of these 11 table names is
      reviewed and a decision made (removed / changed / left as-is with
      reasoning stated), not left ambiguous
- [ ] `build_relationship_release_manifest.py` gets a working
      `BookkeepingStore` connection (env var wiring confirmed for however
      this script is actually invoked in prod), raw `duckdb.connect(...)`
      call removed
- [ ] Full test suite green
