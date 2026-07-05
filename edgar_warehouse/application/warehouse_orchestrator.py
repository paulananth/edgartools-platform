"""Warehouse runtime helpers for infrastructure-oriented command execution."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sys
import uuid
import warnings
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from edgar_warehouse.application.command_context_factory import build_warehouse_context
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.domain.policy.sec_calendar import (
    date_range as calendar_date_range,
    expected_available_at,
    is_business_day,
    last_weekday as calendar_last_weekday,
    latest_eligible_business_date,
    next_business_day,
    nth_weekday as calendar_nth_weekday,
    observed_date as calendar_observed_date,
    previous_business_day,
    us_federal_holidays,
)
from edgar_warehouse.domain.policy.command_scope import (
    dedupe_ints,
    dedupe_strings,
    latest_acceptance_datetime,
    latest_filing_date,
    parse_acceptance_datetime,
    parse_cik,
    parse_date as parse_scope_date,
    resolve_export_business_date,
    sync_mode_for_command,
    sync_scope_key_for_command,
    sync_scope_type_for_command,
)
from edgar_warehouse.loaders import (
    seed_universe_loader,
    stage_daily_index_filing_loader,
    stage_manifest_loader,
    stage_pagination_filing_loader,
    stage_recent_filing_loader,
)
from edgar_warehouse.reconcile import (
    build_reconcile_findings,
    mark_findings_for_resync,
    mark_findings_resolved,
)
from edgar_warehouse.infrastructure.run_manifest_builder import (
    SNOWFLAKE_EXPORT_TABLES,
    layer_manifest,
    planned_writes,
    snowflake_export_manifest,
    snowflake_export_run_manifest,
    snowflake_export_run_manifest_relative_path,
    snowflake_export_run_manifest_table,
    warehouse_success_message,
)
from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory, default_path_resolver
from edgar_warehouse.infrastructure.sec_client import (
    download_sec_bytes,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes
from edgar_warehouse.silver_support.session import open_silver_database, open_silver_shard

if TYPE_CHECKING:
    from edgar_warehouse.silver_store import SilverDatabase

GOLD_AFFECTING_COMMANDS = {
    "bootstrap-full",
    "bootstrap-next",
    "bootstrap",
    # bootstrap-batch deliberately excluded: parallel batch tasks do bronze+silver only.
    # Gold is built once by gold-refresh after all batches complete.
    "daily-incremental",
    "targeted-resync",
    "full-reconcile",
    "gold-refresh",  # builds gold from current silver state, no bronze capture
}

SNOWFLAKE_EXPORT_COMMANDS = GOLD_AFFECTING_COMMANDS | {"seed-universe"}

# load_history's tracking-status contract (data-architecture Issue 2): compute-windows,
# bootstrap-next (via the explicit --tracking-status-filter the load_history state machine
# passes), and bootstrap-fundamentals's CIK resolution must all query the SAME combined status
# set. A CIK is 'bootstrap_pending' from seeding until its first full submissions bootstrap
# completes, then promoted to 'active' (see _sync_mdm_tracking_status below). Filtering
# ComputeWindows to 'active' alone computed zero windows for every freshly-seeded environment,
# since nothing is 'active' yet; filtering to 'bootstrap_pending' alone would stop covering
# already-tracked companies on later runs. Do not change this without updating the matching
# --tracking-status-filter literal in infra/scripts/deploy-aws-application.sh
# (write_load_history_definition's `per_window` bootstrap-next command).
LOAD_HISTORY_TRACKING_STATUS_FILTER = "active,bootstrap_pending"

WAREHOUSE_RUNTIME_MODES = {
    "bronze_capture",
    "infrastructure_validation",
}

OWNERSHIP_FORMS = {"3", "3/A", "4", "4/A", "5", "5/A"}
ADV_FORMS = {"ADV", "ADV/A", "ADV-E", "ADV-E/A", "ADV-H", "ADV-H/A", "ADV-NR", "ADV-W", "ADV-W/A"}

_DAILY_INDEX_LINE_PATTERN = re.compile(
    r"^.+?\s{2,}(?P<cik>\d{4,10})\s+(?:\d{8}|\d{4}-\d{2}-\d{2})\s+edgar/data/"
)


def _emit_pipeline_event(event: str, **payload: Any) -> None:
    """Emit a structured progress event for ECS/CloudWatch pipeline monitoring."""
    document = {
        "event": event,
        "emitted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        **payload,
    }
    print(json.dumps(document, sort_keys=True), file=sys.stderr, flush=True)


def run_command(command_name: str, args: Any) -> int:
    """Execute a warehouse command and emit a JSON result payload."""
    arguments = _namespace_to_payload(args)
    runtime_mode = os.environ.get("WAREHOUSE_RUNTIME_MODE", "infrastructure_validation").strip() or "infrastructure_validation"
    try:
        context = _build_warehouse_context(command_name)
        runtime_mode = context.runtime_mode
        payload = _execute_warehouse(context=context, command_name=command_name, arguments=arguments)
    except WarehouseRuntimeError as exc:
        print(json.dumps(_error_payload(command_name, arguments, str(exc), runtime_mode=runtime_mode), indent=2, sort_keys=True))
        return 2

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def run_seed_universe_command(args: Any) -> int:
    """Seed the MDM tracked universe from a SEC reference JSON file."""
    try:
        from edgar_warehouse.silver_store import _parse_company_ticker_rows

        limit = _resolve_seed_limit(getattr(args, "limit", None))
        source_label, document = _resolve_seed_document(args)
        rows = _parse_company_ticker_rows(document)
        if not rows:
            raise WarehouseRuntimeError(f"No company ticker rows found in {source_label}")
        if limit is not None:
            rows = rows[:limit]

        tracking_status = str(getattr(args, "tracking_status", None) or "active")
        from edgar_warehouse.mdm.database import get_engine
        from edgar_warehouse.mdm.universe import bulk_upsert_universe
        rows_seeded = bulk_upsert_universe(get_engine(), rows, default_status=tracking_status)
    except WarehouseRuntimeError as exc:
        print(
            json.dumps(
                {
                    "command": "seed-universe",
                    "message": str(exc),
                    "status": "error",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    print(
        json.dumps(
            {
                "command": "seed-universe",
                "limit": limit,
                "rows_seeded": rows_seeded,
                "run_id": getattr(args, "run_id", None),
                "source": source_label,
                "status": "ok",
                "tracking_status": tracking_status,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _build_warehouse_context(command_name: str) -> WarehouseCommandContext:
    return build_warehouse_context(command_name)


def _execute_warehouse(
    context: WarehouseCommandContext,
    command_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if context.runtime_mode == "bronze_capture":
        return _execute_warehouse_bronze_capture(context=context, command_name=command_name, arguments=arguments)
    return _execute_warehouse_infrastructure_validation(context=context, command_name=command_name, arguments=arguments)


def _execute_warehouse_infrastructure_validation(
    context: WarehouseCommandContext,
    command_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(UTC)
    run_id = _resolve_run_id(arguments)
    command_path = command_name.replace("_", "-")
    scope = _resolve_scope(command_name=command_name, arguments=arguments, now=now)

    writes = []
    for layer, relative_path in _planned_writes(command_name=command_name, command_path=command_path, run_id=run_id, scope=scope).items():
        target = context.bronze_root if layer == "bronze" else context.storage_root
        manifest = _layer_manifest(
            command_name=command_name,
            run_id=run_id,
            layer=layer,
            relative_path=relative_path,
            arguments=arguments,
            scope=scope,
            now=now,
            runtime_mode=context.runtime_mode,
        )
        writes.append(
            {
                "layer": layer,
                "path": target.write_json(relative_path, manifest),
                "relative_path": relative_path,
            }
        )

    snowflake_exports = []
    if context.snowflake_export_root is not None:
        export_business_date = _resolve_export_business_date(command_name=command_name, scope=scope, now=now)
        for table_name, table_path in SNOWFLAKE_EXPORT_TABLES.items():
            relative_path = (
                f"{table_path}/business_date={export_business_date}/run_id={run_id}/manifest.json"
            )
            export_manifest = _snowflake_export_manifest(
                table_name=table_name,
                command_name=command_name,
                run_id=run_id,
                business_date=export_business_date,
                arguments=arguments,
                now=now,
                runtime_mode=context.runtime_mode,
            )
            snowflake_exports.append(
                {
                    "layer": "snowflake_export",
                    "path": context.snowflake_export_root.write_json(relative_path, export_manifest),
                    "relative_path": relative_path,
                    "table_name": table_name,
                }
            )
        writes.extend(snowflake_exports)

    return {
        "arguments": arguments,
        "command": command_name,
        "environment": {
            "bronze_root": context.bronze_root.root,
            "environment_name": context.environment_name,
            "warehouse_root": context.storage_root.root,
            "silver_root": context.silver_root.root,
            "identity_present": True,
            "snowflake_export_root": context.snowflake_export_root.root if context.snowflake_export_root else None,
        },
        "message": _warehouse_success_message(context.snowflake_export_root is not None),
        "run_id": run_id,
        "runtime_mode": context.runtime_mode,
        "scope": scope,
        "started_at": now.isoformat().replace("+00:00", "Z"),
        "status": "ok",
        "writes": writes,
    }


def _execute_warehouse_bronze_capture(
    context: WarehouseCommandContext,
    command_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(UTC)
    run_id = _resolve_run_id(arguments)
    command_path = command_name.replace("_", "-")

    # --- Shard-aware hydrate/open (Phase 9, STORE-02) ---
    # bootstrap-batch is the ECS chunk task that receives a pre-resolved CIK list
    # (from seed-silver-batches / Step Functions Distributed Map).  For remote
    # storage we download only the overlapping shard rather than the full monolith.
    #
    # NOTE: --cik-offset is a positional index into the MDM CIK list, NOT a CIK
    # value.  Here we already have the final resolved CIK integers in cik_list,
    # so cik_min/cik_max are extracted directly from those values.
    _active_shard_index: int | None = None
    _using_shard_path: bool = (
        command_name == "bootstrap-batch"
        and context.storage_root.is_remote
        and bool(arguments.get("cik_list"))
    )

    if _using_shard_path:
        chunk_ciks = [int(c) for c in arguments["cik_list"]]
        cik_min = min(chunk_ciks)
        cik_max = max(chunk_ciks)
        from edgar_warehouse.application.sharding.shard_manifest import shards_for_window

        try:
            manifest = _read_shard_manifest(context)
        except (FileNotFoundError, OSError):
            # First-load recovery can start from copied bronze before a shard
            # manifest exists. Fall back to the monolith path; the recovery
            # state machine runs BatchSilver sequentially to avoid write races.
            _emit_pipeline_event(
                "shard_manifest_missing_monolith_fallback",
                command=command_name,
                run_id=run_id,
            )
            _using_shard_path = False
        else:
            overlapping = shards_for_window(manifest, cik_min, cik_max)
            if not overlapping:
                # No shard covers this window — fall back to monolith path.
                _using_shard_path = False
            else:
                if len(overlapping) > 1:
                    # A 500-CIK window spanning two shard bands is unusual but possible near
                    # band boundaries.  Only the first overlapping shard is the write target
                    # (operational invariant: configure cik_limit so windows don't straddle
                    # boundaries).  Log a warning but do not error out.
                    _emit_pipeline_event(
                        "shard_window_crosses_band_boundary",
                        command=command_name,
                        run_id=run_id,
                        cik_min=cik_min,
                        cik_max=cik_max,
                        overlapping_shards=overlapping,
                        write_shard=overlapping[0],
                    )
                _active_shard_index = overlapping[0]
                local_shard_path = _hydrate_shard_for_window(context, _active_shard_index)
                if local_shard_path is None:
                    # Shard doesn't exist in remote storage yet — fall back to monolith.
                    _using_shard_path = False
                else:
                    scope = _resolve_scope(
                        command_name=command_name,
                        arguments=arguments,
                        now=now,
                        silver_root=None,
                    )
                    db = open_silver_shard(local_shard_path)

    if not _using_shard_path:
        _hydrate_silver_database_from_storage(context)
        scope = _resolve_scope(command_name=command_name, arguments=arguments, now=now, silver_root=context.silver_root)
        db = _open_silver_database(context.silver_root)
    db_closed = False
    sync_mode = _sync_mode_for_command(command_name)
    sync_scope_type = _sync_scope_type_for_command(command_name, scope)
    db.start_sync_run(
        {
            "sync_run_id": run_id,
            "sync_mode": sync_mode,
            "scope_type": sync_scope_type,
            "scope_key": _sync_scope_key_for_command(command_name, scope),
            "started_at": now,
            "status": "running",
        }
    )

    raw_writes: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {"rows_inserted": 0, "rows_skipped": 0, "sync_status": "succeeded"}
    gold_row_counts: dict[str, int] | None = None
    snowflake_export_counts: dict[str, int] | None = None
    snowflake_export_manifest_write: dict[str, Any] | None = None
    silver_database_write: dict[str, Any] | None = None
    silver_table_counts: dict[str, int] | None = None
    try:
        _emit_pipeline_event(
            "bronze_silver_started",
            command=command_name,
            run_id=run_id,
        )
        raw_writes, metrics = _capture_bronze_raw(
            context=context,
            db=db,
            command_name=command_name,
            arguments=arguments,
            scope=scope,
            now=now,
            sync_run_id=run_id,
        )
        _emit_pipeline_event(
            "bronze_silver_completed",
            command=command_name,
            run_id=run_id,
            rows_inserted=metrics.get("rows_inserted", 0),
            rows_skipped=metrics.get("rows_skipped", 0),
        )
        silver_table_counts = db.get_table_counts()
        if context.snowflake_export_root is not None and command_name in GOLD_AFFECTING_COMMANDS:
            from edgar_warehouse.serving.gold_models import build_gold, write_gold_to_storage
            from edgar_warehouse.serving.targets.snowflake import write_gold_to_snowflake_export

            gold_started_at = datetime.now(UTC)
            _emit_pipeline_event(
                "gold_publish_started",
                command=command_name,
                run_id=run_id,
                silver_table_counts=silver_table_counts,
            )

            _emit_pipeline_event("gold_build_started", command=command_name, run_id=run_id)

            gold_tables = build_gold(db)
            _emit_pipeline_event(
                "gold_build_completed",
                command=command_name,
                run_id=run_id,
                duration_seconds=(datetime.now(UTC) - gold_started_at).total_seconds(),
                table_count=len(gold_tables),
            )

            storage_started_at = datetime.now(UTC)
            _emit_pipeline_event("gold_storage_write_started", command=command_name, run_id=run_id)
            gold_row_counts = write_gold_to_storage(gold_tables, context.storage_root, run_id)
            _emit_pipeline_event(
                "gold_storage_write_completed",
                command=command_name,
                run_id=run_id,
                duration_seconds=(datetime.now(UTC) - storage_started_at).total_seconds(),
                gold_row_counts=gold_row_counts,
            )

            export_business_date = _resolve_export_business_date(command_name=command_name, scope=scope, now=now)
            export_started_at = datetime.now(UTC)
            _emit_pipeline_event(
                "gold_snowflake_export_started",
                command=command_name,
                run_id=run_id,
                export_business_date=str(export_business_date),
            )
            snowflake_export_counts = write_gold_to_snowflake_export(
                gold_tables,
                context.snowflake_export_root,
                run_id,
                export_business_date,
            )
            _emit_pipeline_event(
                "gold_snowflake_export_completed",
                command=command_name,
                run_id=run_id,
                duration_seconds=(datetime.now(UTC) - export_started_at).total_seconds(),
                snowflake_export_counts=snowflake_export_counts,
            )

            del gold_tables
            _emit_pipeline_event(
                "gold_publish_completed",
                command=command_name,
                duration_seconds=(datetime.now(UTC) - gold_started_at).total_seconds(),
                gold_row_counts=gold_row_counts,
                run_id=run_id,
                snowflake_export_counts=snowflake_export_counts,
            )
        db.complete_sync_run(
            run_id,
            status=str(metrics.get("sync_status", "succeeded")),
            rows_inserted=int(metrics.get("rows_inserted", 0) or 0),
            rows_skipped=int(metrics.get("rows_skipped", 0) or 0),
        )
        db.close()
        db_closed = True
        _emit_pipeline_event(
            "silver_publish_started",
            command=command_name,
            run_id=run_id,
            storage_root=context.storage_root.root,
        )
        if _using_shard_path and _active_shard_index is not None:
            silver_database_write = _publish_shard_if_remote(context, _active_shard_index)
        else:
            silver_database_write = _publish_silver_database_if_remote(context)
        _emit_pipeline_event(
            "silver_publish_completed",
            command=command_name,
            run_id=run_id,
            silver_database=silver_database_write,
        )
    except Exception as exc:
        if not db_closed:
            db.complete_sync_run(run_id, status="failed", error_message=str(exc))
        _emit_pipeline_event(
            "pipeline_failed",
            command=command_name,
            error_message=str(exc),
            run_id=run_id,
        )
        raise
    finally:
        if not db_closed:
            db.close()

    writes = []
    for layer, relative_path in _planned_writes(command_name=command_name, command_path=command_path, run_id=run_id, scope=scope).items():
        target = context.bronze_root if layer == "bronze" else context.storage_root
        manifest = _layer_manifest(
            command_name=command_name,
            run_id=run_id,
            layer=layer,
            relative_path=relative_path,
            arguments=arguments,
            scope=scope,
            now=now,
            runtime_mode=context.runtime_mode,
        )
        writes.append(
            {
                "layer": layer,
                "path": target.write_json(relative_path, manifest),
                "relative_path": relative_path,
            }
        )

    if context.snowflake_export_root is not None and command_name in GOLD_AFFECTING_COMMANDS:
        export_business_date = _resolve_export_business_date(command_name=command_name, scope=scope, now=now)
        run_manifest_relative_path = _snowflake_export_run_manifest_relative_path(
            workflow_name=command_name.replace("-", "_"),
            business_date=export_business_date,
            run_id=run_id,
        )
        run_manifest = _snowflake_export_run_manifest(
            environment_name=context.environment_name,
            command_name=command_name,
            run_id=run_id,
            business_date=export_business_date,
            now=now,
            export_counts=snowflake_export_counts or {},
        )
        snowflake_export_manifest_write = {
            "layer": "snowflake_export_manifest",
            "path": context.snowflake_export_root.write_json(run_manifest_relative_path, run_manifest),
            "relative_path": run_manifest_relative_path,
        }
        writes.append(snowflake_export_manifest_write)

    if silver_database_write is not None:
        writes.append(silver_database_write)

    ticker_reference_rows = metrics.pop("_ticker_reference_rows", None)
    if (
        context.snowflake_export_root is not None
        and command_name == "seed-universe"
        and ticker_reference_rows is not None
    ):
        from edgar_warehouse.serving.gold_models import build_ticker_reference_table
        from edgar_warehouse.serving.targets.snowflake import write_ticker_reference_to_snowflake_export

        export_business_date = _resolve_export_business_date(command_name=command_name, scope=scope, now=now)
        ticker_table = build_ticker_reference_table(ticker_reference_rows, run_id)
        ticker_row_count = write_ticker_reference_to_snowflake_export(
            ticker_table,
            context.snowflake_export_root,
            run_id,
            export_business_date,
        )
        snowflake_export_counts = {"ticker_reference": ticker_row_count}
        run_manifest_relative_path = _snowflake_export_run_manifest_relative_path(
            workflow_name="seed_universe",
            business_date=export_business_date,
            run_id=run_id,
        )
        run_manifest = {
            "business_date": export_business_date,
            "completed_at": now.isoformat().replace("+00:00", "Z"),
            "environment": context.environment_name,
            "run_id": run_id,
            "schema_version": 1,
            "tables": [
                _snowflake_export_run_manifest_table(
                    table_name="TICKER_REFERENCE",
                    table_path="ticker_reference",
                    run_id=run_id,
                    business_date=export_business_date,
                    row_count=ticker_row_count,
                )
            ],
            "workflow_name": "seed_universe",
        }
        snowflake_export_manifest_write = {
            "layer": "snowflake_export_manifest",
            "path": context.snowflake_export_root.write_json(run_manifest_relative_path, run_manifest),
            "relative_path": run_manifest_relative_path,
        }
        writes.append(snowflake_export_manifest_write)

    return {
        "arguments": arguments,
        "bronze_object_count": len(raw_writes),
        "command": command_name,
        "environment": {
            "bronze_root": context.bronze_root.root,
            "environment_name": context.environment_name,
            "warehouse_root": context.storage_root.root,
            "silver_root": context.silver_root.root,
            "identity_present": True,
            "snowflake_export_root": context.snowflake_export_root.root if context.snowflake_export_root else None,
        },
        "message": (
            "Warehouse bronze capture completed successfully. "
            "Raw SEC files and run manifests were written to the configured bronze"
            + (
                ", warehouse, and Snowflake export roots."
                if context.snowflake_export_root is not None else
                " and warehouse roots."
            )
        ),
        "raw_writes": raw_writes,
        "run_id": run_id,
        "runtime_mode": context.runtime_mode,
        "scope": scope,
        "gold_row_counts": gold_row_counts,
        "silver_table_counts": silver_table_counts,
        "silver_database": silver_database_write,
        "snowflake_export_manifest": snowflake_export_manifest_write,
        "snowflake_export_row_counts": snowflake_export_counts,
        "started_at": now.isoformat().replace("+00:00", "Z"),
        "status": "ok",
        "writes": writes,
        "cik_universe_path": metrics.get("cik_universe_path"),
        "cik_count": metrics.get("cik_count"),
    }


def _open_silver_database(silver_root: StorageLocation) -> SilverDatabase:
    return open_silver_database(silver_root)


def _hydrate_silver_database_from_storage(context: WarehouseCommandContext) -> None:
    if not context.storage_root.is_remote or context.silver_root.is_remote:
        return
    remote_path = context.storage_root.join("silver", "sec", "silver.duckdb")
    local_path = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))
    try:
        payload = read_bytes(remote_path)
    except (FileNotFoundError, OSError):
        return
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(payload)
    _emit_pipeline_event(
        "silver_database_hydrated",
        path=remote_path,
        local_path=str(local_path),
        size_bytes=len(payload),
    )


def _publish_silver_database_if_remote(context: WarehouseCommandContext) -> dict[str, Any] | None:
    if not context.storage_root.is_remote:
        return None
    source_path = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))
    if not source_path.exists():
        raise WarehouseRuntimeError(f"Silver DuckDB file was not found: {source_path}")
    relative_path = "silver/sec/silver.duckdb"
    size_bytes = source_path.stat().st_size
    destination = context.storage_root.upload_file(relative_path, source_path)
    return {
        "layer": "silver_database",
        "path": destination,
        "relative_path": relative_path,
        "size_bytes": size_bytes,
    }


# ---------------------------------------------------------------------------
# Shard-aware hydrate / publish (Phase 9 — STORE-02 / STORE-03)
#
# PITFALL: --cik-offset is a POSITIONAL INDEX into the sorted MDM CIK list, not
# a CIK value.  Callers must resolve positions to actual CIK values before
# passing cik_min/cik_max to shards_for_window.  The functions below accept an
# already-resolved shard_index.
# ---------------------------------------------------------------------------


def _read_shard_manifest(context: WarehouseCommandContext) -> dict:
    """Fetch and parse shard-manifest.json from remote storage.

    Raises
    ------
    WarehouseRuntimeError
        If the storage root is not remote, or if the manifest is malformed.
    """
    if not context.storage_root.is_remote:
        raise WarehouseRuntimeError(
            "shard manifest requires remote storage; storage_root is local"
        )
    from edgar_warehouse.application.sharding.shard_manifest import load_manifest

    manifest_path = context.storage_root.join("silver", "sec", "shard-manifest.json")
    payload = read_bytes(manifest_path)
    return load_manifest(payload)


def _hydrate_shard_for_window(
    context: WarehouseCommandContext,
    shard_index: int,
) -> str | None:
    """Download shard-{shard_index}.duckdb from remote storage to the local silver directory.

    Parameters
    ----------
    context:
        The warehouse command context carrying storage root paths.
    shard_index:
        The zero-based shard index to download.

    Returns
    -------
    str | None
        The local filesystem path to the downloaded shard, or ``None`` if the
        shard does not yet exist in remote storage (new shard, no pre-existing
        data).  Returns the local shard path directly for non-remote storage
        contexts (no download needed).
    """
    local_path = Path(
        context.silver_root.join("silver", "sec", "shards", f"shard-{shard_index}.duckdb")
    )

    if not context.storage_root.is_remote or context.silver_root.is_remote:
        # Local storage — no download needed; return existing path.
        return str(local_path)

    relative_path = default_path_resolver().shard_path(shard_index)
    remote_path = context.storage_root.join(relative_path)

    try:
        payload = read_bytes(remote_path)
    except (FileNotFoundError, OSError):
        return None

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(payload)
    _emit_pipeline_event(
        "silver_shard_hydrated",
        shard_index=shard_index,
        path=remote_path,
        local_path=str(local_path),
        size_bytes=len(payload),
    )
    return str(local_path)


def _hydrate_all_shards(context: WarehouseCommandContext) -> list[str | None]:
    """Download all shards listed in the shard manifest.

    Used by gold-refresh and MDM commands that require the full silver dataset.

    Returns
    -------
    list[str | None]
        Local paths for each shard (in shard_index order).  An entry is
        ``None`` if that shard does not yet exist in remote storage.
    """
    manifest = _read_shard_manifest(context)
    return [
        _hydrate_shard_for_window(context, shard_index)
        for shard_index in range(manifest["shard_count"])
    ]


def _publish_shard_if_remote(
    context: WarehouseCommandContext,
    shard_index: int,
) -> dict[str, Any] | None:
    """Upload the modified shard-{shard_index}.duckdb to remote storage.

    Parameters
    ----------
    context:
        The warehouse command context.
    shard_index:
        The zero-based shard index to upload.

    Returns
    -------
    dict | None
        A write-record dict (``layer``, ``shard_index``, ``path``,
        ``size_bytes``) if uploaded, or ``None`` if storage is local.

    Raises
    ------
    WarehouseRuntimeError
        If the local shard file does not exist.
    """
    if not context.storage_root.is_remote:
        return None

    local_path = Path(
        context.silver_root.join("silver", "sec", "shards", f"shard-{shard_index}.duckdb")
    )
    if not local_path.exists():
        raise WarehouseRuntimeError(
            f"Shard {shard_index} not found at {local_path}"
        )

    relative_path = default_path_resolver().shard_path(shard_index)
    destination = context.storage_root.upload_file(relative_path, local_path)
    return {
        "layer": "silver_shard",
        "shard_index": shard_index,
        "path": destination,
        "size_bytes": local_path.stat().st_size,
    }


def _capture_bronze_raw(
    context: WarehouseCommandContext,
    db: SilverDatabase,
    command_name: str,
    arguments: dict[str, Any],
    scope: dict[str, Any],
    now: datetime,
    sync_run_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Capture bronze first, then apply silver state for a warehouse command."""
    raw_writes: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {"rows_inserted": 0, "rows_skipped": 0, "sync_status": "succeeded"}

    if arguments.get("include_reference_refresh"):
        reference_result = _sync_reference_data(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            fetch_date=now.date(),
        )
        raw_writes.extend(reference_result["raw_writes"])
        metrics["rows_inserted"] += reference_result["rows_written"]
        metrics["rows_skipped"] += reference_result["rows_skipped"]

    if command_name == "daily-incremental":
        impacted_ciks: list[int] = []
        for target_date in _date_range(
            start=date.fromisoformat(scope["business_date_start"]),
            end=date.fromisoformat(scope["business_date_end"]),
        ):
            result = _load_daily_index_for_date(
                context=context,
                db=db,
                target_date=target_date,
                sync_run_id=sync_run_id,
                now=now,
                force=bool(arguments.get("force")),
            )
            raw_writes.extend(result["raw_writes"])
            metrics["rows_inserted"] += result["rows_written"]
            metrics["rows_skipped"] += result["rows_skipped"]
            impacted_ciks.extend(result["impacted_ciks"])
            if result["status"] in {"waiting_for_publish", "failed_retryable"}:
                metrics["sync_status"] = "partial"
                break
        impacted_ciks = _dedupe_ints(impacted_ciks)
        _mdm_auto_enroll(impacted_ciks, scope_reason="daily_index")
        impacted_ciks = _filter_ciks_to_universe(impacted_ciks)
        cik_limit = arguments.get("cik_limit")
        cik_offset = int(arguments.get("cik_offset") or 0)
        _validate_window_args(cik_limit, cik_offset)
        selected_ciks = impacted_ciks[cik_offset:]
        if cik_limit is not None:
            selected_ciks = selected_ciks[:cik_limit]
        if selected_ciks:
            result = _run_submissions_bronze_then_silver(
                context=context,
                db=db,
                sync_run_id=sync_run_id,
                ciks=selected_ciks,
                include_pagination=False,
                fetch_date=now.date(),
                force=bool(arguments.get("force")),
                load_mode="daily_incremental",
                artifact_policy=str(arguments.get("artifact_policy") or "all_attachments"),
                parser_policy=str(arguments.get("parser_policy") or "configured_forms"),
            )
            raw_writes.extend(result["raw_writes"])
            metrics["rows_inserted"] += result["rows_written"]
            metrics["rows_skipped"] += result["rows_skipped"]
        return raw_writes, metrics

    if command_name == "load-daily-form-index-for-date":
        result = _load_daily_index_for_date(
            context=context,
            db=db,
            target_date=date.fromisoformat(scope["target_date"]),
            sync_run_id=sync_run_id,
            now=now,
            force=bool(arguments.get("force")),
        )
        raw_writes.extend(result["raw_writes"])
        metrics["rows_inserted"] += result["rows_written"]
        metrics["rows_skipped"] += result["rows_skipped"]
        if result["status"] in {"waiting_for_publish", "failed_retryable"}:
            metrics["sync_status"] = "partial"
        return raw_writes, metrics

    if command_name == "bootstrap":
        ciks = _resolve_bootstrap_target_ciks(
            raw_ciks=scope.get("cik_list"),
            command_name=command_name,
            tracking_status_filter=str(scope.get("tracking_status_filter", "active")),
            cik_limit=arguments.get("cik_limit"),
            cik_offset=int(arguments.get("cik_offset") or 0),
        )
        result = _run_submissions_bronze_then_silver(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            ciks=ciks,
            include_pagination=False,
            fetch_date=now.date(),
            force=bool(arguments.get("force")),
            load_mode="bootstrap",
            recent_limit=arguments.get("recent_limit"),
            artifact_policy=str(arguments.get("artifact_policy") or "all_attachments"),
            parser_policy=str(arguments.get("parser_policy") or "configured_forms"),
        )
        raw_writes.extend(result["raw_writes"])
        metrics["rows_inserted"] += result["rows_written"]
        metrics["rows_skipped"] += result["rows_skipped"]
        return raw_writes, metrics

    if command_name == "bootstrap-full":
        ciks = _resolve_bootstrap_target_ciks(
            raw_ciks=scope.get("cik_list"),
            command_name=command_name,
            tracking_status_filter=str(scope.get("tracking_status_filter", "active")),
            cik_limit=arguments.get("cik_limit"),
            cik_offset=int(arguments.get("cik_offset") or 0),
        )
        result = _run_submissions_bronze_then_silver(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            ciks=ciks,
            include_pagination=True,
            fetch_date=now.date(),
            force=bool(arguments.get("force")),
            load_mode="bootstrap_full",
            artifact_policy=str(arguments.get("artifact_policy") or "all_attachments"),
            parser_policy=str(arguments.get("parser_policy") or "configured_forms"),
        )
        raw_writes.extend(result["raw_writes"])
        metrics["rows_inserted"] += result["rows_written"]
        metrics["rows_skipped"] += result["rows_skipped"]
        return raw_writes, metrics

    if command_name == "bootstrap-next":
        pending_pool_limit = int(scope.get("cik_limit") or 100)
        tracking_status_filter = str(scope.get("tracking_status_filter", "bootstrap_pending"))
        ciks = _resolve_bootstrap_target_ciks(
            raw_ciks=None,
            command_name=command_name,
            tracking_status_filter=tracking_status_filter,
            cik_limit=arguments.get("cik_limit"),
            cik_offset=int(arguments.get("cik_offset") or 0),
        )
        ciks = ciks[:pending_pool_limit]
        result = _run_submissions_bronze_then_silver(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            ciks=ciks,
            include_pagination=True,
            fetch_date=now.date(),
            force=bool(arguments.get("force")),
            load_mode="bootstrap_full",
            artifact_policy=str(arguments.get("artifact_policy") or "all_attachments"),
            parser_policy=str(arguments.get("parser_policy") or "configured_forms"),
        )
        raw_writes.extend(result["raw_writes"])
        metrics["rows_inserted"] += result["rows_written"]
        metrics["rows_skipped"] += result["rows_skipped"]
        return raw_writes, metrics

    if command_name == "targeted-resync":
        scope_type = str(scope.get("scope_type", "")).strip()
        scope_key = str(scope.get("scope_key", "")).strip()
        if scope_type == "reference":
            reference_result = _sync_reference_data(
                context=context,
                db=db,
                sync_run_id=sync_run_id,
                fetch_date=now.date(),
                source_names=_reference_sources_for_scope(scope_key),
            )
            raw_writes.extend(reference_result["raw_writes"])
            metrics["rows_inserted"] += reference_result["rows_written"]
            metrics["rows_skipped"] += reference_result["rows_skipped"]
            return raw_writes, metrics
        if scope_type == "cik":
            result = submissions_orchestrator(
                context=context,
                db=db,
                sync_run_id=sync_run_id,
                cik=_parse_cik(scope_key),
                include_pagination=True,
                fetch_date=now.date(),
                force=bool(arguments.get("force", True)),
                load_mode="targeted_resync",
            )
            raw_writes.extend(result["raw_writes"])
            metrics["rows_inserted"] += result["rows_written"]
            metrics["rows_skipped"] += result["rows_skipped"]
            if arguments.get("include_artifacts") or arguments.get("include_text") or arguments.get("include_parsers"):
                accessions = result["recent_accessions"]
                total_accessions = len(accessions)
                _emit_pipeline_event(
                    "accession_resync_started",
                    cik=_parse_cik(scope_key),
                    accession_count=total_accessions,
                    run_id=sync_run_id,
                )
                accession_started_at = datetime.now(UTC)
                for acc_index, accession_number in enumerate(accessions, start=1):
                    _emit_pipeline_event(
                        "accession_resync_progress",
                        accession_number=accession_number,
                        index=acc_index,
                        total=total_accessions,
                        run_id=sync_run_id,
                    )
                    pipeline_result = _run_accession_resync(
                        context=context,
                        db=db,
                        sync_run_id=sync_run_id,
                        accession_number=accession_number,
                        include_artifacts=bool(arguments.get("include_artifacts", True)),
                        include_text=bool(arguments.get("include_text", True)),
                        include_parsers=bool(arguments.get("include_parsers", True)),
                        force=bool(arguments.get("force", True)),
                    )
                    raw_writes.extend(pipeline_result["raw_writes"])
                    metrics["rows_inserted"] += pipeline_result["rows_written"]
                _emit_pipeline_event(
                    "accession_resync_completed",
                    cik=_parse_cik(scope_key),
                    accession_count=total_accessions,
                    rows_written=metrics["rows_inserted"],
                    duration_seconds=(datetime.now(UTC) - accession_started_at).total_seconds(),
                    run_id=sync_run_id,
                )
            return raw_writes, metrics
        if scope_type == "accession":
            pipeline_result = _run_accession_resync(
                context=context,
                db=db,
                sync_run_id=sync_run_id,
                accession_number=scope_key,
                include_artifacts=bool(arguments.get("include_artifacts", True)),
                include_text=bool(arguments.get("include_text", True)),
                include_parsers=bool(arguments.get("include_parsers", True)),
                force=bool(arguments.get("force", True)),
            )
            raw_writes.extend(pipeline_result["raw_writes"])
            metrics["rows_inserted"] += pipeline_result["rows_written"]
            return raw_writes, metrics
        raise WarehouseRuntimeError(f"Unsupported targeted-resync scope_type: {scope_type}")

    if command_name == "full-reconcile":
        ciks = _resolve_reconcile_ciks(
            db=db,
            raw_ciks=scope.get("cik_list"),
            sample_limit=scope.get("sample_limit"),
        )
        all_findings: list[dict[str, Any]] = []
        for cik in ciks:
            snapshot = _capture_reconcile_snapshot(
                context=context,
                db=db,
                cik=cik,
                fetch_date=now.date(),
                force=bool(arguments.get("force", True)),
            )
            raw_writes.append(snapshot["write_record"])
            findings = build_reconcile_findings(
                db=db,
                cik=cik,
                sync_run_id=sync_run_id,
                submissions_payload=snapshot["payload"],
            )
            all_findings.extend(findings)
        if all_findings:
            db.insert_reconcile_findings(all_findings)
            metrics["rows_inserted"] += len(all_findings)
        if scope.get("auto_heal"):
            healed_rows = mark_findings_for_resync(all_findings, resync_run_id=sync_run_id)
            if healed_rows:
                db.insert_reconcile_findings(healed_rows)
            resolved_rows: list[dict[str, Any]] = []
            for row in healed_rows:
                if row["recommended_action"] == "accession_resync":
                    _run_accession_resync(
                        context=context,
                        db=db,
                        sync_run_id=sync_run_id,
                        accession_number=row["object_key"],
                        include_artifacts=True,
                        include_text=True,
                        include_parsers=True,
                        force=True,
                    )
                else:
                    submissions_orchestrator(
                        context=context,
                        db=db,
                        sync_run_id=sync_run_id,
                        cik=int(row["cik"]),
                        include_pagination=True,
                        fetch_date=now.date(),
                        force=True,
                        load_mode="targeted_resync",
                    )
                resolved_rows.append(row)
            if resolved_rows:
                db.insert_reconcile_findings(mark_findings_resolved(resolved_rows, resync_run_id=sync_run_id))
        return raw_writes, metrics

    if command_name == "catch-up-daily-form-index":
        end_date = date.fromisoformat(scope["end_date"])
        result = _capture_catch_up_daily_form_index(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            end_date=end_date,
            now=now,
            force=bool(arguments.get("force")),
        )
        raw_writes.extend(result["raw_writes"])
        metrics["rows_inserted"] += result["rows_written"]
        metrics["rows_skipped"] += result["rows_skipped"]
        if result["status"] == "partial":
            metrics["sync_status"] = "partial"
        return raw_writes, metrics

    if command_name == "seed-universe":
        reference_result = _sync_reference_data(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            fetch_date=now.date(),
        )
        raw_writes.extend(reference_result["raw_writes"])
        metrics["rows_inserted"] += reference_result["rows_written"]
        metrics["rows_skipped"] += reference_result["rows_skipped"]
        seed_document = reference_result.get("seed_document") or {}
        universe_rows = seed_universe_loader(
            seed_document,
            sync_run_id=sync_run_id,
            raw_object_id=reference_result["raw_writes"][0]["sha256"] if reference_result["raw_writes"] else "",
            load_mode="seed_universe",
        )
        # Preserve the full per-ticker rows for TICKER_REFERENCE export (before dedup/cap).
        ticker_reference_rows = list(universe_rows)
        # SEC emits one row per ticker; dedupe to unique CIKs for batching.
        seen_ciks: set[int] = set()
        deduped_rows: list[dict[str, Any]] = []
        for row in universe_rows:
            cik = int(row["cik"])
            if cik in seen_ciks:
                continue
            seen_ciks.add(cik)
            deduped_rows.append(row)
        universe_rows = deduped_rows
        limited_ciks = _apply_bronze_cik_limit([int(row["cik"]) for row in universe_rows])
        if len(limited_ciks) < len(universe_rows):
            allowed = set(limited_ciks)
            universe_rows = [row for row in universe_rows if int(row["cik"]) in allowed]
        # Exclude companies already fully bootstrapped. Check both silver DuckDB
        # (sec_company_sync_state.tracking_status = 'active') and MDM Postgres,
        # since MDM may have been reset while silver still holds accurate status.
        # Non-fatal: MDM unreachability returns [] and silver is always available.
        active_ciks = set(_get_mdm_tracked_ciks("active"))
        silver_active_ciks = set(
            row["cik"]
            for row in db.get_active_ciks()
        )
        active_ciks = active_ciks | silver_active_ciks
        if active_ciks:
            before = len(universe_rows)
            universe_rows = [row for row in universe_rows if int(row["cik"]) not in active_ciks]
            _emit_pipeline_event(
                "seed_universe_filtered",
                total_ciks=before,
                new_ciks=len(universe_rows),
                skipped_active=before - len(universe_rows),
                skipped_mdm_active=len(silver_active_ciks & {int(r["cik"]) for r in universe_rows[:before]}),
                skipped_silver_active=len(silver_active_ciks),
            )
        if arguments.get("limit") is not None:
            universe_rows = universe_rows[: int(arguments["limit"])]
        metrics["_ticker_reference_rows"] = ticker_reference_rows
        cik_universe_path = _write_cik_universe_batches(
            context=context,
            rows=universe_rows,
            fetch_date=now.date(),
            sync_run_id=sync_run_id,
            batch_size=100,
        )
        metrics["cik_universe_path"] = cik_universe_path
        metrics["cik_count"] = len(universe_rows)
        return raw_writes, metrics

    if command_name == "parse-ownership-bronze":
        return _run_parse_ownership_bronze(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            metrics=metrics,
            limit=int(arguments["limit"]) if arguments.get("limit") is not None else None,
            accession_list=arguments.get("accession_list") or None,
        )

    if command_name == "parse-adv-bronze":
        return _run_parse_adv_bronze(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            metrics=metrics,
            limit=int(arguments["limit"]) if arguments.get("limit") is not None else None,
            accession_list=arguments.get("accession_list") or None,
            explicit_artifacts=arguments.get("artifacts") or [],
        )

    if command_name == "seed-silver-batches":
        tracking_status_filter = str(arguments.get("tracking_status_filter") or "all").strip()
        batch_size = int(arguments.get("batch_size") or 100)
        rows = db.get_ciks_with_bronze(tracking_status_filter=tracking_status_filter)
        _emit_pipeline_event(
            "seed_silver_batches_started",
            tracking_status_filter=tracking_status_filter,
            cik_count=len(rows),
            batch_size=batch_size,
            run_id=sync_run_id,
        )
        if not rows:
            _emit_pipeline_event(
                "seed_silver_batches_completed",
                cik_count=0,
                batch_count=0,
                run_id=sync_run_id,
            )
            metrics["cik_count"] = 0
            return raw_writes, metrics
        cik_universe_path = _write_cik_universe_batches(
            context=context,
            rows=rows,
            fetch_date=now.date(),
            sync_run_id=sync_run_id,
            batch_size=batch_size,
        )
        batch_count = -(-len(rows) // batch_size)  # ceiling division
        _emit_pipeline_event(
            "seed_silver_batches_completed",
            cik_count=len(rows),
            batch_count=batch_count,
            cik_universe_path=cik_universe_path,
            run_id=sync_run_id,
        )
        metrics["cik_universe_path"] = cik_universe_path
        metrics["cik_count"] = len(rows)
        return raw_writes, metrics

    if command_name == "seed-bronze-batches":
        batch_size = int(arguments.get("batch_size") or 100)
        ciks = _list_bronze_submission_ciks(context)
        _emit_pipeline_event(
            "seed_bronze_batches_started",
            cik_count=len(ciks),
            batch_size=batch_size,
            run_id=sync_run_id,
        )
        if not ciks:
            _emit_pipeline_event(
                "seed_bronze_batches_completed",
                cik_count=0,
                batch_count=0,
                run_id=sync_run_id,
            )
            metrics["cik_count"] = 0
            return raw_writes, metrics
        rows = [{"cik": cik} for cik in ciks]
        cik_universe_path = _write_cik_universe_batches(
            context=context,
            rows=rows,
            fetch_date=now.date(),
            sync_run_id=sync_run_id,
            batch_size=batch_size,
        )
        batch_count = -(-len(rows) // batch_size)  # ceiling division
        _emit_pipeline_event(
            "seed_bronze_batches_completed",
            cik_count=len(rows),
            batch_count=batch_count,
            cik_universe_path=cik_universe_path,
            run_id=sync_run_id,
        )
        metrics["cik_universe_path"] = cik_universe_path
        metrics["cik_count"] = len(rows)
        return raw_writes, metrics

    if command_name == "bootstrap-batch":
        cik_list = list(arguments.get("cik_list") or [])
        include_pagination = bool(arguments.get("include_pagination", True))
        result = _run_submissions_bronze_then_silver(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            ciks=cik_list,
            include_pagination=include_pagination,
            fetch_date=now.date(),
            force=bool(arguments.get("force", False)),
            load_mode="bootstrap_batch",
            artifact_policy=str(arguments.get("artifact_policy") or "all_attachments"),
            parser_policy=str(arguments.get("parser_policy") or "configured_forms"),
        )
        raw_writes.extend(result["raw_writes"])
        metrics["rows_inserted"] += result["rows_written"]
        metrics["rows_skipped"] += result["rows_skipped"]
        return raw_writes, metrics

    if command_name == "gold-refresh":
        # Bronze and silver are already complete. _execute_warehouse (the caller)
        # will build gold tables and write Snowflake export manifests because
        # gold-refresh is in GOLD_AFFECTING_COMMANDS. Nothing to do here.
        _emit_pipeline_event("gold_refresh_started", run_id=sync_run_id)
        return raw_writes, metrics

    if command_name == "compute-windows":
        window_size = int(arguments.get("window_size") or 500)
        if window_size <= 0:
            raise WarehouseRuntimeError(
                f"--window-size must be a positive integer, got {window_size}"
            )
        ciks = _get_mdm_tracked_ciks(LOAD_HISTORY_TRACKING_STATUS_FILTER)
        # Build window descriptors: {window_offset, window_limit} for each slice
        window_descs = [
            {"window_offset": i, "window_limit": min(window_size, len(ciks) - i)}
            for i in range(0, max(len(ciks), 1), window_size)
            if i < len(ciks)
        ]
        # Write cik_windows.jsonl
        windows_content = "\n".join(json.dumps(w) for w in window_descs) + "\n"
        windows_rel = default_path_resolver().cik_windows_path(sync_run_id)
        context.bronze_root.write_text(windows_rel, windows_content)
        # Write cik_snapshot.jsonl
        snapshot_content = "\n".join(json.dumps({"cik": cik}) for cik in ciks) + "\n"
        snapshot_rel = default_path_resolver().cik_snapshot_path(sync_run_id)
        context.bronze_root.write_text(snapshot_rel, snapshot_content)
        _emit_pipeline_event(
            "compute_windows_completed",
            run_id=sync_run_id,
            cik_count=len(ciks),
            window_count=len(window_descs),
            window_size=window_size,
        )
        metrics["cik_count"] = len(ciks)
        metrics["window_count"] = len(window_descs)
        return raw_writes, metrics

    if command_name == "write-run-summary":
        from_windows_key = str(arguments.get("from_windows_key") or "").strip()
        if not from_windows_key:
            raise WarehouseRuntimeError(
                "--from-windows-key is required for write-run-summary"
            )
        # Read cik_windows.jsonl via the supplied --from-windows-key
        windows_full_path = context.bronze_root.join(from_windows_key)
        try:
            windows_bytes = read_bytes(windows_full_path)
        except (FileNotFoundError, OSError) as exc:
            raise WarehouseRuntimeError(
                f"write-run-summary: cik_windows.jsonl not found at S3 key '{from_windows_key}'"
            ) from exc
        windows_text = windows_bytes.decode("utf-8")
        window_lines = [line for line in windows_text.splitlines() if line.strip()]
        if not window_lines:
            raise WarehouseRuntimeError(
                f"write-run-summary: cik_windows.jsonl at '{from_windows_key}' is empty"
            )
        window_count = len(window_lines)
        # Derive cik_snapshot.jsonl path from the same run prefix
        snapshot_rel = default_path_resolver().cik_snapshot_path(sync_run_id)
        snapshot_full_path = context.bronze_root.join(snapshot_rel)
        try:
            snapshot_bytes = read_bytes(snapshot_full_path)
        except (FileNotFoundError, OSError) as exc:
            raise WarehouseRuntimeError(
                f"write-run-summary: cik_snapshot.jsonl not found at '{snapshot_rel}'"
            ) from exc
        snapshot_text = snapshot_bytes.decode("utf-8")
        cik_lines = [line for line in snapshot_text.splitlines() if line.strip()]
        if not cik_lines:
            raise WarehouseRuntimeError(
                f"write-run-summary: cik_snapshot.jsonl at '{snapshot_rel}' is empty"
            )
        cik_count = len(cik_lines)
        # Build run-summary.json
        completed_at = datetime.now(UTC).isoformat()
        payload = {
            "run_id": sync_run_id,
            "window_count": window_count,
            "cik_count": cik_count,
            "completed_at": completed_at,
        }
        summary_rel = default_path_resolver().run_summary_path(sync_run_id)
        context.bronze_root.write_text(summary_rel, json.dumps(payload) + "\n")
        _emit_pipeline_event(
            "write_run_summary_completed",
            run_id=sync_run_id,
            window_count=window_count,
            cik_count=cik_count,
        )
        metrics["window_count"] = window_count
        metrics["cik_count"] = cik_count
        return raw_writes, metrics

    raise WarehouseRuntimeError(f"bronze_capture mode does not support {command_name}")


def submissions_orchestrator(
    *,
    context: WarehouseCommandContext,
    db: SilverDatabase,
    sync_run_id: str,
    cik: int,
    include_pagination: bool,
    fetch_date: date,
    force: bool,
    load_mode: str,
    recent_limit: int | None = None,
) -> dict[str, Any]:
    """Fetch one submissions main file, then stage and merge silver state."""
    result = _run_submissions_bronze_then_silver(
        context=context,
        db=db,
        sync_run_id=sync_run_id,
        ciks=[cik],
        include_pagination=include_pagination,
        fetch_date=fetch_date,
        force=force,
        load_mode=load_mode,
        recent_limit=recent_limit,
    )
    return {
        "raw_writes": result["raw_writes"],
        "rows_written": result["rows_written"],
        "rows_skipped": result["rows_skipped"],
        "recent_accessions": result["recent_accessions"],
        "pagination_accessions": result["pagination_accessions"],
    }


def _run_submissions_bronze_then_silver(
    *,
    context: WarehouseCommandContext,
    db: SilverDatabase,
    sync_run_id: str,
    ciks: list[int],
    include_pagination: bool,
    fetch_date: date,
    force: bool,
    load_mode: str,
    recent_limit: int | None = None,
    artifact_policy: str = "none",
    parser_policy: str = "none",
) -> dict[str, Any]:
    """Capture every selected SEC submission into bronze before applying silver."""
    bronze_snapshots = []
    total_ciks = len(ciks)
    bronze_started_at = datetime.now(UTC)
    _emit_pipeline_event(
        "bronze_capture_started",
        cik_count=total_ciks,
        include_pagination=include_pagination,
        load_mode=load_mode,
        run_id=sync_run_id,
    )
    for index, cik in enumerate(ciks, start=1):
        bronze_snapshots.append(
            _capture_submission_bronze_snapshot(
                context=context,
                db=db,
                cik=cik,
                include_pagination=include_pagination,
                fetch_date=fetch_date,
                force=force,
            )
        )
        if index == total_ciks or index % 10 == 0:
            _emit_pipeline_event(
                "bronze_capture_progress",
                captured=index,
                cik_count=total_ciks,
                run_id=sync_run_id,
            )
    raw_writes = [
        write_record
        for snapshot in bronze_snapshots
        for write_record in snapshot["raw_writes"]
    ]
    _emit_pipeline_event(
        "bronze_capture_completed",
        cik_count=total_ciks,
        duration_seconds=(datetime.now(UTC) - bronze_started_at).total_seconds(),
        raw_object_count=len(raw_writes),
        run_id=sync_run_id,
    )

    rows_written = 0
    rows_skipped = 0
    recent_accessions: list[str] = []
    pagination_accessions: list[str] = []
    now = datetime.now(UTC)
    silver_started_at = datetime.now(UTC)
    _emit_pipeline_event(
        "silver_apply_started",
        cik_count=total_ciks,
        raw_object_count=len(raw_writes),
        run_id=sync_run_id,
    )
    for index, snapshot in enumerate(bronze_snapshots, start=1):
        result = _apply_submission_snapshot_to_silver(
            db=db,
            sync_run_id=sync_run_id,
            snapshot=snapshot,
            force=force,
            load_mode=load_mode,
            recent_limit=recent_limit,
            now=now,
        )
        rows_written += int(result["rows_written"])
        rows_skipped += int(result["rows_skipped"])
        recent_accessions.extend(result["recent_accessions"])
        pagination_accessions.extend(result["pagination_accessions"])
        if index == total_ciks or index % 10 == 0:
            _emit_pipeline_event(
                "silver_apply_progress",
                applied=index,
                cik_count=total_ciks,
                rows_skipped=rows_skipped,
                rows_written=rows_written,
                run_id=sync_run_id,
            )
    _emit_pipeline_event(
        "silver_apply_completed",
        cik_count=total_ciks,
        duration_seconds=(datetime.now(UTC) - silver_started_at).total_seconds(),
        rows_skipped=rows_skipped,
        rows_written=rows_written,
        run_id=sync_run_id,
    )

    artifact_result = _run_configured_form_artifact_pipeline(
        context=context,
        db=db,
        sync_run_id=sync_run_id,
        accession_numbers=_dedupe_strings([*recent_accessions, *pagination_accessions]),
        artifact_policy=artifact_policy,
        parser_policy=parser_policy,
        force=force,
    )
    raw_writes.extend(artifact_result["raw_writes"])
    rows_written += int(artifact_result["rows_written"])
    rows_skipped += int(artifact_result["rows_skipped"])

    return {
        "raw_writes": raw_writes,
        "rows_written": rows_written,
        "rows_skipped": rows_skipped,
        "recent_accessions": _dedupe_strings(recent_accessions),
        "pagination_accessions": _dedupe_strings(pagination_accessions),
    }


def _run_configured_form_artifact_pipeline(
    *,
    context: WarehouseCommandContext,
    db: SilverDatabase,
    sync_run_id: str,
    accession_numbers: list[str],
    artifact_policy: str,
    parser_policy: str,
    force: bool,
) -> dict[str, Any]:
    fetch_artifacts = _artifact_policy_fetches(artifact_policy)
    run_parsers = _parser_policy_runs(parser_policy)
    if not fetch_artifacts and not run_parsers:
        return {"raw_writes": [], "rows_written": 0, "rows_skipped": 0}

    selected_accessions = _configured_parser_accessions(db, accession_numbers)
    if not selected_accessions:
        return {"raw_writes": [], "rows_written": 0, "rows_skipped": 0}

    _emit_pipeline_event(
        "filing_artifact_pipeline_started",
        accession_count=len(selected_accessions),
        artifact_policy=artifact_policy,
        parser_policy=parser_policy,
        run_id=sync_run_id,
    )
    import time as _time
    _CONSECUTIVE_ERROR_LIMIT = int(os.environ.get("WAREHOUSE_ARTIFACT_CIRCUIT_BREAKER", "20"))
    raw_writes: list[dict[str, Any]] = []
    rows_written = 0
    errors = 0
    consecutive_errors = 0
    for accession_number in selected_accessions:
        if consecutive_errors >= _CONSECUTIVE_ERROR_LIMIT:
            _emit_pipeline_event(
                "filing_artifact_circuit_open",
                consecutive_errors=consecutive_errors,
                remaining_accessions=len(selected_accessions) - errors - rows_written,
                run_id=sync_run_id,
            )
            break
        try:
            if fetch_artifacts:
                from edgar_warehouse.infrastructure.filing_artifact_service import refresh_filing_artifacts

                artifact_result = refresh_filing_artifacts(
                    context=context,
                    db=db,
                    accession_number=accession_number,
                    sync_run_id=sync_run_id,
                    download_bytes=_download_sec_bytes,
                    force=force,
                )
                raw_writes.extend(artifact_result["raw_writes"])
                rows_written += int(artifact_result["attachment_count"])
                _time.sleep(float(os.environ.get("WAREHOUSE_ARTIFACT_REQUEST_DELAY", "1.0")))
            if run_parsers:
                rows_written += _run_parse_pipeline(
                    db=db,
                    accession_number=accession_number,
                    sync_run_id=sync_run_id,
                )
            consecutive_errors = 0
        except Exception as exc:
            errors += 1
            consecutive_errors += 1
            _emit_pipeline_event(
                "filing_artifact_failed",
                accession_number=accession_number,
                error=str(exc),
                run_id=sync_run_id,
            )
    _emit_pipeline_event(
        "filing_artifact_pipeline_completed",
        accession_count=len(selected_accessions),
        raw_object_count=len(raw_writes),
        rows_written=rows_written,
        errors=errors,
        run_id=sync_run_id,
    )
    return {"raw_writes": raw_writes, "rows_written": rows_written, "rows_skipped": errors}


def _configured_parser_accessions(db: SilverDatabase, accession_numbers: list[str]) -> list[str]:
    selected: list[str] = []
    for accession_number in _dedupe_strings(accession_numbers):
        filing = db.get_filing(accession_number)
        if filing is None:
            continue
        if _is_configured_parser_form(filing.get("form")):
            selected.append(accession_number)
    return selected


def _is_configured_parser_form(form_type: Any) -> bool:
    normalized = str(form_type or "").strip().upper()
    return normalized in OWNERSHIP_FORMS or normalized in ADV_FORMS


def _run_parse_ownership_bronze(
    *,
    context: "WarehouseCommandContext",
    db: "SilverDatabase",
    sync_run_id: str,
    metrics: dict[str, Any],
    limit: int | None = None,
    accession_list: list[str] | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Parse Form 3/4/5 ownership XMLs that already exist in bronze into silver.

    Reads primary XML through the artifact registry (sec_filing_attachment +
    sec_raw_object + read_bytes) — no S3 prefix listing, no SEC API calls.
    Idempotent: skips accessions already present in sec_ownership_reporting_owner.

    Args:
        context: Warehouse command context (bronze_root, silver_root, etc.)
        db: Silver database connection for queries and merges.
        sync_run_id: Run ID for audit trail and event payloads.
        metrics: Mutable dict; populated with parsed/skipped/errors/missing_artifacts/rows_written.
        limit: Optional cap on the number of accessions to process.
        accession_list: Optional explicit list of accession numbers to process
            (filters the sec_company_filing query result to this set).
    """
    from edgar_warehouse.parsers.ownership import parse_ownership

    filings = db.fetch(
        """
        SELECT f.accession_number, f.cik, f.form
        FROM sec_company_filing f
        WHERE f.form IN ('3','3/A','4','4/A','5','5/A')
        ORDER BY f.cik, f.report_date
        """
    )

    # Apply optional accession filter
    if accession_list is not None:
        allowed = set(accession_list)
        filings = [f for f in filings if f["accession_number"] in allowed]

    already_parsed: set[str] = {
        row["accession_number"]
        for row in db.fetch("SELECT DISTINCT accession_number FROM sec_ownership_reporting_owner")
    }

    # Apply optional limit after skip-filter so the limit counts processable accessions
    if limit is not None:
        filings = filings[:limit]

    total = len(filings)
    parsed_count = skipped_count = error_count = missing_artifact_count = 0
    rows_written = 0

    _emit_pipeline_event(
        "parse_ownership_bronze_started",
        total_filings=total,
        already_parsed=len(already_parsed),
        run_id=sync_run_id,
    )

    for filing in filings:
        accession = filing["accession_number"]
        form = filing["form"]

        if accession in already_parsed:
            skipped_count += 1
            continue

        try:
            xml_bytes = _read_primary_artifact_bytes(db, accession)
        except WarehouseRuntimeError as exc:
            missing_artifact_count += 1
            _emit_pipeline_event(
                "parse_ownership_bronze_missing_artifact",
                accession_number=accession,
                reason=str(exc)[:200],
                run_id=sync_run_id,
            )
            continue

        try:
            xml_content = xml_bytes.decode("utf-8", errors="replace")
            parsed = parse_ownership(accession, xml_content, form)

            rows_written += db.merge_ownership_reporting_owners(
                parsed.get("sec_ownership_reporting_owner", []), sync_run_id
            )
            rows_written += db.merge_ownership_non_derivative_txns(
                parsed.get("sec_ownership_non_derivative_txn", []), sync_run_id
            )
            rows_written += db.merge_ownership_derivative_txns(
                parsed.get("sec_ownership_derivative_txn", []), sync_run_id
            )
            already_parsed.add(accession)
            parsed_count += 1

        except Exception as exc:
            error_count += 1
            _emit_pipeline_event(
                "parse_ownership_bronze_error",
                accession_number=accession,
                error=str(exc)[:200],
                run_id=sync_run_id,
            )

    _emit_pipeline_event(
        "parse_ownership_bronze_completed",
        total=total,
        parsed=parsed_count,
        skipped=skipped_count,
        errors=error_count,
        missing_artifacts=missing_artifact_count,
        rows_written=rows_written,
        run_id=sync_run_id,
    )
    metrics["parsed"] = parsed_count
    metrics["skipped"] = skipped_count
    metrics["errors"] = error_count
    metrics["missing_artifacts"] = missing_artifact_count
    metrics["rows_written"] = rows_written
    return [], metrics


def _run_parse_adv_bronze(
    *,
    context: "WarehouseCommandContext",
    db: "SilverDatabase",
    sync_run_id: str,
    metrics: dict[str, Any],
    limit: int | None = None,
    accession_list: list[str] | None = None,
    explicit_artifacts: list[Any] | tuple[Any, ...] | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Parse ADV-family filings already captured in bronze into silver ADV tables."""
    from edgar_warehouse.application.adv_bronze_discovery import (
        discover_adv_bronze_artifacts,
        read_adv_bronze_artifacts,
    )
    from edgar_warehouse.parsers.adv import parse_adv

    already_parsed: set[str] = {
        row["accession_number"]
        for row in db.fetch("SELECT DISTINCT accession_number FROM sec_adv_filing")
        if row["accession_number"]
    }
    initial_already_parsed_count = len(already_parsed)
    discovery = discover_adv_bronze_artifacts(
        db,
        accession_list=accession_list,
        explicit_artifacts=explicit_artifacts,
        limit=None,
    )

    selected_candidates = []
    skipped_count = 0
    for candidate in discovery.candidates:
        if candidate.accession_number in already_parsed:
            skipped_count += 1
            _emit_pipeline_event(
                "parse_adv_bronze_skipped_already_parsed",
                accession_number=candidate.accession_number,
                source_kind=candidate.source_kind,
                run_id=sync_run_id,
            )
            continue
        selected_candidates.append(candidate)

    if limit is not None:
        selected_candidates = selected_candidates[:limit]

    explicit_count = len(explicit_artifacts or [])
    missing_artifact_count = len(discovery.issues)
    unreadable_artifact_count = 0
    parsed_count = 0
    error_count = 0
    rows_written = 0

    _emit_pipeline_event(
        "parse_adv_bronze_started",
        discovered=len(discovery.candidates),
        selected=len(selected_candidates),
        already_parsed=initial_already_parsed_count,
        skipped=skipped_count,
        missing_artifacts=missing_artifact_count,
        explicit_artifacts=explicit_count,
        run_id=sync_run_id,
    )

    for issue in discovery.issues:
        _emit_pipeline_event(
            "parse_adv_bronze_missing_artifact",
            accession_number=issue.accession_number,
            storage_path=issue.storage_path,
            source_kind=issue.source_kind,
            reason=issue.reason,
            detail=(issue.detail or "")[:200] or None,
            run_id=sync_run_id,
        )

    read_result = read_adv_bronze_artifacts(selected_candidates, read_bytes_fn=read_bytes)
    unreadable_artifact_count = len(read_result.issues)
    for issue in read_result.issues:
        _emit_pipeline_event(
            "parse_adv_bronze_unreadable_artifact",
            accession_number=issue.accession_number,
            storage_path=issue.storage_path,
            source_kind=issue.source_kind,
            reason=issue.reason,
            detail=(issue.detail or "")[:200] or None,
            run_id=sync_run_id,
        )

    for bronze_payload in read_result.payloads:
        candidate = bronze_payload.candidate
        try:
            parsed = parse_adv(
                candidate.accession_number,
                bronze_payload.payload.decode("utf-8", errors="replace"),
                candidate.form,
                candidate.cik,
            )

            rows_written += db.merge_adv_filings(parsed.get("sec_adv_filing", []), sync_run_id)
            rows_written += db.merge_adv_offices(parsed.get("sec_adv_office", []), sync_run_id)
            rows_written += db.merge_adv_disclosure_events(
                parsed.get("sec_adv_disclosure_event", []),
                sync_run_id,
            )
            rows_written += db.merge_adv_private_funds(parsed.get("sec_adv_private_fund", []), sync_run_id)
            already_parsed.add(candidate.accession_number)
            parsed_count += 1
        except Exception as exc:
            error_count += 1
            _emit_pipeline_event(
                "parse_adv_bronze_error",
                accession_number=candidate.accession_number,
                source_kind=candidate.source_kind,
                error=str(exc)[:200],
                run_id=sync_run_id,
            )

    _emit_pipeline_event(
        "parse_adv_bronze_completed",
        discovered=len(discovery.candidates),
        selected=len(selected_candidates),
        parsed=parsed_count,
        skipped=skipped_count,
        missing_artifacts=missing_artifact_count,
        unreadable_artifacts=unreadable_artifact_count,
        errors=error_count,
        rows_written=rows_written,
        explicit_artifacts=explicit_count,
        run_id=sync_run_id,
    )
    metrics["discovered"] = len(discovery.candidates)
    metrics["selected"] = len(selected_candidates)
    metrics["parsed"] = parsed_count
    metrics["skipped"] = skipped_count
    metrics["missing_artifacts"] = missing_artifact_count
    metrics["unreadable_artifacts"] = unreadable_artifact_count
    metrics["errors"] = error_count
    metrics["rows_written"] = rows_written
    metrics["explicit_artifacts"] = explicit_count
    metrics["already_parsed"] = initial_already_parsed_count
    return [], metrics


def _artifact_policy_fetches(policy: str) -> bool:
    normalized = _normalize_policy(policy)
    if normalized in {"none", "skip", "disabled", "off"}:
        return False
    if normalized in {"all_attachments", "configured_forms"}:
        return True
    raise WarehouseRuntimeError(f"Unsupported artifact_policy: {policy}")


def _parser_policy_runs(policy: str) -> bool:
    normalized = _normalize_policy(policy)
    if normalized in {"none", "skip", "disabled", "off"}:
        return False
    if normalized == "configured_forms":
        return True
    raise WarehouseRuntimeError(f"Unsupported parser_policy: {policy}")


def _normalize_policy(policy: str) -> str:
    return str(policy or "").strip().lower().replace("-", "_")


def _capture_submission_bronze_snapshot(
    *,
    context: WarehouseCommandContext,
    db: "SilverDatabase",
    cik: int,
    include_pagination: bool,
    fetch_date: date,
    force: bool,
) -> dict[str, Any]:
    main_snapshot = _capture_submissions_main(
        context=context, db=db, cik=cik, fetch_date=fetch_date, force=force,
    )
    raw_writes = [main_snapshot["write_record"]]
    main_payload = main_snapshot["payload"]
    pagination_snapshots: list[dict[str, Any]] = []

    manifest_file_names = _pagination_file_names(main_payload) if include_pagination else []
    for file_name in manifest_file_names:
        pagination_snapshot = _capture_submissions_pagination(
            context=context,
            db=db,
            cik=cik,
            file_name=file_name,
            fetch_date=fetch_date,
            force=force,
        )
        pagination_snapshots.append(
            {
                "file_name": file_name,
                "payload": pagination_snapshot["payload"],
                "write_record": pagination_snapshot["write_record"],
            }
        )
        raw_writes.append(pagination_snapshot["write_record"])

    return {
        "cik": cik,
        "include_pagination": include_pagination,
        "main_payload": main_payload,
        "main_write_record": main_snapshot["write_record"],
        "manifest_file_names": manifest_file_names,
        "pagination_snapshots": pagination_snapshots,
        "raw_writes": raw_writes,
    }


def _apply_submission_snapshot_to_silver(
    *,
    db: SilverDatabase,
    sync_run_id: str,
    snapshot: dict[str, Any],
    force: bool,
    load_mode: str,
    recent_limit: int | None,
    now: datetime,
) -> dict[str, Any]:
    raw_writes: list[dict[str, Any]] = []
    rows_written = 0
    rows_skipped = 0
    cik = int(snapshot["cik"])
    existing_state = db.get_company_sync_state(cik) or {"tracking_status": "bootstrap_pending"}
    main_write_record = snapshot["main_write_record"]
    main_payload = snapshot["main_payload"]
    raw_writes.append(main_write_record)
    pagination_snapshots = list(snapshot["pagination_snapshots"])
    pagination_payloads = [
        (str(item["file_name"]), item["payload"])
        for item in pagination_snapshots
    ]
    pagination_write_records = [
        item["write_record"]
        for item in pagination_snapshots
    ]
    pagination_same = True

    for file_name, write_record in zip(snapshot["manifest_file_names"], pagination_write_records):
        raw_writes.append(write_record)
        checkpoint = db.get_source_checkpoint("submissions_pagination", f"file:{file_name}")
        if force or checkpoint is None or checkpoint.get("last_sha256") != write_record["sha256"]:
            pagination_same = False

    main_checkpoint = db.get_source_checkpoint("submissions_main", f"cik:{cik}")
    main_same = (
        (not force)
        and main_checkpoint is not None
        and main_checkpoint.get("last_sha256") == main_write_record["sha256"]
    )
    all_same = main_same and pagination_same

    for write_record in [main_write_record, *pagination_write_records]:
        source_name = write_record["source_name"]
        source_key = f"cik:{cik}" if source_name == "submissions_main" else f"file:{Path(write_record['relative_path']).name}"
        db.upsert_source_checkpoint(
            {
                "source_name": source_name,
                "source_key": source_key,
                "raw_object_id": write_record["sha256"],
                "last_success_at": now,
                "last_sha256": write_record["sha256"],
                # Store the bronze path so future runs can read without re-downloading
                "bronze_path": write_record.get("path", ""),
            }
        )

    result: dict[str, Any]
    if all_same:
        rows_skipped = 1 + len(pagination_payloads)
        recent_rows = stage_recent_filing_loader(
            main_payload,
            cik,
            sync_run_id,
            main_write_record["sha256"],
            load_mode,
            recent_limit=recent_limit,
        )
        result = {
            "rows_written": 0,
            "recent_rows": recent_rows,
            "manifest_rows": stage_manifest_loader(main_payload, cik, sync_run_id, main_write_record["sha256"], load_mode),
            "recent_accessions": [
                row["accession_number"]
                for row in recent_rows
                if row.get("accession_number")
            ],
            "pagination_accessions": [],
        }
    else:
        result = db.stage_submission(
            cik=cik,
            main_payload=main_payload,
            pagination_payloads=pagination_payloads,
            sync_run_id=sync_run_id,
            raw_object_id=main_write_record["sha256"],
            load_mode=load_mode,
            recent_limit=recent_limit,
        )
        rows_written += int(result["rows_written"])

    all_filing_rows = list(result["recent_rows"])
    pagination_rows_for_accessions: list[dict[str, Any]] = []
    for _file_name, pagination_payload in pagination_payloads:
        pagination_rows = stage_pagination_filing_loader(
            pagination_payload,
            cik,
            sync_run_id,
            main_write_record["sha256"],
            load_mode,
        )
        pagination_rows_for_accessions.extend(pagination_rows)
        all_filing_rows.extend(pagination_rows)

    latest_filing_date = _latest_filing_date(all_filing_rows)
    latest_acceptance_datetime = _latest_acceptance_datetime(all_filing_rows)
    include_pagination = bool(snapshot["include_pagination"])
    pagination_files_expected = len(snapshot["manifest_file_names"])
    pagination_files_loaded = len(snapshot["manifest_file_names"]) if include_pagination else 0
    bootstrap_completed_at = existing_state.get("bootstrap_completed_at")
    pagination_completed_at = existing_state.get("pagination_completed_at")
    tracking_status = existing_state.get("tracking_status", "active")
    if load_mode == "bootstrap_full":
        tracking_status = "bootstrap_pending"
        if include_pagination and pagination_files_loaded == pagination_files_expected:
            tracking_status = "active"
            bootstrap_completed_at = now
            pagination_completed_at = now
    elif tracking_status == "bootstrap_pending" and include_pagination and pagination_files_loaded == pagination_files_expected:
        tracking_status = "active"
        bootstrap_completed_at = bootstrap_completed_at or now
        pagination_completed_at = now
    elif tracking_status not in {"active", "paused", "historical_complete", "error"}:
        tracking_status = "active"

    db.upsert_company_sync_state(
        {
            "cik": cik,
            "tracking_status": tracking_status,
            "bootstrap_completed_at": bootstrap_completed_at,
            "last_main_sync_at": now,
            "last_main_raw_object_id": main_write_record["sha256"],
            "last_main_sha256": main_write_record["sha256"],
            "latest_filing_date_seen": latest_filing_date,
            "latest_acceptance_datetime_seen": latest_acceptance_datetime,
            "pagination_files_expected": pagination_files_expected if include_pagination else 0,
            "pagination_files_loaded": pagination_files_loaded if include_pagination else 0,
            "pagination_completed_at": pagination_completed_at,
            "next_sync_after": now + timedelta(days=1),
            "last_error_message": None,
        }
    )
    _sync_mdm_tracking_status(cik, tracking_status)
    return {
        "raw_writes": raw_writes,
        "rows_written": rows_written,
        "rows_skipped": rows_skipped,
        "recent_accessions": _dedupe_strings(result["recent_accessions"]),
        "pagination_accessions": _dedupe_strings(
            [
                row["accession_number"]
                for row in pagination_rows_for_accessions
                if row.get("accession_number")
            ]
        ),
    }


def _sync_reference_data(
    *,
    context: WarehouseCommandContext,
    db: SilverDatabase,
    sync_run_id: str,
    fetch_date: date,
    source_names: list[str] | None = None,
    seed_company_sync_state: bool = True,
) -> dict[str, Any]:
    selected_sources = source_names or ["company_tickers", "company_tickers_exchange"]
    raw_writes: list[dict[str, Any]] = []
    rows_written = 0
    rows_skipped = 0
    seed_document: dict[str, Any] | None = None
    now = datetime.now(UTC)
    capture_specs = default_capture_spec_factory()

    for spec in capture_specs.references(fetch_date, selected_sources):
        from edgar_warehouse.silver_store import _parse_company_ticker_rows

        # Idempotency: check bronze cache before hitting SEC API.
        # Reference data (company tickers) changes infrequently — re-downloading
        # on every bootstrap run is unnecessary and wastes API quota.
        cached_ref = _read_bronze_if_cached(
            bronze_root=context.bronze_root,
            db=db,
            source_name=spec.source_name,
            source_key="global",
            source_url=spec.source_url or "",
            relative_path=spec.relative_path,
        )
        if cached_ref is not None:
            write_record = cached_ref["write_record"]
            document = cached_ref["payload"]
            rows_skipped += 1
        else:
            raw_payload = _download_sec_bytes(url=spec.source_url or "", identity=context.identity)
            write_record = _write_bronze_object(
                context=context,
                relative_path=spec.relative_path,
                source_name=spec.source_name,
                source_url=spec.source_url or "",
                payload=raw_payload,
            )
            document = _decode_json_bytes(raw_payload, spec.source_url or "")

        raw_writes.append(write_record)
        rows = _parse_company_ticker_rows(document)
        checkpoint = db.get_source_checkpoint(spec.source_name, "global")
        if cached_ref is None and (not checkpoint or checkpoint.get("last_sha256") != write_record["sha256"]):
            rows_written += db.replace_company_tickers(rows, sync_run_id, source_name=spec.source_name)
        db.upsert_source_checkpoint(
            {
                "source_name": spec.source_name,
                "source_key": "global",
                "raw_object_id": write_record["sha256"],
                "last_success_at": now,
                "last_sha256": write_record["sha256"],
                "bronze_path": write_record.get("path", ""),
            }
        )
        if rows and (spec.source_name == "company_tickers_exchange" or seed_document is None):
            seed_document = document
        if seed_company_sync_state:
            for row in rows:
                existing = db.get_company_sync_state(int(row["cik"]))
                db.upsert_company_sync_state(
                    {
                        "cik": int(row["cik"]),
                        "tracking_status": existing.get("tracking_status", "bootstrap_pending") if existing else "bootstrap_pending",
                        "last_error_message": None,
                    }
                )

    return {
        "raw_writes": raw_writes,
        "rows_written": rows_written,
        "rows_skipped": rows_skipped,
        "seed_document": seed_document,
    }



def _write_cik_universe_batches(
    context: WarehouseCommandContext,
    rows: list[dict[str, Any]],
    fetch_date: date,
    sync_run_id: str,
    batch_size: int = 100,
) -> str:
    """Write the CIK universe as pre-batched JSON Lines to the bronze root.

    Each line is {"cik_list": "cik1,cik2,..."} for use by the Distributed Map
    bootstrap-batch iterator.

    Path uses run_id only (no date component) so the Step Function can construct
    the key deterministically from $$.Execution.Name without date extraction.

    Returns the full S3/local path to the JSON Lines file.
    """
    relative_path = default_capture_spec_factory().cik_universe_batches(sync_run_id).relative_path
    lines = []
    ciks = [str(row["cik"]) for row in rows]
    for i in range(0, len(ciks), batch_size):
        batch = ciks[i : i + batch_size]
        lines.append(json.dumps({"cik_list": ",".join(batch)}))
    content = "\n".join(lines) + ("\n" if lines else "")
    return context.bronze_root.write_text(relative_path, content)


def _list_bronze_submission_ciks(context: WarehouseCommandContext) -> list[str]:
    """List distinct CIKs that have submissions bronze data, by listing S3/local
    directly (no SEC calls, no silver/MDM bookkeeping dependency).
    """
    submissions_root = default_path_resolver().submissions_cik_root_path()
    names = context.bronze_root.list_child_names(submissions_root)
    ciks: set[str] = set()
    for name in names:
        if not name.startswith("cik="):
            continue
        cik = name[len("cik="):].strip()
        if cik.isdigit():
            ciks.add(cik)
    return sorted(ciks, key=int)


def _reference_sources_for_scope(scope_key: str) -> list[str]:
    normalized = scope_key.strip().lower()
    if normalized in {"", "all", "reference"}:
        return ["company_tickers", "company_tickers_exchange"]
    if normalized in {"company_tickers", "company_tickers_exchange"}:
        return [normalized]
    raise WarehouseRuntimeError(f"Unsupported reference scope_key: {scope_key}")


def _capture_submissions_main(
    *,
    context: WarehouseCommandContext,
    db: "SilverDatabase",
    cik: int,
    fetch_date: date,
    force: bool,
) -> dict[str, Any]:
    capture_spec = default_capture_spec_factory().submissions_main(cik, fetch_date)

    # Idempotency: consult the silver checkpoint before hitting the SEC API.
    # If force=False and the bronze file we wrote last time is still intact,
    # reuse it.  This prevents duplicate bronze files across bootstrap re-runs
    # and eliminates redundant SEC API calls for data that hasn't changed.
    if not force:
        cached = _read_bronze_if_cached(
            bronze_root=context.bronze_root,
            db=db,
            source_name=capture_spec.source_name,
            source_key=f"cik:{cik}",
            source_url=capture_spec.source_url or "",
            relative_path=capture_spec.relative_path,
            cik=cik,
        )
        if cached is not None:
            return cached
        # No local silver checkpoint (e.g. fresh silver DB that never processed this
        # CIK), but bronze may already exist in storage from another environment's
        # run. Check by CIK before falling back to a live SEC call.
        cached = _read_bronze_by_glob_if_present(
            bronze_root=context.bronze_root,
            source_name=capture_spec.source_name,
            source_url=capture_spec.source_url or "",
            relative_glob=default_path_resolver().submissions_main_glob(cik),
            cik=cik,
        )
        if cached is not None:
            return cached

    payload_bytes = _download_sec_bytes(url=capture_spec.source_url or "", identity=context.identity)
    write_record = _write_bronze_object(
        context=context,
        relative_path=capture_spec.relative_path,
        source_name=capture_spec.source_name,
        source_url=capture_spec.source_url or "",
        payload=payload_bytes,
        cik=cik,
    )
    return {
        "payload": _decode_json_bytes(payload_bytes, capture_spec.source_url or ""),
        "write_record": write_record,
    }


def _capture_submissions_pagination(
    *,
    context: WarehouseCommandContext,
    db: "SilverDatabase",
    cik: int,
    file_name: str,
    fetch_date: date,
    force: bool,
) -> dict[str, Any]:
    capture_spec = default_capture_spec_factory().submissions_pagination(cik, file_name, fetch_date)

    if not force:
        cached = _read_bronze_if_cached(
            bronze_root=context.bronze_root,
            db=db,
            source_name=capture_spec.source_name,
            source_key=f"file:{file_name}",
            source_url=capture_spec.source_url or "",
            relative_path=capture_spec.relative_path,
            cik=cik,
        )
        if cached is not None:
            return cached
        cached = _read_bronze_by_glob_if_present(
            bronze_root=context.bronze_root,
            source_name=capture_spec.source_name,
            source_url=capture_spec.source_url or "",
            relative_glob=default_path_resolver().submissions_pagination_glob(cik, file_name),
            cik=cik,
        )
        if cached is not None:
            return cached

    payload_bytes = _download_sec_bytes(url=capture_spec.source_url or "", identity=context.identity)
    write_record = _write_bronze_object(
        context=context,
        relative_path=capture_spec.relative_path,
        source_name=capture_spec.source_name,
        source_url=capture_spec.source_url or "",
        payload=payload_bytes,
        cik=cik,
    )
    return {
        "payload": _decode_json_bytes(payload_bytes, capture_spec.source_url or ""),
        "write_record": write_record,
    }


def _read_bronze_by_glob_if_present(
    *,
    bronze_root: "StorageLocation",
    source_name: str,
    source_url: str,
    relative_glob: str,
    cik: int | None = None,
) -> "dict[str, Any] | None":
    """Return cached write_record+payload for a bronze file matching relative_glob.

    Fallback for when no silver checkpoint exists for this source_key (e.g. a fresh
    silver database that never processed this CIK locally) but bronze may already
    exist in S3/local storage from another environment's run (e.g. synced in via
    `aws s3 sync`). Without this, _read_bronze_if_cached's checkpoint-only lookup
    always misses on a fresh silver database, forcing a redundant SEC API call even
    though the bronze file is already sitting in storage — defeating the purpose of
    seed-bronze-batches / bronze_seed_silver_gold ("zero new SEC calls").
    Returns None when no match exists or the matched file can't be read.
    """
    matches = bronze_root.find_existing(relative_glob)
    if not matches:
        return None
    chosen = matches[-1]
    try:
        payload_bytes = read_bytes(chosen)
    except Exception:
        return None
    chosen_relative = chosen[len(bronze_root.root) :].lstrip("/") if chosen.startswith(bronze_root.root) else chosen
    record: dict[str, Any] = {
        "layer": "bronze_raw",
        "path": chosen,
        "relative_path": chosen_relative,
        "sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "size_bytes": len(payload_bytes),
        "source_name": source_name,
        "source_url": source_url,
        "cached": True,
    }
    if cik is not None:
        record["cik"] = cik
    return {
        "payload": _decode_json_bytes(payload_bytes, source_url),
        "write_record": record,
    }


def _read_bronze_if_cached(
    *,
    bronze_root: "StorageLocation",
    db: "SilverDatabase",
    source_name: str,
    source_key: str,
    source_url: str,
    relative_path: str,
    cik: int | None = None,
) -> "dict[str, Any] | None":
    """Return cached write_record+payload if a valid bronze file exists for this source_key.

    Looks up the silver checkpoint for the previously stored bronze_path and SHA256.
    If the file is still readable and the SHA matches, returns it so the caller
    skips the SEC API call entirely — no duplicate bronze file is written.
    source_url and relative_path come from the caller's capture_spec (they are
    not stored in the checkpoint table).
    Returns None when no valid cache entry exists (first run, force=True, or corrupt file).
    """
    checkpoint = db.get_source_checkpoint(source_name, source_key)
    if checkpoint is None:
        return None
    bronze_path: str | None = checkpoint.get("bronze_path")
    last_sha256: str | None = checkpoint.get("last_sha256")
    if not bronze_path or not last_sha256:
        return None
    try:
        payload_bytes = read_bytes(bronze_path)
    except Exception:
        return None
    if hashlib.sha256(payload_bytes).hexdigest() != last_sha256:
        return None
    record: dict[str, Any] = {
        "layer": "bronze_raw",
        "path": bronze_path,
        "relative_path": relative_path,   # caller's spec — semantically correct
        "sha256": last_sha256,
        "size_bytes": len(payload_bytes),
        "source_name": source_name,
        "source_url": source_url,          # caller's spec — not stored in checkpoint
        "cached": True,
    }
    if cik is not None:
        record["cik"] = cik
    return {
        "payload": _decode_json_bytes(payload_bytes, source_url),
        "write_record": record,
    }


def _capture_reconcile_snapshot(
    *,
    context: WarehouseCommandContext,
    db: "SilverDatabase",
    cik: int,
    fetch_date: date,
    force: bool = True,
) -> dict[str, Any]:
    snapshot = _capture_submissions_main(
        context=context, db=db, cik=cik, fetch_date=fetch_date, force=force,
    )
    snapshot["write_record"]["source_name"] = "submissions_main"
    return snapshot


def _load_daily_index_for_date(
    *,
    context: WarehouseCommandContext,
    db: SilverDatabase,
    target_date: date,
    sync_run_id: str,
    now: datetime,
    force: bool,
) -> dict[str, Any]:
    daily_index_spec = default_capture_spec_factory().daily_index(target_date)
    source_url = daily_index_spec.source_url or ""
    expected_available_at = _expected_available_at(target_date)
    existing = db.get_daily_index_checkpoint(target_date.isoformat())
    first_attempt_at = existing.get("first_attempt_at") if existing else now

    if not _is_business_day(target_date):
        db.upsert_daily_index_checkpoint(
            {
                "business_date": target_date.isoformat(),
                "source_key": f"date:{target_date.isoformat()}",
                "source_url": source_url,
                "expected_available_at": expected_available_at,
                "first_attempt_at": first_attempt_at,
                "last_attempt_at": now,
                "status": "skipped_non_business_day",
                "finalized_at": now,
            }
        )
        return {
            "raw_writes": [],
            "rows_written": 0,
            "rows_skipped": 1,
            "impacted_ciks": [],
            "status": "skipped_non_business_day",
        }

    if not force and existing and existing.get("status") == "succeeded":
        rows = db.get_daily_index_filings(target_date.isoformat())
        return {
            "raw_writes": [],
            "rows_written": 0,
            "rows_skipped": 1,
            "impacted_ciks": _dedupe_ints([int(row["cik"]) for row in rows if row.get("cik") is not None]),
            "status": "succeeded",
        }

    if now < expected_available_at:
        db.upsert_daily_index_checkpoint(
            {
                "business_date": target_date.isoformat(),
                "source_key": f"date:{target_date.isoformat()}",
                "source_url": source_url,
                "expected_available_at": expected_available_at,
                "first_attempt_at": first_attempt_at,
                "last_attempt_at": now,
                "status": "waiting_for_publish",
            }
        )
        return {
            "raw_writes": [],
            "rows_written": 0,
            "rows_skipped": 1,
            "impacted_ciks": [],
            "status": "waiting_for_publish",
        }

    db.upsert_daily_index_checkpoint(
        {
            "business_date": target_date.isoformat(),
            "source_key": f"date:{target_date.isoformat()}",
            "source_url": source_url,
            "expected_available_at": expected_available_at,
            "first_attempt_at": first_attempt_at,
            "last_attempt_at": now,
            "status": "running",
        }
    )
    try:
        payload = _download_sec_bytes(url=daily_index_spec.source_url or "", identity=context.identity)
        write_record = _write_bronze_object(
            context=context,
            relative_path=daily_index_spec.relative_path,
            source_name=daily_index_spec.source_name,
            source_url=daily_index_spec.source_url or "",
            payload=payload,
            business_date=target_date.isoformat(),
        )
        rows = stage_daily_index_filing_loader(
            payload=payload,
            business_date=target_date,
            sync_run_id=sync_run_id,
            raw_object_id=write_record["sha256"],
            source_url=source_url,
        )
        row_count = db.merge_daily_index_filings(rows, sync_run_id)
        distinct_cik_count = len({int(row["cik"]) for row in rows if row.get("cik") is not None})
        distinct_accession_count = len({row["accession_number"] for row in rows if row.get("accession_number")})
        db.upsert_daily_index_checkpoint(
            {
                "business_date": target_date.isoformat(),
                "source_key": f"date:{target_date.isoformat()}",
                "source_url": source_url,
                "expected_available_at": expected_available_at,
                "first_attempt_at": first_attempt_at,
                "last_attempt_at": now,
                "raw_object_id": write_record["sha256"],
                "last_sha256": write_record["sha256"],
                "row_count": row_count,
                "distinct_cik_count": distinct_cik_count,
                "distinct_accession_count": distinct_accession_count,
                "status": "succeeded",
                "finalized_at": now,
                "last_success_at": now,
            }
        )
        return {
            "raw_writes": [write_record],
            "rows_written": row_count,
            "rows_skipped": 0,
            "impacted_ciks": _dedupe_ints([int(row["cik"]) for row in rows if row.get("cik") is not None]),
            "status": "succeeded",
        }
    except WarehouseRuntimeError as exc:
        db.upsert_daily_index_checkpoint(
            {
                "business_date": target_date.isoformat(),
                "source_key": f"date:{target_date.isoformat()}",
                "source_url": source_url,
                "expected_available_at": expected_available_at,
                "first_attempt_at": first_attempt_at,
                "last_attempt_at": now,
                "status": "failed_retryable",
                "error_message": str(exc),
            }
        )
        return {
            "raw_writes": [],
            "rows_written": 0,
            "rows_skipped": 0,
            "impacted_ciks": [],
            "status": "failed_retryable",
        }


def _run_accession_resync(
    *,
    context: WarehouseCommandContext,
    db: SilverDatabase,
    sync_run_id: str,
    accession_number: str,
    include_artifacts: bool,
    include_text: bool,
    include_parsers: bool,
    force: bool,
) -> dict[str, Any]:
    raw_writes: list[dict[str, Any]] = []
    rows_written = 0
    filing = db.get_filing(accession_number)
    if filing is None:
        raise WarehouseRuntimeError(f"Unknown accession_number for targeted resync: {accession_number}")

    rows_written += db.merge_filings([filing], sync_run_id)
    if include_artifacts:
        from edgar_warehouse.infrastructure.filing_artifact_service import refresh_filing_artifacts

        artifact_result = refresh_filing_artifacts(
            context=context,
            db=db,
            accession_number=accession_number,
            sync_run_id=sync_run_id,
            download_bytes=_download_sec_bytes,
            force=force,
        )
        raw_writes.extend(artifact_result["raw_writes"])
        rows_written += int(artifact_result["attachment_count"])
    if include_text:
        from edgar_warehouse.infrastructure.filing_artifact_service import extract_filing_text

        text_row = extract_filing_text(context=context, db=db, accession_number=accession_number)
        rows_written += 1 if text_row else 0
    if include_parsers:
        rows_written += _run_parse_pipeline(db=db, accession_number=accession_number, sync_run_id=sync_run_id)
    return {"raw_writes": raw_writes, "rows_written": rows_written}


def _run_parse_pipeline(
    *,
    db: SilverDatabase,
    accession_number: str,
    sync_run_id: str,
) -> int:
    filing = db.get_filing(accession_number)
    if filing is None:
        return 0
    form_type = str(filing.get("form") or "").strip()
    parser_name, parser_version, form_family = _parser_metadata(form_type)
    parse_run_id = str(uuid.uuid4())
    db.start_parse_run(
        {
            "parse_run_id": parse_run_id,
            "accession_number": accession_number,
            "parser_name": parser_name,
            "parser_version": parser_version,
            "target_form_family": form_family,
        }
    )

    try:
        if form_family == "generic":
            db.complete_parse_run(parse_run_id, status="skipped", rows_written=0)
            return 0
        payload = _read_primary_artifact_bytes(db, accession_number)
        from edgar_warehouse.parsers import get_parser

        parser = get_parser(form_type)
        content = payload.decode("utf-8", errors="replace")
        if form_family == "ownership":
            parsed = parser(accession_number, content, form_type)
        else:
            parsed = parser(accession_number, content, form_type, filing.get("cik"))
        rows_written = 0
        rows_written += db.merge_ownership_reporting_owners(parsed.get("sec_ownership_reporting_owner", []), sync_run_id)
        rows_written += db.merge_ownership_non_derivative_txns(parsed.get("sec_ownership_non_derivative_txn", []), sync_run_id)
        rows_written += db.merge_ownership_derivative_txns(parsed.get("sec_ownership_derivative_txn", []), sync_run_id)
        rows_written += db.merge_adv_filings(parsed.get("sec_adv_filing", []), sync_run_id)
        rows_written += db.merge_adv_offices(parsed.get("sec_adv_office", []), sync_run_id)
        rows_written += db.merge_adv_disclosure_events(parsed.get("sec_adv_disclosure_event", []), sync_run_id)
        rows_written += db.merge_adv_private_funds(parsed.get("sec_adv_private_fund", []), sync_run_id)
        db.complete_parse_run(parse_run_id, status="succeeded", rows_written=rows_written)
        return rows_written
    except Exception as exc:
        db.complete_parse_run(
            parse_run_id,
            status="failed",
            error_code="parse_failed",
            error_message=str(exc),
            rows_written=0,
        )
        return 0


def _read_primary_artifact_bytes(db: SilverDatabase, accession_number: str) -> bytes:
    attachments = db.get_filing_attachments(accession_number)
    primary = next((row for row in attachments if row.get("is_primary")), None)
    if primary is None or not primary.get("raw_object_id"):
        raise WarehouseRuntimeError(f"No primary attachment found for accession {accession_number}")
    raw_object = db.get_raw_object(str(primary["raw_object_id"]))
    if raw_object is None:
        raise WarehouseRuntimeError(f"Missing raw object for accession {accession_number}")
    return read_bytes(str(raw_object["storage_path"]))


def _parser_metadata(form_type: str) -> tuple[str, str, str]:
    if form_type in OWNERSHIP_FORMS:
        module = importlib.import_module("edgar_warehouse.parsers.ownership")
        return str(module.PARSER_NAME), str(module.PARSER_VERSION), "ownership"
    if form_type in ADV_FORMS:
        module = importlib.import_module("edgar_warehouse.parsers.adv")
        return str(module.PARSER_NAME), str(module.PARSER_VERSION), "adv"
    return "generic_text_v1", "1", "generic"


def _capture_reference_files(context: WarehouseCommandContext, fetch_date: date) -> list[dict[str, Any]]:
    capture_specs = default_capture_spec_factory().references(fetch_date)
    return [
        _write_bronze_object(
            context=context,
            relative_path=spec.relative_path,
            source_name=spec.source_name,
            source_url=spec.source_url or "",
            payload=_download_sec_bytes(url=spec.source_url or "", identity=context.identity),
        )
        for spec in capture_specs
    ]


def _capture_daily_index_file(context: WarehouseCommandContext, target_date: date) -> tuple[dict[str, Any], list[int]]:
    capture_spec = default_capture_spec_factory().daily_index(target_date)
    payload = _download_sec_bytes(url=capture_spec.source_url or "", identity=context.identity)
    record = _write_bronze_object(
        context=context,
        relative_path=capture_spec.relative_path,
        source_name=capture_spec.source_name,
        source_url=capture_spec.source_url or "",
        payload=payload,
        business_date=target_date.isoformat(),
    )
    return record, _extract_impacted_ciks_from_daily_index(payload=payload, source_url=capture_spec.source_url or "")


def _capture_submissions_scope(
    context: WarehouseCommandContext,
    ciks: list[int],
    include_pagination: bool,
    fetch_date: date,
) -> tuple[list[dict[str, Any]], list[tuple[int, str, dict[str, Any], list[tuple[str, dict[str, Any]]]]]]:
    """Download submissions JSON for each CIK, write to bronze, and return staging data.

    Returns (write_records, silver_staging) where silver_staging is a list of
    (cik, raw_object_id, main_payload_dict, pagination_payloads) tuples.
    """
    raw_writes: list[dict[str, Any]] = []
    silver_staging: list[tuple[int, str, dict[str, Any], list[tuple[str, dict[str, Any]]]]] = []
    capture_specs = default_capture_spec_factory()

    for cik in ciks:
        main_spec = capture_specs.submissions_main(cik, fetch_date)
        main_payload_bytes = _download_sec_bytes(url=main_spec.source_url or "", identity=context.identity)
        write_record = _write_bronze_object(
            context=context,
            relative_path=main_spec.relative_path,
            source_name=main_spec.source_name,
            source_url=main_spec.source_url or "",
            payload=main_payload_bytes,
            cik=cik,
        )
        raw_writes.append(write_record)
        raw_object_id = write_record["sha256"]
        main_document = _decode_json_bytes(main_payload_bytes, main_spec.source_url or "")
        pagination_payloads: list[tuple[str, dict[str, Any]]] = []

        if include_pagination:
            for file_name in _pagination_file_names(main_document):
                pagination_spec = capture_specs.submissions_pagination(cik, file_name, fetch_date)
                pagination_payload_bytes = _download_sec_bytes(
                    url=pagination_spec.source_url or "",
                    identity=context.identity,
                )
                raw_writes.append(
                    _write_bronze_object(
                        context=context,
                        relative_path=pagination_spec.relative_path,
                        source_name=pagination_spec.source_name,
                        source_url=pagination_spec.source_url or "",
                        payload=pagination_payload_bytes,
                        cik=cik,
                    )
                )
                pagination_payloads.append(
                    (
                        file_name,
                        _decode_json_bytes(pagination_payload_bytes, pagination_spec.source_url or ""),
                    )
                )

        silver_staging.append((cik, raw_object_id, main_document, pagination_payloads))

    return raw_writes, silver_staging


def _capture_catch_up_daily_form_index(
    context: WarehouseCommandContext,
    db: SilverDatabase,
    sync_run_id: str,
    end_date: date,
    now: datetime,
    force: bool,
) -> dict[str, Any]:
    """Fetch missing daily indexes in ascending order up to end_date."""
    last_success = db.get_last_successful_checkpoint_date()

    if last_success is not None:
        start_date = _next_business_day(date.fromisoformat(last_success))
    else:
        start_date = end_date

    raw_writes: list[dict[str, Any]] = []
    rows_written = 0
    rows_skipped = 0
    status = "succeeded"

    for target_date in _date_range(start_date, end_date):
        result = _load_daily_index_for_date(
            context=context,
            db=db,
            target_date=target_date,
            sync_run_id=sync_run_id,
            now=now,
            force=force,
        )
        raw_writes.extend(result["raw_writes"])
        rows_written += result["rows_written"]
        rows_skipped += result["rows_skipped"]
        if result["status"] in {"waiting_for_publish", "failed_retryable"}:
            status = "partial"
            break

    return {
        "raw_writes": raw_writes,
        "rows_written": rows_written,
        "rows_skipped": rows_skipped,
        "status": status,
    }


def _is_business_day(d: date) -> bool:
    return is_business_day(d)


def _expected_available_at(business_date: date) -> datetime:
    return expected_available_at(business_date)


def _write_bronze_object(
    context: WarehouseCommandContext,
    relative_path: str,
    source_name: str,
    source_url: str,
    payload: bytes,
    *,
    business_date: str | None = None,
    cik: int | None = None,
) -> dict[str, Any]:
    destination = context.bronze_root.write_bytes(relative_path, payload)
    record: dict[str, Any] = {
        "layer": "bronze_raw",
        "path": destination,
        "relative_path": relative_path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "source_name": source_name,
        "source_url": source_url,
    }
    if business_date is not None:
        record["business_date"] = business_date
    if cik is not None:
        record["cik"] = cik
    return record


def _download_sec_bytes(url: str, identity: str) -> bytes:
    return download_sec_bytes(url, identity)


def _require_cik_list(raw_ciks: Any, command_name: str) -> list[int]:
    if not raw_ciks:
        raise WarehouseRuntimeError(f"{command_name} requires --cik-list or a seeded tracked universe")
    return [_parse_cik(value) for value in raw_ciks]


def _parse_cik(value: Any) -> int:
    return parse_cik(value)


def _get_mdm_tracked_ciks(status_filter: str) -> list[int]:
    """Query MDM for tracked CIKs. MDM is the sole source of truth for universe tracking.

    Raises WarehouseRuntimeError if MDM_DATABASE_URL is not set or MDM is unreachable.
    """
    import os
    url = os.environ.get("MDM_DATABASE_URL")
    if not url:
        raise WarehouseRuntimeError(
            "MDM_DATABASE_URL is required. Seed the universe with "
            "'edgar-warehouse mdm seed-universe' before running bootstrap commands."
        )
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.universe import get_tracked_ciks
    return get_tracked_ciks(get_engine(url), status_filter=status_filter)


def _sync_mdm_tracking_status(cik: int, status: str) -> None:
    """Update mdm_company.tracking_status after a company sync completes.

    Raises on failure — MDM is the tracking source of truth and write failures
    must surface rather than silently produce stale state.
    """
    import os
    url = os.environ.get("MDM_DATABASE_URL")
    if not url:
        raise WarehouseRuntimeError("MDM_DATABASE_URL is required for tracking status updates")
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.universe import update_tracking_status
    update_tracking_status(get_engine(url), cik, status)


def _resolve_target_ciks(
    *,
    raw_ciks: Any,
    command_name: str,
    tracking_status_filter: str,
) -> list[int]:
    if raw_ciks:
        return [_parse_cik(value) for value in raw_ciks]
    ciks = _get_mdm_tracked_ciks(tracking_status_filter)
    if ciks:
        return ciks
    raise WarehouseRuntimeError(
        f"{command_name} requires --cik-list or a seeded MDM universe "
        f"(tracking_status='{tracking_status_filter}'). "
        "Run 'edgar-warehouse mdm seed-universe' first."
    )


def _mdm_auto_enroll(ciks: list[int], *, scope_reason: str = "auto_discovered") -> None:
    """Enroll newly discovered CIKs into MDM with tracking_status='active'.

    Used by daily-incremental to register companies seen in the SEC daily index
    that are not yet in the MDM universe. Non-fatal — logs on failure rather than
    aborting the pipeline, since auto-enrollment is best-effort discovery.
    """
    if not ciks:
        return
    import os
    url = os.environ.get("MDM_DATABASE_URL")
    if not url:
        return
    try:
        from edgar_warehouse.mdm.database import get_engine
        from edgar_warehouse.mdm.universe import bulk_upsert_universe
        rows = [{"cik": cik, "ticker": str(cik), "exchange": None} for cik in ciks]
        bulk_upsert_universe(get_engine(url), rows, default_status="active")
    except Exception as exc:
        _emit_pipeline_event("mdm_auto_enroll_failed", scope_reason=scope_reason, error=str(exc), cik_count=len(ciks))


def _validate_window_args(cik_limit: int | None, cik_offset: int) -> None:
    """Validate --cik-limit and --cik-offset values. Raises WarehouseRuntimeError on invalid input."""
    if cik_limit is not None and cik_limit <= 0:
        raise WarehouseRuntimeError(
            f"--cik-limit must be a positive integer, got {cik_limit}"
        )
    if cik_offset < 0:
        raise WarehouseRuntimeError(
            f"--cik-offset must be a non-negative integer, got {cik_offset}"
        )


def _resolve_bootstrap_target_ciks(
    *,
    raw_ciks: Any,
    command_name: str,
    tracking_status_filter: str,
    cik_limit: int | None = None,
    cik_offset: int = 0,
) -> list[int]:
    """Resolve CIKs from MDM exclusively. SEC bronze is not consulted for scope.

    Applies deterministic windowing (cik_offset then cik_limit) after MDM lookup.
    """
    _validate_window_args(cik_limit, cik_offset)
    if raw_ciks:
        ciks = [_parse_cik(value) for value in raw_ciks]
    else:
        ciks = _get_mdm_tracked_ciks(tracking_status_filter)
        if not ciks:
            raise WarehouseRuntimeError(
                f"{command_name} found no companies with tracking_status='{tracking_status_filter}' in MDM. "
                "Run 'edgar-warehouse mdm seed-universe --tracking-status "
                f"{tracking_status_filter}' first."
            )
    # Apply windowing: offset first, then limit
    ciks = ciks[cik_offset:]
    if cik_limit is not None:
        ciks = ciks[:cik_limit]
    return ciks


def _resolve_reconcile_ciks(
    *,
    raw_ciks: Any,
    sample_limit: int | None,
) -> list[int]:
    ciks = [_parse_cik(value) for value in raw_ciks] if raw_ciks else _get_mdm_tracked_ciks("active")
    if sample_limit is not None:
        return ciks[: int(sample_limit)]
    return ciks


def _decode_json_bytes(payload: bytes, source_url: str) -> dict[str, Any]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WarehouseRuntimeError(f"Expected JSON payload from {source_url}") from exc
    if not isinstance(document, dict):
        raise WarehouseRuntimeError(f"Expected JSON object from {source_url}")
    return document


def _pagination_file_names(submissions_document: dict[str, Any]) -> list[str]:
    filings = submissions_document.get("filings", {})
    files = filings.get("files", []) if isinstance(filings, dict) else []
    if not isinstance(files, list):
        return []
    names: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        file_name = str(entry.get("name", "")).strip()
        if file_name:
            names.append(file_name)
    return names


def _filter_ciks_to_universe(impacted_ciks: list[int]) -> list[int]:
    """Return only CIKs that are active in the MDM tracked universe.

    Falls through to all impacted_ciks if MDM returns an empty active universe
    (cold-start guard so daily-incremental can run before the first seed).
    """
    tracked = _get_mdm_tracked_ciks("active")
    if not tracked:
        return impacted_ciks
    tracked_set = set(tracked)
    return [c for c in impacted_ciks if c in tracked_set]


def _extract_impacted_ciks_from_daily_index(payload: bytes, source_url: str) -> list[int]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WarehouseRuntimeError(f"Expected text daily index payload from {source_url}") from exc

    ciks: list[int] = []
    for line in text.splitlines():
        if "edgar/data/" not in line:
            continue
        match = _DAILY_INDEX_LINE_PATTERN.match(line.rstrip())
        if match is None:
            continue
        ciks.append(int(match.group("cik")))
    return _dedupe_ints(ciks)


def _apply_bronze_cik_limit(ciks: list[int]) -> list[int]:
    raw_limit = os.environ.get("WAREHOUSE_BRONZE_CIK_LIMIT", "").strip()
    if not raw_limit:
        return ciks
    warnings.warn("WAREHOUSE_BRONZE_CIK_LIMIT is deprecated; use --cik-limit/--cik-offset instead", DeprecationWarning, stacklevel=2)
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise WarehouseRuntimeError("WAREHOUSE_BRONZE_CIK_LIMIT must be a positive integer") from exc
    if limit <= 0:
        raise WarehouseRuntimeError("WAREHOUSE_BRONZE_CIK_LIMIT must be a positive integer")
    return ciks[:limit]


def _dedupe_ints(values: list[int]) -> list[int]:
    return dedupe_ints(values)


def _dedupe_strings(values: list[str]) -> list[str]:
    return dedupe_strings(values)


def _latest_filing_date(rows: list[dict[str, Any]]) -> date | None:
    return latest_filing_date(rows)


def _latest_acceptance_datetime(rows: list[dict[str, Any]]) -> datetime | None:
    return latest_acceptance_datetime(rows)


def _parse_acceptance_datetime(value: Any) -> datetime | None:
    return parse_acceptance_datetime(value)


def _next_business_day(value: date) -> date:
    return next_business_day(value)


def _previous_business_day(today: date) -> date:
    return previous_business_day(today)


def _latest_eligible_business_date(now: datetime) -> date:
    return latest_eligible_business_date(now)


def _us_federal_holidays(year: int) -> set[date]:
    return us_federal_holidays(year)


def _observed_date(day: date) -> date:
    return calendar_observed_date(day)


def _nth_weekday(year: int, month: int, weekday: int, ordinal: int) -> date:
    return calendar_nth_weekday(year, month, weekday, ordinal)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    return calendar_last_weekday(year, month, weekday)


def _date_range(start: date, end: date) -> list[date]:
    return calendar_date_range(start, end)


def _sync_mode_for_command(command_name: str) -> str:
    return sync_mode_for_command(command_name)


def _sync_scope_type_for_command(command_name: str, scope: dict[str, Any]) -> str:
    return sync_scope_type_for_command(command_name, scope)


def _sync_scope_key_for_command(command_name: str, scope: dict[str, Any]) -> str | None:
    return sync_scope_key_for_command(command_name, scope)


def _resolve_scope(
    command_name: str,
    arguments: dict[str, Any],
    now: datetime,
    silver_root: StorageLocation | None = None,
) -> dict[str, Any]:
    db = _open_silver_database(silver_root) if silver_root is not None else None
    if command_name == "bootstrap":
        return {
            "cik_list": arguments.get("cik_list"),
            "recent_limit": arguments.get("recent_limit"),
            "tracking_status_filter": arguments.get("tracking_status_filter"),
        }

    if command_name == "bootstrap-full":
        return {
            "cik_list": arguments.get("cik_list"),
            "tracking_status_filter": arguments.get("tracking_status_filter"),
        }

    if command_name == "bootstrap-next":
        return {
            "cik_limit": arguments.get("limit", 100),
            "tracking_status_filter": arguments.get("tracking_status_filter", "bootstrap_pending"),
        }

    if command_name == "daily-incremental":
        start_date = _parse_date(arguments.get("start_date"), "start_date")
        end_date = _parse_date(arguments.get("end_date"), "end_date")
        if end_date is None:
            end_date = _latest_eligible_business_date(now)
        if start_date is None:
            last_success = db.get_last_successful_checkpoint_date() if db is not None else None
            if last_success:
                start_date = _next_business_day(date.fromisoformat(last_success))
            else:
                start_date = end_date
        if start_date is None or end_date is None:
            raise WarehouseRuntimeError("daily_incremental could not resolve a business date range")
        if start_date > end_date:
            raise WarehouseRuntimeError("start_date must be on or before end_date")
        return {
            "business_date_start": start_date.isoformat(),
            "business_date_end": end_date.isoformat(),
            "tracking_status_filter": arguments.get("tracking_status_filter"),
        }

    if command_name == "load-daily-form-index-for-date":
        target_date = _parse_date(arguments.get("target_date"), "target_date")
        if target_date is None:
            raise WarehouseRuntimeError("target_date is required")
        return {"target_date": target_date.isoformat()}

    if command_name == "catch-up-daily-form-index":
        end_date = _parse_date(arguments.get("end_date"), "end_date")
        if end_date is None:
            end_date = _latest_eligible_business_date(now)
        return {"end_date": end_date.isoformat()}

    if command_name == "targeted-resync":
        return {
            "scope_key": arguments.get("scope_key"),
            "scope_type": arguments.get("scope_type"),
        }

    if command_name == "full-reconcile":
        return {
            "auto_heal": arguments.get("auto_heal"),
            "cik_list": arguments.get("cik_list"),
            "sample_limit": arguments.get("sample_limit"),
        }

    if command_name == "seed-universe":
        return {"run_date": now.date().isoformat()}

    if command_name == "bootstrap-batch":
        return {
            "cik_list": arguments.get("cik_list") or [],
            "include_pagination": arguments.get("include_pagination", True),
        }

    if command_name == "bootstrap-fundamentals":
        # Branch B counterpart of bootstrap-batch. CIK list + mode dispatch.
        return {
            "cik_list": arguments.get("cik_list") or [],
            "mode": arguments.get("mode") or "per-filing",
        }

    if command_name == "gold-refresh":
        # Scope is empty — bronze/silver are already complete.
        # _execute_warehouse builds gold because gold-refresh is in GOLD_AFFECTING_COMMANDS.
        return {}

    if command_name == "seed-silver-batches":
        return {
            "tracking_status_filter": arguments.get("tracking_status_filter") or "all",
            "batch_size": arguments.get("batch_size") or 100,
        }

    if command_name == "seed-bronze-batches":
        return {
            "batch_size": arguments.get("batch_size") or 100,
        }

    if command_name == "parse-ownership-bronze":
        return {
            "limit": arguments.get("limit"),
            "accession_list": arguments.get("accession_list"),
        }

    if command_name == "parse-adv-bronze":
        return {
            "limit": arguments.get("limit"),
            "accession_list": arguments.get("accession_list"),
            "explicit_artifact_count": len(arguments.get("artifacts") or []),
        }

    if command_name == "compute-windows":
        return {
            "window_size": arguments.get("window_size", 500),
        }

    if command_name == "write-run-summary":
        return {
            "from_windows_key": arguments.get("from_windows_key"),
        }

    raise WarehouseRuntimeError(f"Unsupported warehouse command: {command_name}")


def _planned_writes(command_name: str, command_path: str, run_id: str, scope: dict[str, Any]) -> dict[str, str]:
    return planned_writes(command_name, command_path, run_id, scope)


def _resolve_export_business_date(command_name: str, scope: dict[str, Any], now: datetime) -> str:
    return resolve_export_business_date(command_name, scope, now)


def _layer_manifest(
    command_name: str,
    run_id: str,
    layer: str,
    relative_path: str,
    arguments: dict[str, Any],
    scope: dict[str, Any],
    now: datetime,
    runtime_mode: str,
) -> dict[str, Any]:
    return layer_manifest(command_name, run_id, layer, relative_path, arguments, scope, now, runtime_mode)


def _snowflake_export_manifest(
    table_name: str,
    command_name: str,
    run_id: str,
    business_date: str,
    arguments: dict[str, Any],
    now: datetime,
    runtime_mode: str,
    row_count: int = 0,
    file_count: int = 0,
) -> dict[str, Any]:
    return snowflake_export_manifest(
        table_name=table_name,
        command_name=command_name,
        run_id=run_id,
        business_date=business_date,
        arguments=arguments,
        now=now,
        runtime_mode=runtime_mode,
        row_count=row_count,
        file_count=file_count,
    )


def _snowflake_export_run_manifest_relative_path(workflow_name: str, business_date: str, run_id: str) -> str:
    return snowflake_export_run_manifest_relative_path(workflow_name, business_date, run_id)


def _snowflake_export_run_manifest(
    *,
    environment_name: str,
    command_name: str,
    run_id: str,
    business_date: str,
    now: datetime,
    export_counts: dict[str, int],
) -> dict[str, Any]:
    return snowflake_export_run_manifest(
        environment_name=environment_name,
        command_name=command_name,
        run_id=run_id,
        business_date=business_date,
        now=now,
        export_counts=export_counts,
    )


def _snowflake_export_run_manifest_table(
    *,
    table_name: str,
    table_path: str,
    run_id: str,
    business_date: str,
    row_count: int,
) -> dict[str, Any]:
    return snowflake_export_run_manifest_table(
        table_name=table_name,
        table_path=table_path,
        run_id=run_id,
        business_date=business_date,
        row_count=row_count,
    )


def _error_payload(command_name: str, arguments: dict[str, Any], message: str, runtime_mode: str = "infrastructure_validation") -> dict[str, Any]:
    return {
        "arguments": arguments,
        "command": command_name,
        "message": message,
        "runtime_mode": runtime_mode,
        "status": "error",
    }


def _parse_date(value: Any, field_name: str) -> date | None:
    return parse_scope_date(value, field_name)


def _namespace_to_payload(args: Any) -> dict[str, Any]:
    payload = vars(args).copy()
    payload.pop("handler", None)
    return payload


def _resolve_run_id(arguments: dict[str, Any]) -> str:
    candidate = str(arguments.get("run_id", "") or "").strip()
    return candidate or str(uuid.uuid4())


def _warehouse_success_message(has_snowflake_exports: bool) -> str:
    return warehouse_success_message(has_snowflake_exports)
