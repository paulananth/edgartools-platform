# 09 — Remove `duckdb` from `pyproject.toml`/`uv.lock` and delete the DuckDB engine

**Type:** task — the destination.

## Question

With every writer landing-only and every reader deleted, `SilverDatabase` is a DDL-and-migrations
shell around a `LandingExportBuffer`. Delete it: `silver_store.py`'s DuckDB engine and schema
migrations, `silver_protection.py` (`merge_candidate_into_canonical`, `PROTECTED_TABLE_REGISTRY`
— check what else imports the registry first; `test_silver_landing_export.py` uses it as the
landing-scope list), `application/silver_event_reducer.py` (out of scope for redesign here —
see the map's Out of scope; it leaves with the engine), `application/commands/migrate_silver_shards.py`,
`silver_landing_historical_backfill.py` (with `silver_support/sharded_reader.py`, its last
user after Ticket 08, plus that reader's tests in `test_sharding.py`, `test_fundamentals_modules.py`
and `test_adv_preflight.py`'s fixture), `scripts/ops/*.py`'s three DuckDB diagnostics,
`scripts/build_relationship_release_manifest.py` (already deleted by Ticket 11), then `duckdb>=1.0.0` itself and the warehouse
deps image (`uv.lock` change → rebuild both deps images per CLAUDE.md's table).

`LandingExportBuffer` + the `_record_landing_passthrough` defaults/stamps/NOT-NULL sets are the
only thing the writers still need — they move to a store-free module (name TBD when this lands).
Ticket 06d's in-run lookup (`_IN_RUN_LOOKUP_TABLES`, `_remember_in_run`, `_in_run_lookup`) moves
with them. It takes its row shape (every column, in order) from `_table_columns`, which reads the
DuckDB DDL, so that column list needs a DuckDB-free source too.

Two more DuckDB dependencies, found 2026-09-14 and not covered above:

- **`compute-windows` uploads the local DuckDB file.** `_execute_warehouse_bronze_capture`
  passes the local `silver/sec/silver.duckdb` to `persist_run_manifest` as
  `reference_snapshot_file`, which copies its bytes to S3 as
  `identity_refresh/runs/<run_id>/reference/reference_snapshot.duckdb` on every run. The
  manifest check only reads the snapshot's `sha256` and `path`, never the file itself. Decide
  what replaces it (a hash of the reference rows landed this run, or nothing) before the engine
  goes; with no DuckDB file the upload raises "identity refresh reference snapshot is missing".
- **`deploy-aws-application.sh` still injects `MDM_SILVER_DUCKDB`** (the `--mdm-silver-duckdb`
  flag, its default `s3://<warehouse-bucket>/warehouse/silver/sec/silver.duckdb`, and the MDM
  task environment and `silver_duckdb` definition field). Nothing else in the repo reads it (only
  historical `.planning/` notes mention it). Remove it with the engine.

Also: `scripts/ops/` has five scripts that import `duckdb`, not three (`check-issued-by-coverage.py`,
`check-neo4j-e2e.py`, `diagnose-mdm-run.py`, `diagnose-silver-anomalies.py`, `verify-counts.py`),
and `table-reconcile` (`table_reconciliation/cli.py`) hydrates `silver.duckdb` to compare with
Snowflake — it is the tool duckdb-retirement-cutover Ticket 19 needs, so it leaves after Ticket 21.

**Blocked by:** [Ticket 07](07-delete-confirmed-dead-duckdb-readers.md),
[Ticket 08](08-delete-sharded-reader-and-parity-tooling.md), duckdb-retirement-cutover
[Ticket 21](../../duckdb-retirement-cutover/issues/21-apply-duckdb-file-lifecycle-disposition.md)
(the old canonical S3 objects must be dispositioned before the tools that read them go), and
[Ticket 12](12-fundamentals-markers-landing-only.md) (`mark_entity_facts_refreshed`/
`mark_fundamentals_accession_processed` still write local DuckDB). Ticket 12 replaced the earlier
blocker, "the bootstrap-fundamentals-crash-resume map's marker move": DuckDB removal needs only
the landing-only switch, not that map's per-CIK resume ledger.
