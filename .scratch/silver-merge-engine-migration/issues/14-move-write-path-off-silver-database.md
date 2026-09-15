# 14 — Move the write path into a store-free module

**Type:** task

**Status:** resolved in code 2026-09-14.

## Question

Production code calls 34 `SilverDatabase` methods (2026-09-14 count): `close` (112 sites), the
`merge_*`/`mark_*`/`upsert_*`/`stage_*`/`replace_*` writers (one to five sites each),
`get_filing`/`get_filing_attachments`/`get_raw_object` (the in-run lookup, ADR 0011),
`get_table_counts` (one site, `warehouse_orchestrator.py`), and `fetch` (see Ticket 16 for the
local-store callers). 35 production modules import the class; 60 test files do.

Move `LandingExportBuffer` wiring, `_record_landing_passthrough`, the stamps/defaults helpers,
`_remember_in_run`/`_in_run_lookup` and the three `get_*` readers into a store-free module that
keeps the same method names and the `open_silver_database(silver_root, landing_export=...)`
opener, so the call sites do not churn in the same diff as the engine deletion. `SilverDatabase`
becomes an alias or thin subclass until Ticket 17 deletes it. `get_table_counts` on the local
store returns nothing useful since Ticket 10; drop it and its merge into the run summary.

**Blocked by:** [Ticket 13](13-duckdb-free-silver-schema-snapshot.md).

## Plan (2026-09-14)

Checked by AST: every writer and in-run reader the call sites use is already free of `self._conn`;
only `close`, `fetch`, `get_table_counts`, `_table_columns`, the migrations and the shard-reconcile
helpers touch DuckDB. So:

1. New `edgar_warehouse/silver_landing_store.py`, class `SilverLandingStore`: `__init__(*,
   landing_export=None)`, no-op `close()`, `_in_run_rows`, the passthrough, stamps/defaults, the
   in-run lookup, `get_filing`/`get_filing_attachments`/`get_raw_object`, and every `merge_*`/`mark_*`/
   `upsert_*`/`stage_*`/`replace_*` writer — moved verbatim (AST-extracted source segments), with
   `_IN_RUN_LOOKUP_TABLES` and whatever module constants they reference.
2. `SilverDatabase(SilverLandingStore)` keeps the DuckDB parts (`_conn`, `_DDL`, migrations, `fetch`,
   `_table_columns`, shard reconcile). `open_silver_database` still returns it.
3. `get_table_counts` on the local store: dropped, and the orchestrator's run-summary merge with it.
4. Tests: existing suites cover the moved methods unchanged; add one that `SilverLandingStore` alone
   (no DuckDB file) records a row through a writer and answers a same-run `get_filing`.

## Answer

Resolved 2026-09-14 in code, as planned.

- `edgar_warehouse/silver_landing_store.py`: `SilverLandingStore` with 46 methods AST-extracted
  verbatim from `SilverDatabase` (the review diffed them: identical), plus its own `__init__`
  (`landing_export`, `_in_run_rows`), a no-op `close()` and a no-op `_shard_advisory_lock`. The
  old file lock guarded concurrent local DuckDB writers, which no longer exist: every writer
  `stage_submission` reaches is the in-memory passthrough, and both callers run on the main
  thread. `_IN_RUN_LOOKUP_TABLES` and `_INSTANT_FACT_PERIOD_START_SENTINEL` moved with them.
- `SilverDatabase(SilverLandingStore)` keeps `_conn`, `_DDL`, the migrations, `fetch`,
  `_table_columns`, the file-lock override and the shard-reconcile helpers. `open_silver_database`
  and the `silver.py` shim are unchanged, so no call site moved. `super().__init__` runs before
  `_ensure_schema_evolution` (migrations read neither attribute).
- `SilverDatabase.get_table_counts` deleted with `test_silver_store_counts.py`; the run summary's
  `silver_table_counts` is bookkeeping's 10 Postgres tables alone (every consumer is a pass-through
  into events/manifests; nothing gated on it). The manifest key still says "silver" — noted, left.
- Tests: `tests/unit/test_silver_landing_store.py` (a writer records with no database; same-run
  `get_filing` answers; NOT NULL raises; no buffer records nothing; `SilverDatabase` is-a
  `SilverLandingStore`). Four run-manifest test files lost their `fake_db.get_table_counts` stubs.
  Full suite (integration excluded): 3468 passed before the review cleanups; touched suites re-run
  green after.
- Reviews: `/gof-refactor-reviewer` before (inheritance is the expand step; Ticket 17 contracts) and
  the three-axis `/code-review` after: Standards 4 judgement calls (orphaned section banners, a
  stale `SilverDatabase._record_landing_passthrough` doc reference, one missed stub sweep, a
  vestigial `getattr`), all applied; Spec 0; GoF 0.
- For Ticket 17: `LandingExportBuffer` and `_in_run_rows` carry no lock of their own, so a future
  threaded writer would have no serialization; `_INSTANT_FACT_PERIOD_START_SENTINEL` is also defined
  in `parsers/financials.py` (pre-existing duplication).
