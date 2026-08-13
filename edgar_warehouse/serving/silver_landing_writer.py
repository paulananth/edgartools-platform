"""Flush a LandingExportBuffer to Parquet + a run manifest.

silver-snowflake-migration map, Ticket 01: reuses the existing native-pull
apparatus's SHAPE (per-table Parquet + a run_manifest.json, picked up by
Snowpipe auto-ingest) but writes to its own root
(`SILVER_LANDING_EXPORT_ROOT`, distinct from `SERVING_EXPORT_ROOT`, which
Ticket 03 established stays gold's), and reuses
`dataset_path_catalog`'s existing `snowflake_export_table`/
`snowflake_export_run_manifest_path` templates unchanged -- same relative-path
shape (`{table}/business_date=.../run_id=.../{table}.parquet`) that already
works for gold's export, at a different destination root.

Unlike gold's `SNOWFLAKE_EXPORT_TABLES` (a static, hand-maintained dict),
the table list here is *dynamic*: whichever landing tables a command
actually wrote rows to this run, read straight from the buffer -- there is
nothing to keep in lockstep by hand.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pyarrow as pa

from edgar_warehouse.infrastructure.dataset_path_catalog import (
    default_capture_spec_factory,
    default_path_resolver,
)
from edgar_warehouse.serving.gold_models import _write_parquet
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer


def _landing_run_manifest(
    *,
    environment_name: str,
    command_name: str,
    run_id: str,
    business_date: str,
    now: datetime,
    table_writes: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "business_date": business_date,
        "completed_at": now.isoformat().replace("+00:00", "Z"),
        "environment": environment_name,
        "run_id": run_id,
        "schema_version": 1,
        "target": "silver_landing",
        "tables": table_writes,
        "workflow_name": command_name.replace("-", "_"),
    }


def write_landing_export(
    buffer: LandingExportBuffer,
    export_root: Any,
    *,
    run_id: str,
    business_date: str,
    command_name: str,
    environment_name: str,
    now: datetime,
) -> dict[str, int]:
    """Write every table the buffer collected to Parquet, plus a run manifest.

    Returns {table_name: row_count} for tables actually written (empty
    tables are skipped -- an empty parse run writes nothing and the
    manifest reflects that, rather than a zero-row Parquet file). No-op
    (returns {}) if the buffer collected nothing this run.
    """
    tables = buffer.tables()
    if not tables:
        return {}

    spec_factory = default_capture_spec_factory()
    table_writes: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    for table_name, rows in tables.items():
        arrow_table = pa.Table.from_pylist(rows)
        spec = spec_factory.snowflake_export_table(
            table_path=table_name,
            business_date=business_date,
            run_id=run_id,
        )
        _write_parquet(arrow_table, export_root, spec.relative_path)
        counts[table_name] = arrow_table.num_rows
        table_writes.append(
            {
                "file_count": 1,
                "relative_path": spec.relative_path,
                "row_count": arrow_table.num_rows,
                "table_name": table_name,
            }
        )

    manifest = _landing_run_manifest(
        environment_name=environment_name,
        command_name=command_name,
        run_id=run_id,
        business_date=business_date,
        now=now,
        table_writes=table_writes,
    )
    manifest_relative_path = default_path_resolver().snowflake_export_run_manifest_path(
        workflow_name=f"silver_landing_{command_name}".replace("-", "_"),
        business_date=business_date,
        run_id=run_id,
    )
    export_root.write_json(manifest_relative_path, manifest)

    return counts
