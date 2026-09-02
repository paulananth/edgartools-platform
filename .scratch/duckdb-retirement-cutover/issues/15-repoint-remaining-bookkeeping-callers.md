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

**Status:** done (2026-08-31)

- [x] `verify_pipeline_run.py` and `drive_filing_discovery.py` repointed at
      `BookkeepingStore`. `verify_pipeline_run.py` turned out fully mechanical
      -- `db` became entirely unused once repointed, so its hydrate/open/
      close/publish DuckDB lifecycle was removed as a direct consequence (not
      touched-content, just now-dead code). `drive_filing_discovery.py` was
      NOT purely mechanical: `_load_sealed_discovery_rows`'s two bookkeeping
      calls are reached via a shared core (`run_gated_discovery_for_business_date`,
      12 flat params) with 3 real callers spanning 4 files
      (`drive_filing_discovery.py` itself, `warehouse_orchestrator.py`'s
      `_run_filing_artifact_gated_capture`, `acquisition/capture_parity.py`'s
      `run_dual_path_filing_artifact_parity` -- called in turn from `cli.py`'s
      `compare-filing-artifact-capture` handler). All 3 needed `bookkeeping`
      threaded through. A `/gof-refactor-reviewer` consult (this session, git-log
      evidence: 8 historical commits growing that function's param list across
      Tickets 16/29/20/24b4/46/48/38-51-53) confirmed adding `bookkeeping` as a
      13th flat param was the wrong move -- instead split the signature into
      `GatedDiscoveryResources` (open handles: context/db/bookkeeping/engine,
      caller-owned lifecycle) and `GatedDiscoveryScope` (9 per-call scalars),
      done as a 5-step behavior-preserving migration (add both types + a
      `run_gated_discovery(resources, scope)` wrapper delegating to the
      unchanged flat function -> migrate each of the 3 callers one at a time,
      running that caller's tests after each -> collapse the flat function and
      wrapper into one `run_gated_discovery` once no caller used the flat
      signature). `capture_parity.py`'s own `db.get_daily_index_filings` call
      (this ticket's own 2026-08-30 addendum item) fixed the same pass.
- [x] `validate_data_quality.py` and `silver_once.py` repointed using
      [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)'s
      `get_recent_successful_pipeline_runs`/`has_successful_parse_run`, raw
      SQL removed, test stubs updated (`_FakeBookkeeping` added to
      `test_silver_once.py`; `_patch_bookkeeping_store` helper added to
      `test_validate_data_quality.py`). Found and fixed a THIRD bookkeeping
      call in `silver_once.py` not listed in this ticket's original text:
      `daily_index_is_finalized` reads `sec_daily_index_checkpoint` via
      `db.get_daily_index_checkpoint` -- confirmed to have zero production
      callers (only its own unit test), so no live bug, but fixed anyway
      since it's a trivial one-line swap in a file already being edited.
      `has_successful_ownership_parse` stayed genuinely dual-parameter (`db`
      for its `sec_ownership_reporting_owner` content-table fallback,
      `bookkeeping` for the primary `sec_parse_run` check) -- not collapsible
      to one store.
- [x] `migrate_silver_shards.py`'s handling of the 11 table names reviewed;
      decision: **left as-is**, documented inline with a comment block above
      `CIK_DIRECT_TABLES`. Reasoning: this migration tool's whole job is
      faithfully copying whatever rows physically exist in a *source*
      silver.duckdb into 4 shards; removing the 7 bookkeeping-table entries
      from its routing config would silently DROP real historical data if an
      operator ever re-runs it against an older, pre-cutover monolith that
      still has genuine (not just frozen-stale) rows in these tables. Cost of
      leaving the entries as-is is zero -- nothing reads shards for these
      tables anymore post-repoint (a separate, already-tracked cleanup item
      covers `ShardedSilverReader._TABLES`'s own stale entries, per Ticket 14's
      deferred note).
- [x] `build_relationship_release_manifest.py` gets a working `BookkeepingStore`
      connection: `_load_silver_inputs` now takes a `bookkeeping` param, reads
      `bookkeeping.get_all_company_sync_states()` and filters by
      `tracking_status` in Python (no existing store method offered the exact
      status-list filter the raw SQL had), raw `sec_company_sync_state` query
      on the bare `duckdb.connect(...)` removed (the `sec_company_filing`
      query stays on that connection -- genuine DuckDB content table,
      unaffected). **Found and fixed via the mandated Spec-axis code review**
      (not caught before that pass): the script's real prod invocation path
      -- `mdm build-relationship-release-manifest`, an ad-hoc ECS task on the
      MDM task profile (`infra/scripts/deploy-aws-application.sh`'s
      `write_mdm_container_definitions`) -- never injected
      `BOOKKEEPING_DATABASE_URL` into that task's secrets at all (only the
      warehouse profile's `register_task_definition` had that wiring). Fixed
      by threading `BOOKKEEPING_POSTGRES_DSN_SECRET_ARN` (an existing,
      already-resolved shell variable) into `write_mdm_container_definitions`
      and appending the same optional `BOOKKEEPING_DATABASE_URL` secret entry
      the warehouse profile already uses. Without this fix the script would
      have raised `KeyError: 'BOOKKEEPING_DATABASE_URL'` on its actual prod
      path despite passing every test (tests monkeypatch `_bookkeeping_store()`
      entirely, so none of them exercised the real env-var lookup).
- [x] Full test suite green: 2861 passed, 5 skipped, 152 warnings, 35 subtests
      passed -- only the 8 pre-existing, unrelated Postgres-integration
      failures remain (`test_acquisition_ledger_postgres.py`/
      `test_conflict_postgres.py`, missing local migration column, not
      introduced by this ticket).

**Three-axis code review (Standards/Spec/GoF, mandated by CLAUDE.md) run before
commit.** GoF: clean, no findings. Standards: two minor, non-blocking notes
(missing return-type annotation on `cli.py`'s new `_bookkeeping_store()`;
`verify_pipeline_run()`'s `context` parameter is now unused inside the
function body, kept only to preserve the call signature) -- left as-is, judged
not worth the churn. Spec: the `BOOKKEEPING_DATABASE_URL` ECS-secret gap above
was this axis's one real finding, fixed prior to commit.

**Gap found and fixed later (2026-09-01), not in the original recon pass:**
`edgar_warehouse/application/workflows/drive_submissions_discovery.py` and
`drive_company_facts_discovery.py` both still called `db.get_tracked_ciks(...)`
against the local DuckDB `SilverDatabase` in `_resolve_ciks`'s `cik_list`-omitted
fallback branch -- neither file nor `get_tracked_ciks` is mentioned anywhere in
this ticket's text above, so this recon pass genuinely missed them (not a
deliberately-deferred item like the three call sites documented earlier in this
file). Because `sec_company_sync_state`'s DuckDB copy still physically exists
(just empty/stale in production, since every real write already goes through
`BookkeepingStore`), this didn't crash -- `get_tracked_ciks()` silently returned
an empty CIK universe instead. Found while scoping a request to remove the 11
bookkeeping tables' now-dead DuckDB DDL: that removal would have made the bug
loud (a `CatalogException` on a missing table) rather than fixing the silent
wrong-store read underneath it, so the read-repointing gap had to be fixed
first regardless of whether/when the DDL itself is ever removed. Fixed the same
way `drive_filing_discovery.py`/`bootstrap_fundamentals.py` already do: open a
second `bookkeeping = _bookkeeping_store()` connection alongside `db` (which
stays, still needed for the real SEC-content silver write path in both
functions) and read `sec_company_sync_state` from there. New regression tests
cover the `cik_list=None` path in both files -- every pre-existing test in
either file passes an explicit `cik_list`, so none of them exercised this
branch before. Full three-axis review re-run clean (no hard violations, no
scope creep, no structural findings). Commit `268b27f6`.
