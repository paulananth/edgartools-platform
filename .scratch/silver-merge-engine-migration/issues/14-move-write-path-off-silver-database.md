# 14 — Move the write path into a store-free module

**Type:** task

**Status:** open

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
