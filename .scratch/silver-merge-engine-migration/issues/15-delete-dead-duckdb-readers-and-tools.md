# 15 — Delete the remaining DuckDB readers and tools

**Type:** task

**Status:** open

## Question

Delete, with their tests: `application/silver_event_reducer.py` (Out of scope on the map; leaves
with the engine), `application/commands/migrate_silver_shards.py`, `silver_support/sharded_reader.py`
and `silver_landing_historical_backfill.py` (its last user), the `table_reconciliation` package
(`table-reconcile` hydrates `silver.duckdb`; cutover Ticket 21's delete markers land within a day of
2026-09-14 20:29 ET, so it fails to hydrate before this slice runs — expected), and the five
`scripts/ops` DuckDB diagnostics (`check-issued-by-coverage.py`, `check-neo4j-e2e.py`,
`diagnose-mdm-run.py`, `diagnose-silver-anomalies.py`, `verify-counts.py`). Remove
`MDM_SILVER_DUCKDB` (`--mdm-silver-duckdb`, its default, the MDM task environment and the
`silver_duckdb` definition field) from `deploy-aws-application.sh`; nothing reads it.
`table_reconciliation/contracts.py` is the only production importer of `PROTECTED_TABLE_REGISTRY`
outside `silver_protection.py`.

Also, per [Ticket 16](16-retire-remaining-local-store-couplings.md)'s decisions (2026-09-14): drop
the `compute-windows` reference-snapshot upload and manifest field (`persist_run_manifest`'s
`reference_snapshot_file`, `reference_snapshot_path`, the `_valid_sha256` check) together with the
dead `reduce-identity-refresh` command and the zero-caller manifest readers; and retire
`parse-ownership-bronze` (CLI parser/handler, `_run_parse_ownership_bronze`, its two test files' parts).

**Blocked by:** [Ticket 14](14-move-write-path-off-silver-database.md).
