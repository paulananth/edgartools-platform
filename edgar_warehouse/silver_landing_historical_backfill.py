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

This module reads every table in `_BACKFILL_TABLES` directly from the full
DuckDB canonical silver dataset (every shard, via `ShardedSilverReader`) and
re-emits each row as-is into the landing-zone buffer, bypassing every
merge-level skip gate entirely -- a one-time seed, not a new ongoing write
path. Safe to re-run: the landing zone is append-only with
latest-parse_sequence-wins collapse in dbt, so a second run just adds a
newer, identical snapshot that wins the same way. `sec_company_ticker` is
deliberately excluded -- its landing shape isn't a raw DuckDB row (see
`replace_company_tickers`'s own inline enrichment, silver-snowflake-migration
Ticket 14), and it already has healthy live coverage through `seed-universe`'s
own export path, so it doesn't have this gap.
"""
from __future__ import annotations

from datetime import UTC, datetime
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


def _fetch_all_rows(reader: Any, table: str) -> list[dict[str, Any]]:
    return reader.fetch(f"SELECT * FROM {table}")


def run_silver_landing_historical_backfill(context: Any, run_id: str) -> dict[str, Any]:
    """One-time seed of `_BACKFILL_TABLES` into Snowflake silver landing from
    DuckDB canonical.

    Reads across every shard rather than the single active shard a normal
    command touches, since rows for any of these tables may live in any
    CIK-range shard and this backfill needs the complete universe in one pass.
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
            "SILVER_LANDING_EXPORT_ROOT is required for backfill-silver-landing-historical"
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
        command_name="backfill-silver-landing-historical", scope={}, now=now
    )
    landing_export_counts = write_landing_export(
        landing_export,
        context.silver_landing_export_root,
        run_id=run_id,
        business_date=business_date,
        command_name="backfill-silver-landing-historical",
        environment_name=context.environment_name,
        now=now,
    )

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
