"""One-time backfill: seed Snowflake silver landing with pre-existing company
metadata that predates the landing-zone write path.

duckdb-retirement map: `_stage_submission_locked`'s caller
(`warehouse_orchestrator.py`'s `all_same` check) skips
`merge_company`/`merge_addresses`/`merge_former_names`/`merge_submission_files`
entirely whenever a CIK's submissions.json content hash is unchanged since its
last sync -- true for nearly the whole already-loaded universe. Those four
merges are the only places `sec_company`/`sec_company_address`/
`sec_company_former_name`/`sec_company_submission_file` ever get tracked into
the landing-zone buffer (via `@track_landing_rows`), so a CIK whose company
metadata was last written before the landing-zone write path existed may
never reach Snowflake silver through the ongoing incremental path. Confirmed
live: zero `sec_company` Parquet files had ever landed in S3, despite ~3,225
companies already resolved in MDM from DuckDB canonical content.

This module reads all four tables directly from the full DuckDB canonical
silver dataset (every shard, via `ShardedSilverReader`) and re-emits every
row as-is into the landing-zone buffer, bypassing the checksum gate entirely
-- a one-time seed, not a new ongoing write path. Safe to re-run: the landing
zone is append-only with latest-parse_sequence-wins collapse in dbt, so a
second run just adds a newer, identical snapshot that wins the same way.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_BACKFILL_TABLES: tuple[str, ...] = (
    "sec_company",
    "sec_company_address",
    "sec_company_former_name",
    "sec_company_submission_file",
)


def _fetch_all_rows(reader: Any, table: str) -> list[dict[str, Any]]:
    return reader.fetch(f"SELECT * FROM {table}")


def run_silver_landing_company_backfill(context: Any, run_id: str) -> dict[str, Any]:
    """One-time seed of company-metadata landing tables from DuckDB canonical.

    Reads across every shard rather than the single active shard a normal
    command touches, since company rows may live in any CIK-range shard and
    this backfill needs the complete universe in one pass.
    """
    from edgar_warehouse.application.warehouse_orchestrator import (
        WarehouseRuntimeError,
        _emit_pipeline_event,
        _hydrate_all_shards,
        _resolve_export_business_date,
    )
    from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
    from edgar_warehouse.serving.silver_landing_writer import write_landing_export
    from edgar_warehouse.silver_support.sharded_reader import ShardedSilverReader

    if context.silver_landing_export_root is None:
        raise WarehouseRuntimeError(
            "SILVER_LANDING_EXPORT_ROOT is required for backfill-silver-landing-company-metadata"
        )

    started_at = datetime.now(UTC)
    shard_paths = [path for path in _hydrate_all_shards(context) if path is not None]
    if not shard_paths:
        raise WarehouseRuntimeError(
            "No silver shards found to backfill from -- has bronze/silver ever run?"
        )

    landing_export = LandingExportBuffer()
    source_counts: dict[str, int] = {}
    reader = ShardedSilverReader(shard_paths)
    try:
        for table in _BACKFILL_TABLES:
            rows = _fetch_all_rows(reader, table)
            source_counts[table] = len(rows)
            if rows:
                landing_export.record(table, rows)
    finally:
        reader.close()

    now = datetime.now(UTC)
    business_date = _resolve_export_business_date(
        command_name="backfill-silver-landing-company-metadata", scope={}, now=now
    )
    landing_export_counts = write_landing_export(
        landing_export,
        context.silver_landing_export_root,
        run_id=run_id,
        business_date=business_date,
        command_name="backfill-silver-landing-company-metadata",
        environment_name=context.environment_name,
        now=now,
    )

    _emit_pipeline_event(
        "silver_landing_company_backfill_completed",
        run_id=run_id,
        source_counts=source_counts,
        landing_export_counts=landing_export_counts,
    )

    return {
        "command": "backfill-silver-landing-company-metadata",
        "run_id": run_id,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "source_counts": source_counts,
        "landing_export": landing_export_counts,
    }
