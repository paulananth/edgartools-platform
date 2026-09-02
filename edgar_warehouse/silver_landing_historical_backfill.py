"""One-time backfill: seed Snowflake silver landing with pre-existing silver
content that predates the landing-zone write path.

duckdb-retirement map: `_stage_submission_locked`'s caller
(`warehouse_orchestrator.py`'s `all_same` check) skips
`merge_company`/`merge_addresses`/`merge_former_names`/`merge_submission_files`
entirely whenever a CIK's submissions.json content hash is unchanged since its
last sync -- true for nearly the whole already-loaded universe. Those four
merges were the only places `sec_company`/`sec_company_address`/
`sec_company_former_name`/`sec_company_submission_file` got tracked into the
landing-zone buffer (via `@track_landing_rows`), so a CIK whose company
metadata was last written before the landing-zone write path existed never
reached Snowflake silver through the ongoing incremental path.

silver-snowflake-migration map, Ticket 15: the identical shape applies well
beyond company metadata. Every `@track_landing_rows`/`@track_landing_row`
write in `silver_store.py` only fires when its owning merge/upsert method
actually executes -- and most of those methods are themselves gated by an
idempotent skip-if-unchanged/skip-if-already-loaded check (this repo's own
"SEC data idempotency" policy: loaders skip already-captured artifacts by
default). Confirmed live 2026-09-01: `sec_adv_filing` and `sec_financial_fact`
had **zero** Parquet exports ever land in S3 despite tens of thousands of
rows in canonical DuckDB silver; `sec_ownership_non_derivative_txn` had 7
files covering 36 of 78,096 rows. The Snowflake-side ingestion mechanism
itself is not the problem -- `sec_company`/`sec_company_ticker` prove it
works -- the gap is entirely on the write side: bulk-historical content
loaded before (or without re-triggering) the landing-zone write path simply
never gets a chance to flow through it.

**Two bugs found running the first version of this module live against
prod (2026-09-01), both fixed here:**

1. The original implementation hydrated via `_hydrate_all_shards`, which
   reads the CIK-sharded `shard-*.duckdb` files DuckDB Retirement Ticket 06
   already retired as a write target. Live prod still has these files
   sitting in S3 -- last written 2026-08-20, 12+ days stale as of this
   fix -- so the backfill was silently reading stale data instead of the
   current canonical monolith `silver.duckdb` (updated daily). Fixed:
   hydrate the monolith directly via
   `_hydrate_silver_database_from_storage`, the same helper every other
   command uses to read canonical silver, and fail loud if it's genuinely
   absent rather than falling back to a stale alternative.
2. The original implementation buffered every table's rows as Python dicts
   in memory (`reader.fetch("SELECT * FROM {table}")` into a shared
   `LandingExportBuffer`, one single `write_landing_export()` call at the
   very end) before writing anything to S3. This OOM-killed a real prod run
   at 8192MB -- the largest task profile this platform has -- on
   `sec_thirteenf_holding` alone (~6.8M rows), before even reaching the
   other ~5 tables with meaningful row counts. Fixed: each table streams
   straight from DuckDB to a local Parquet file via `COPY (SELECT ...) TO
   ... (FORMAT PARQUET)`, which DuckDB executes internally without ever
   materializing the result set as Python objects, then that file is
   uploaded with `StorageLocation.upload_file` (a genuine chunked stream,
   not an in-memory buffer) and deleted locally before the next table
   starts. Peak memory is now bounded by DuckDB's own internal Parquet
   writer, not by this process's Python heap holding millions of row-dicts.

This module reads every table in `_BACKFILL_TABLES` directly from the
current canonical DuckDB silver monolith and re-emits each row as-is into
Snowflake silver landing, bypassing every merge-level skip gate entirely --
a one-time seed, not a new ongoing write path. Safe to re-run: the landing
zone is append-only with latest-parse_sequence-wins collapse in dbt, so a
second run just adds a newer, identical snapshot that wins the same way.
`sec_company_ticker` is deliberately excluded -- its landing shape isn't a
raw DuckDB row (see `replace_company_tickers`'s own inline enrichment,
silver-snowflake-migration Ticket 14), and it already has healthy live
coverage through `seed-universe`'s own export path, so it doesn't have this
gap.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edgar_warehouse.mdm.silver_parity import PARITY_TABLES

# Every table verify-silver-parity tracks, except sec_company_ticker (see
# module docstring for why). Deliberately a superset that includes tables
# already covered by the original narrower backfill (sec_company and its
# three siblings) -- re-running for them is a harmless no-op duplicate seed,
# and keeping one table list (rather than "the original four" plus "the rest")
# avoids a second place this list could drift from PARITY_TABLES.
_BACKFILL_TABLES: tuple[str, ...] = tuple(
    table for table in PARITY_TABLES if table != "sec_company_ticker"
)


def run_silver_landing_historical_backfill(context: Any, run_id: str) -> dict[str, Any]:
    """One-time seed of `_BACKFILL_TABLES` into Snowflake silver landing from
    the current canonical DuckDB silver monolith.

    Streams each table straight from DuckDB to a local Parquet file, then
    uploads that file -- never materializes a whole table as Python row
    objects (see module docstring, bug 2).
    """
    from edgar_warehouse.application.warehouse_orchestrator import (
        WarehouseRuntimeError,
        _emit_pipeline_event,
        _hydrate_silver_database_from_storage,
        _resolve_export_business_date,
    )
    from edgar_warehouse.infrastructure.dataset_path_catalog import (
        default_capture_spec_factory,
        default_path_resolver,
    )
    from edgar_warehouse.serving.silver_landing_writer import _landing_run_manifest
    from edgar_warehouse.silver_support.sharded_reader import ShardedSilverReader

    if context.silver_landing_export_root is None:
        raise WarehouseRuntimeError(
            "SILVER_LANDING_EXPORT_ROOT is required for backfill-silver-landing-historical"
        )

    started_at = datetime.now(UTC)

    # The current canonical monolith -- not the CIK-sharded shard-*.duckdb
    # files (see module docstring, bug 1). _hydrate_silver_database_from_storage
    # is the same helper every other command uses to read canonical silver.
    monolith_local_path = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))
    if not monolith_local_path.exists():
        _hydrate_silver_database_from_storage(context)
    if not monolith_local_path.exists():
        raise WarehouseRuntimeError(
            "No canonical silver.duckdb found to backfill from -- has bronze/silver ever run?"
        )

    now = datetime.now(UTC)
    business_date = _resolve_export_business_date(
        command_name="backfill-silver-landing-historical", scope={}, now=now
    )
    spec_factory = default_capture_spec_factory()

    source_counts: dict[str, int] = {}
    landing_export_counts: dict[str, int] = {}
    table_writes: list[dict[str, Any]] = []

    reader = ShardedSilverReader([str(monolith_local_path)])
    tmp_dir = Path(tempfile.mkdtemp(prefix="silver-landing-historical-"))
    try:
        for table in _BACKFILL_TABLES:
            count_rows = reader.fetch(f"SELECT COUNT(*) AS n FROM {table}")  # noqa: S608 -- table is from _BACKFILL_TABLES, never user input
            count = count_rows[0]["n"] if count_rows else 0
            source_counts[table] = count
            if count == 0:
                continue

            local_parquet_path = tmp_dir / f"{table}.parquet"
            # Streams via DuckDB's own COPY internally -- unlike .fetch(),
            # never materializes the result set as a Python list of dicts
            # (see module docstring, bug 2). Kept on ShardedSilverReader
            # itself (not called via reader._conn directly) so its lock
            # discipline stays in one place -- see
            # ShardedSilverReader.copy_table_to_parquet's own docstring.
            reader.copy_table_to_parquet(table, str(local_parquet_path))

            spec = spec_factory.snowflake_export_table(
                table_path=table, business_date=business_date, run_id=run_id
            )
            context.silver_landing_export_root.upload_file(spec.relative_path, local_parquet_path)
            local_parquet_path.unlink()

            landing_export_counts[table] = count
            table_writes.append(
                {
                    "file_count": 1,
                    "relative_path": spec.relative_path,
                    "row_count": count,
                    "table_name": table,
                }
            )
    finally:
        reader.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if table_writes:
        manifest = _landing_run_manifest(
            environment_name=context.environment_name,
            command_name="backfill-silver-landing-historical",
            run_id=run_id,
            business_date=business_date,
            now=now,
            table_writes=table_writes,
        )
        manifest_relative_path = default_path_resolver().snowflake_export_run_manifest_path(
            workflow_name="silver_landing_backfill_silver_landing_historical",
            business_date=business_date,
            run_id=run_id,
        )
        context.silver_landing_export_root.write_json(manifest_relative_path, manifest)

    _emit_pipeline_event(
        "silver_landing_historical_backfill_completed",
        run_id=run_id,
        source_counts=source_counts,
        landing_export_counts=landing_export_counts,
    )

    return {
        "command": "backfill-silver-landing-historical",
        "run_id": run_id,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "source_counts": source_counts,
        "landing_export": landing_export_counts,
    }
