# 14 — Move the write path into a store-free module

**Type:** task

**Status:** claimed (2026-09-14)

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

## Plan (2026-09-14, in progress)

Checked by AST: every writer and in-run reader the call sites use is already free of `self._conn`;
only `close`, `fetch`, `get_table_counts`, `_table_columns`, the migrations and the shard-reconcile
helpers touch DuckDB. So:

1. New `edgar_warehouse/silver_landing_store.py`, class `SilverLandingStore`: `__init__(*,
   landing_export=None)`, no-op `close()`, `_in_run_rows`, the passthrough, stamps/defaults, the
   in-run lookup, `get_filing`/`get_filing_attachments`/`get_raw_object`, and every `merge_*`/`mark_*`/
   `upsert_*`/`stage_*`/`replace_*` writer — moved verbatim (AST-extracted source segments), with
   `_IN_RUN_LOOKUP_TABLES` and whatever module constants they reference.
2. `SilverDatabase(SilverLandingStore)` keeps the DuckDB parts (`_conn`, `_DDL`, migrations, `fetch`,
   `get_table_counts`, `_table_columns`, shard reconcile). `open_silver_database` still returns it.
3. `get_table_counts` on the local store: dropped, and the orchestrator's run-summary merge with it.
4. Tests: existing suites cover the moved methods unchanged; add one that `SilverLandingStore` alone
   (no DuckDB file) records a row through a writer and answers a same-run `get_filing`.
