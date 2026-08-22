"""Warehouse runtime helpers for infrastructure-oriented command execution."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Final, Iterable, Mapping

from edgar_warehouse.application.acquisition_command_registry import (
    acquisition_command_registration,
)
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
    filter_rows_by_min_filing_date,
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
    run_manifest,
    run_manifest_relative_path,
    snowflake_export_manifest,
    snowflake_export_run_manifest,
    snowflake_export_run_manifest_relative_path,
    snowflake_export_run_manifest_table,
    warehouse_success_message,
)
from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory, default_path_resolver
from edgar_warehouse.infrastructure.edgartools_sec_gateway import (
    download_bytes as _gateway_download_bytes,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.serving.silver_landing_writer import write_landing_export
from edgar_warehouse.silver_protection import compute_silver_fingerprint, merge_candidate_into_canonical
from edgar_warehouse.silver_support.session import open_silver_database, open_silver_shard

if TYPE_CHECKING:
    from edgar_warehouse.silver_store import SilverDatabase

SOURCE_EXPORT_COMMANDS = {
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
SNOWFLAKE_EXPORT_COMMANDS = SOURCE_EXPORT_COMMANDS | {"seed-universe"}


def _gold_publication_enabled(command_name: str, arguments: dict[str, Any]) -> bool:
    """Return whether this invocation owns a gold/Snowflake publication.

    ``bootstrap-next`` remains gold-affecting for standalone compatibility,
    but phased ``load_history`` windows explicitly defer publication to the
    workflow's single final ``gold-refresh`` task.
    """

    return command_name in SOURCE_EXPORT_COMMANDS and not (
        command_name == "bootstrap-next" and bool(arguments.get("silver_only"))
    )


def _snowflake_publication_enabled(command_name: str, arguments: dict[str, Any]) -> bool:
    """Return whether this invocation plans any Snowflake publication."""

    return command_name in SNOWFLAKE_EXPORT_COMMANDS and not (
        command_name == "bootstrap-next" and bool(arguments.get("silver_only"))
    )


def _planned_writes_for_publication(
    *,
    command_name: str,
    command_path: str,
    run_id: str,
    scope: dict[str, Any],
    include_gold: bool,
) -> dict[str, str]:
    """Filter the command's normal writes by this invocation's publication policy."""

    writes = _planned_writes(
        command_name=command_name,
        command_path=command_path,
        run_id=run_id,
        scope=scope,
    )
    if include_gold:
        return writes
    return {layer: path for layer, path in writes.items() if layer != "gold"}


# Single source of truth for the run-level lease shared by the Daily Identity
# Refresh and the Identity Backstop Sweep (release-readiness ticket 45/49) --
# acquire/release must reference the exact same name, or the mutual-exclusion
# mechanism silently breaks (masked for up to 18h by the stale-reclaim window).
IDENTITY_REFRESH_LEASE_NAME = "daily_identity_refresh"

# Cross-command SEC-fetch mutual exclusion (release-readiness ticket 80,
# implementing pipeline-throughput-architecture ticket 09's decision): a
# separate pipeline_run_lease row so only one of the five SEC-fetching
# commands (daily_incremental, bootstrap, bootstrap_full, targeted_resync,
# bootstrap_batch) runs its SEC-request-heavy phase at a time platform-wide.
# Deliberately a distinct lease from IDENTITY_REFRESH_LEASE_NAME -- Daily
# Identity Refresh's own SEC fetching is already serialized against itself
# via that lease, and coupling the two would block unrelated work for no
# reason. Phase 1 only (this constant plus the acquire/release commands
# below); the Step Functions wiring that actually acquires/releases it
# around each command's fetch phase is a separate follow-up ticket -- see
# release-readiness ticket 80's Progress notes.
SEC_FETCH_LEASE_NAME = "sec_fetch_active"

# release-readiness ticket 84: sized against real measured prod runtimes
# (daily-incremental ~7h7m, bootstrap ~4h10m) plus the worst documented
# related-pipeline run (13h20m, CLAUDE.md's pre-fix daily accession-expansion
# case), leaving ~2h40m margin -- deliberately shorter than
# IDENTITY_REFRESH_LEASE_NAME's 20h default, which was sized for a different
# process (the 18h Identity Backstop Sweep bound).
SEC_FETCH_LEASE_STALE_AFTER_SECONDS = 16 * 3600

# These four commands touch nothing but the pipeline_run_lease table (a
# handful of rows). Routing them through the normal hydrate/merge/publish
# path against the full canonical silver.duckdb (1.5GB+ as of 2026-08 and
# growing) downloads and re-uploads the entire monolith, plus a full
# protected-table merge scan across all 31 tables, just to flip one row --
# confirmed live to OOM a 4096MB task (task #35's first load_history
# attempt, 2026-08-09): hydration and the merge scan of every other table
# succeeded, and the kill landed during/after re-uploading the merged
# canonical file. _lease_command_context() repoints these commands at a
# separate, tiny silver.duckdb under a "leases" prefix instead -- same
# schema (SilverDatabase creates every table, just empty ones here), same
# acquire/release/get/mark SQL (edgar_warehouse/silver_store.py, unchanged),
# so the lease's atomicity and stale-reclaim semantics are identical; only
# the file being downloaded/merged/uploaded is now KB instead of GB.
LEASE_ONLY_COMMANDS = frozenset(
    {
        "acquire-sec-fetch-lease",
        "release-sec-fetch-lease",
        "acquire-identity-refresh-lease",
        "release-identity-refresh-lease",
    }
)


def _lease_command_context(context: WarehouseCommandContext) -> WarehouseCommandContext:
    """Repoint storage_root/silver_root at a small, lease-only silver.duckdb.

    Every other root (bronze_root, snowflake_export_root) is left untouched
    -- lease commands don't touch bronze or Snowflake export at all, and
    lease_result.json still needs to land in the normal bronze location the
    Step Functions Choice state reads it from.
    """
    import dataclasses

    return dataclasses.replace(
        context,
        storage_root=StorageLocation(f"{context.storage_root.root}/leases"),
        silver_root=StorageLocation(f"{context.silver_root.root}/leases"),
    )

# load_history's tracking-status contract (data-architecture Issue 2): compute-windows,
# bootstrap-next (via the explicit --tracking-status-filter the load_history state machine
# passes), and bootstrap-fundamentals's CIK resolution must all query the SAME combined status
# set. A CIK is 'bootstrap_pending' from seeding until its first full submissions bootstrap
# completes, then promoted to 'active' in sec_company_sync_state. Filtering
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
# Form 3/4/5 artifact + silver parse window. Historical deep Form 4 histories
# (often thousands of accessions per heavy-insider issuer) are not useful for
# IS_INSIDER / current insider identity; only the recent band matters. 0 =
# full history (operator repair / explicit override only).
DEFAULT_OWNERSHIP_LOOKBACK_YEARS = 2
# Item 5.02 8-K agent window matches Ticket 20 / agent-source lock (W−2y).
# Integrated with the ownership load: same default, same CLI/env ownership
# lookback knob unless WAREHOUSE_ITEM_502_LOOKBACK_YEARS is set explicitly.
DEFAULT_ITEM_502_LOOKBACK_YEARS = 2
# General filing-discovery window (10-K/10-Q/8-K/DEF 14A/13F/ADV/etc): unlike
# the two lookbacks above, this gates whether a filing row is written into
# sec_company_filing (bronze discovery) at all, not just whether its artifact
# gets parsed. 0 = disabled (full history) -- this is the pre-existing
# behavior for every caller that doesn't opt in, so bootstrap/daily-
# incremental/targeted-resync are unaffected unless --filing-lookback-years
# is passed explicitly.
DEFAULT_FILING_LOOKBACK_YEARS = 0

def _emit_pipeline_event(event: str, **payload: Any) -> None:
    """Emit a structured progress event for ECS/CloudWatch pipeline monitoring."""
    document = {
        "event": event,
        "emitted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        **payload,
    }
    print(json.dumps(document, sort_keys=True), file=sys.stderr, flush=True)


# Cap on how many `raw_writes` entries a command result prints to stdout.
# `raw_writes` carries one write receipt per document (path, sha256,
# raw_object_id, cik, cached) and can run into the thousands for a single
# bootstrap window. The full list is already durable elsewhere -- one row per
# run in `pipeline_run.raw_writes_json` (SilverDatabase.complete_pipeline_run)
# inside the published silver database, plus the underlying S3 objects
# themselves -- so printing it in full to stdout only duplicated data ECS was
# already routing to CloudWatch, and was the single largest contributor to
# production log volume (ops-cost-control ticket 01: 61.9M bytes, 71% of all
# records in one measured 14-hour window).
COMMAND_RESULT_RAW_WRITES_LOG_SAMPLE = 5


def _command_result_for_log(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a command result payload that is safe to print to stdout.

    Every other field in a command result payload is already bounded (a
    handful of layer manifest paths, per-table row counts) -- `raw_writes` is
    the one field whose size scales with documents processed, so it's the
    only one summarized here.
    """
    raw_writes = payload.get("raw_writes")
    if not isinstance(raw_writes, list) or len(raw_writes) <= COMMAND_RESULT_RAW_WRITES_LOG_SAMPLE:
        return payload
    summarized = dict(payload)
    summarized["raw_writes"] = raw_writes[:COMMAND_RESULT_RAW_WRITES_LOG_SAMPLE]
    summarized["raw_writes_total_count"] = len(raw_writes)
    summarized["raw_writes_sample_size"] = COMMAND_RESULT_RAW_WRITES_LOG_SAMPLE
    return summarized


def _print_command_result(payload: dict[str, Any]) -> None:
    """Print a command result payload, bounding its `raw_writes` field first."""
    print(json.dumps(_command_result_for_log(payload), indent=2, sort_keys=True))


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

    _print_command_result(payload)
    return 0


def run_seed_universe_command(args: Any) -> int:
    """Compatibility entry point for explicit MDM universe seeding."""
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
    publish_gold = _gold_publication_enabled(command_name, arguments)

    writes = []
    for layer, relative_path in _planned_writes_for_publication(
        command_name=command_name,
        command_path=command_path,
        run_id=run_id,
        scope=scope,
        include_gold=publish_gold,
    ).items():
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
    publish_snowflake = context.snowflake_export_root is not None and not (
        command_name == "bootstrap-next" and bool(arguments.get("silver_only"))
    )
    if publish_snowflake:
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

    writes.append(
        _write_consolidated_run_manifest(
            context=context,
            command_name=command_name,
            command_path=command_path,
            run_id=run_id,
            arguments=arguments,
            scope=scope,
            now=now,
            manifest_writes=list(writes),
        )
    )

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
        "message": _warehouse_success_message(publish_snowflake),
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
    if command_name in LEASE_ONLY_COMMANDS:
        context = _lease_command_context(context)

    landing_export = (
        LandingExportBuffer() if context.silver_landing_export_root is not None else None
    )

    now = datetime.now(UTC)
    run_id = _resolve_run_id(arguments)
    command_path = command_name.replace("_", "-")
    publish_gold = _gold_publication_enabled(command_name, arguments)
    publish_snowflake = _snowflake_publication_enabled(command_name, arguments)

    if command_name == "backfill-mdm-entity-ids":
        # mdm-ahead-of-silver map, Phase B: iterates every shard (or the
        # monolith) on its own -- doesn't fit the single-db-handle shape the
        # rest of this function assumes, so it's dispatched before the
        # shard/monolith hydration decision below rather than through it.
        # Caller MUST wrap this in the sec_fetch_active lease -- see
        # edgar_warehouse/mdm_entity_backfill.py's module docstring.
        from edgar_warehouse.mdm_entity_backfill import run_mdm_entity_backfill_sweep

        return run_mdm_entity_backfill_sweep(context, run_id)

    if command_name == "backfill-silver-landing-company-metadata":
        # duckdb-retirement map: one-time seed of sec_company/address/
        # former_name/submission_file into the landing zone -- see
        # edgar_warehouse/silver_landing_company_backfill.py's module
        # docstring. Reads every shard directly, same dispatch shape as
        # backfill-mdm-entity-ids above.
        from edgar_warehouse.silver_landing_company_backfill import (
            run_silver_landing_company_backfill,
        )

        return run_silver_landing_company_backfill(context, run_id)

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
                    db = open_silver_shard(local_shard_path, landing_export=landing_export)

    if not _using_shard_path:
        _hydrate_silver_database_from_storage(context)
        scope = _resolve_scope(command_name=command_name, arguments=arguments, now=now, silver_root=context.silver_root)
        db = _open_silver_database(context.silver_root, landing_export=landing_export)
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
    pipeline_writes = _planned_pipeline_writes(
        context=context,
        command_name=command_name,
        command_path=command_path,
        run_id=run_id,
        scope=scope,
        now=now,
        include_snowflake_export_manifest=(
            context.snowflake_export_root is not None and publish_snowflake
        ),
        include_gold_manifest=publish_gold,
        shard_index=_active_shard_index if _using_shard_path else None,
    )
    db.start_pipeline_run(
        {
            "pipeline_run_id": run_id,
            "command_name": command_name,
            "runtime_mode": context.runtime_mode,
            "environment_name": context.environment_name,
            "started_at": now,
            "status": "running",
            "arguments": arguments,
            "scope": scope,
            "bronze_root": context.bronze_root.root,
            "storage_root": context.storage_root.root,
            "silver_root": context.silver_root.root,
            "serving_export_root": (
                context.snowflake_export_root.root
                if context.snowflake_export_root is not None
                else None
            ),
        }
    )

    raw_writes: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {"rows_inserted": 0, "rows_skipped": 0, "sync_status": "succeeded"}
    gold_row_counts: dict[str, int] | None = None
    gold_manifest_entries: list[dict[str, Any]] | None = None
    snowflake_export_counts: dict[str, int] | None = None
    snowflake_export_manifest_write: dict[str, Any] | None = None
    silver_database_write: dict[str, Any] | None = None
    silver_table_counts: dict[str, int] | None = None
    landing_export_counts: dict[str, int] | None = None
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
        if context.snowflake_export_root is not None and publish_gold:
            from edgar_warehouse.serving.source_dimensional_export import (
                iter_source_export_tables,
                write_source_export_table_manifest_entry,
            )
            from edgar_warehouse.serving.targets.snowflake import write_gold_table_to_serving_export

            gold_started_at = datetime.now(UTC)
            _emit_pipeline_event(
                "gold_publish_started",
                command=command_name,
                run_id=run_id,
                silver_table_counts=silver_table_counts,
            )

            export_business_date = _resolve_export_business_date(command_name=command_name, scope=scope, now=now)

            # Stream one gold table at a time: build -> write to storage ->
            # export to Snowflake -> discard -> next. See iter_source_export_tables()
            # for why the previous all-at-once shape is unsafe.
            _emit_pipeline_event("gold_build_started", command=command_name, run_id=run_id)
            gold_manifest_entries = []
            gold_row_counts = {}
            snowflake_export_counts = {}
            table_count = 0
            for table_name, table in iter_source_export_tables(db):
                table_count += 1
                manifest_entry = write_source_export_table_manifest_entry(
                    table_name, table, context.storage_root, run_id
                )
                gold_manifest_entries.append(manifest_entry)
                gold_row_counts[manifest_entry["table_name"]] = int(manifest_entry["row_count"])
                # Recorded per table, not batched at the end of the loop: this is
                # an idempotent per-(run_id, storage_layer, table_name) upsert, so
                # a later table's export failure can't erase an earlier table's
                # already-durable manifest row the way a single end-of-loop call
                # would (that table's write already succeeded on disk).
                db.record_gold_manifest(
                    run_id=run_id,
                    command_name=command_name,
                    entries=[manifest_entry],
                )

                export_result = write_gold_table_to_serving_export(
                    table_name, table, context.snowflake_export_root, run_id, export_business_date
                )
                if export_result is not None:
                    export_name, export_row_count = export_result
                    snowflake_export_counts[export_name] = export_row_count

                del table

            # build/write/export are now fused per table (see loop above), so
            # there's no separate storage-write or Snowflake-export phase
            # left to time -- one combined duration covers all three, unlike
            # the old three-pass shape where each phase had its own timer.
            gold_build_duration = (datetime.now(UTC) - gold_started_at).total_seconds()
            _emit_pipeline_event(
                "gold_build_completed",
                command=command_name,
                run_id=run_id,
                duration_seconds=gold_build_duration,
                table_count=table_count,
                gold_row_counts=gold_row_counts,
                gold_manifest=gold_manifest_entries,
                snowflake_export_counts=snowflake_export_counts,
            )
            _emit_pipeline_event(
                "gold_publish_completed",
                command=command_name,
                duration_seconds=gold_build_duration,
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
        db.complete_pipeline_run(
            run_id,
            status=str(metrics.get("sync_status", "succeeded")),
            writes=pipeline_writes,
            raw_writes=raw_writes,
            metrics={
                **metrics,
                "silver_table_counts": silver_table_counts or {},
                "gold_row_counts": gold_row_counts or {},
                "gold_manifest": gold_manifest_entries or [],
                "snowflake_export_row_counts": snowflake_export_counts or {},
            },
        )
        db.close()
        db_closed = True
        _emit_pipeline_event(
            "silver_publish_started",
            command=command_name,
            run_id=run_id,
            storage_root=context.storage_root.root,
        )
        if command_name == "compute-identity-refresh-window":
            # This pre-stage is the sole owner of the global reference snapshot
            # for daily_incremental's bounded Identity Refresh. It deliberately
            # does not publish canonical silver: the reducer
            # (ReduceIdentityRefresh) will merge this immutable candidate with
            # all batch deltas exactly once.
            #
            # compute-windows (load_history) used to join this same branch
            # (Company Identity Hydrate Elimination map, ticket 03), but no
            # longer does: stage0-stage1-consolidation wayfinder map, ticket
            # 02/04 removed Stage0CompanyIdentity/ReduceIdentityRefresh from
            # load_history entirely, since Stage1's WindowedBootstrap already
            # writes the identical sec_company rows as a byproduct of its own
            # capture. compute-windows now falls through to the normal direct
            # publish below, so its once-per-run reference-data sync
            # (company_tickers/company_tickers_exchange) lands in canonical on
            # its own -- there is no reducer left to merge it otherwise.
            from edgar_warehouse.application.identity_refresh_publication import persist_run_manifest

            image_identity = os.environ.get("WAREHOUSE_IMAGE_REF", "").strip()
            snapshot = persist_run_manifest(
                context.storage_root,
                run_id=run_id,
                image_identity=image_identity,
                reference_snapshot_file=Path(context.silver_root.join("silver", "sec", "silver.duckdb")),
                batches=metrics.pop("_identity_refresh_batches"),
            )
            silver_database_write = {
                "layer": "identity_refresh_reference_snapshot",
                "path": context.storage_root.join(snapshot["reference_snapshot"]["path"]),
                "run_manifest_path": context.storage_root.join("identity_refresh/runs", run_id, "run_manifest.json"),
                "size_bytes": Path(context.silver_root.join("silver", "sec", "silver.duckdb")).stat().st_size,
            }
        elif _using_shard_path and _active_shard_index is not None:
            silver_database_write = _publish_shard_if_remote_with_retry(context, _active_shard_index)
        else:
            silver_database_write = _publish_silver_database_with_retry(context)
        _emit_pipeline_event(
            "silver_publish_completed",
            command=command_name,
            run_id=run_id,
            silver_database=silver_database_write,
        )
        if landing_export is not None:
            landing_export_counts = write_landing_export(
                landing_export,
                context.silver_landing_export_root,
                run_id=run_id,
                business_date=_resolve_export_business_date(command_name=command_name, scope=scope, now=now),
                command_name=command_name,
                environment_name=context.environment_name,
                now=now,
            )
            _emit_pipeline_event(
                "silver_landing_export_completed",
                command=command_name,
                run_id=run_id,
                table_counts=landing_export_counts,
            )
    except Exception as exc:
        if not db_closed:
            db.complete_sync_run(run_id, status="failed", error_message=str(exc))
            db.complete_pipeline_run(
                run_id,
                status="failed",
                writes=pipeline_writes,
                raw_writes=raw_writes,
                metrics=metrics,
                error_message=str(exc),
            )
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
    for layer, relative_path in _planned_writes_for_publication(
        command_name=command_name,
        command_path=command_path,
        run_id=run_id,
        scope=scope,
        include_gold=publish_gold,
    ).items():
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

    if context.snowflake_export_root is not None and publish_gold:
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
        from edgar_warehouse.serving.source_dimensional_export import build_ticker_reference_table
        from edgar_warehouse.serving.targets.snowflake import write_ticker_reference_to_serving_export

        export_business_date = _resolve_export_business_date(command_name=command_name, scope=scope, now=now)
        ticker_table = build_ticker_reference_table(ticker_reference_rows, run_id)
        ticker_row_count = write_ticker_reference_to_serving_export(
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

    writes.append(
        _write_consolidated_run_manifest(
            context=context,
            command_name=command_name,
            command_path=command_path,
            run_id=run_id,
            arguments=arguments,
            scope=scope,
            now=now,
            manifest_writes=list(writes),
            metrics=metrics,
            raw_writes=raw_writes,
            silver_table_counts=silver_table_counts,
            gold_row_counts=gold_row_counts,
            serving_export_counts=snowflake_export_counts,
        )
    )

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
            "silver_landing_export_root": (
                context.silver_landing_export_root.root if context.silver_landing_export_root else None
            ),
        },
        "message": (
            "Warehouse bronze capture completed successfully. "
            "Raw SEC files and run manifests were written to the configured bronze"
            + (
                ", warehouse, and Snowflake export roots."
                if snowflake_export_manifest_write is not None else
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
        "silver_landing_export_row_counts": landing_export_counts,
        "started_at": now.isoformat().replace("+00:00", "Z"),
        "status": "ok",
        "writes": writes,
        "cik_universe_path": metrics.get("cik_universe_path"),
        "cik_count": metrics.get("cik_count"),
    }


def _open_silver_database(
    silver_root: StorageLocation, *, landing_export: "LandingExportBuffer | None" = None
) -> SilverDatabase:
    return open_silver_database(silver_root, landing_export=landing_export)


def _protected_fingerprint_sidecar_path(local_path: Path) -> Path:
    """Local-only sidecar recording ``compute_silver_fingerprint``'s output at
    hydration time, so ``_publish_silver_database_if_remote`` can cheaply tell
    whether anything actually changed since (release-readiness ticket 79).
    """
    return local_path.with_name(local_path.name + ".protected-fingerprint.json")


def _write_fingerprint_sidecar(local_path: Path, fingerprint: dict[str, Any]) -> None:
    _protected_fingerprint_sidecar_path(local_path).write_text(
        json.dumps(fingerprint, sort_keys=True), encoding="utf-8"
    )


def _read_fingerprint_sidecar(local_path: Path) -> dict[str, Any] | None:
    sidecar_path = _protected_fingerprint_sidecar_path(local_path)
    try:
        return json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return None


def _hydrate_silver_database_from_storage(context: WarehouseCommandContext) -> None:
    if not context.storage_root.is_remote or context.silver_root.is_remote:
        return
    remote_path = context.storage_root.join("silver", "sec", "silver.duckdb")
    local_path = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))
    # Delete any stale sidecar from a prior invocation up front (e.g. a reused
    # ECS task volume) so "sidecar present" always means "this process
    # successfully hydrated", never leftover state from an earlier run.
    _protected_fingerprint_sidecar_path(local_path).unlink(missing_ok=True)
    try:
        context.storage_root.download_file("silver/sec/silver.duckdb", local_path)
    except (FileNotFoundError, OSError):
        return
    # Snapshot the hydration-time fingerprint before any caller opens the
    # database and runs schema DDL, so the sidecar reflects exactly what was
    # downloaded from canonical -- the baseline every later publish attempt
    # in this process compares itself against. Deliberately fail-open: a
    # fingerprint failure (e.g. not a valid DuckDB file) must never break
    # hydration itself -- worst case is just no sidecar, which is the same
    # safe "always do the real merge" default as remote canonical not
    # existing yet.
    try:
        fingerprint = compute_silver_fingerprint(local_path)
    except Exception:
        fingerprint = None
    if fingerprint is not None:
        _write_fingerprint_sidecar(local_path, fingerprint)
    _emit_pipeline_event(
        "silver_database_hydrated",
        path=remote_path,
        local_path=str(local_path),
        size_bytes=local_path.stat().st_size,
    )


def _publish_silver_database_if_remote(context: WarehouseCommandContext) -> dict[str, Any] | None:
    """Merge the local silver candidate into canonical and publish it, safely.

    Ordinary publication is monotonic and concurrency-safe (ARTF-01/ARTF-02):
    the candidate is merged into a fresh local copy of canonical (never
    overwriting it directly) via ``merge_candidate_into_canonical`` --
    unclassified tables, dropped/retyped columns, and ambiguous same-key
    conflicts all fail closed -- then the merged result is uploaded to an
    immutable staging key and promoted onto the canonical key only if
    canonical's version/ETag has not changed since it was read at the start
    of this call. A concurrent writer between those two points raises
    ``PromotionConflictError`` (retryable; the staged object is preserved)
    instead of silently last-writer-wins. There is no ``--force`` parameter
    on this path -- it cannot bypass the merge or the concurrency check.

    Skip-if-unchanged (release-readiness ticket 79): before any of the above,
    a cheap local-only check compares the candidate's current
    ``compute_silver_fingerprint`` against the one snapshotted right after
    hydration. If they're identical -- same table set, same protected-table
    content -- nothing this process wrote can differ from canonical, so the
    whole download/copy2/merge/upload/promote cycle is skipped: it would
    provably produce a no-op. Fingerprint comparison is local-only (no S3
    calls), so it costs nothing close to what it replaces. If the sidecar is
    missing (hydration didn't run, or wrote nothing) the check is skipped and
    behavior is unchanged -- absence never causes a skip, only presence of a
    provably-matching fingerprint does.
    """
    if not context.storage_root.is_remote:
        return None
    source_path = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))
    if not source_path.exists():
        raise WarehouseRuntimeError(f"Silver DuckDB file was not found: {source_path}")
    relative_path = "silver/sec/silver.duckdb"

    hydration_fingerprint = _read_fingerprint_sidecar(source_path)
    if hydration_fingerprint is not None:
        try:
            current_fingerprint = compute_silver_fingerprint(source_path)
        except Exception:
            # Fail-open, matching hydration's own handling: a fingerprint
            # failure here must never block publication -- fall through to
            # the full, always-correct merge path instead.
            current_fingerprint = None
        if current_fingerprint is not None and current_fingerprint == hydration_fingerprint:
            _emit_pipeline_event(
                "silver_publish_skipped_noop",
                relative_path=relative_path,
                protected_tables=sorted(current_fingerprint["protected"]) if current_fingerprint else [],
            )
            return {
                "layer": "silver_database",
                "path": context.storage_root.join(relative_path),
                "relative_path": relative_path,
                "size_bytes": source_path.stat().st_size,
                "source_version": None,
                "staged_checksum": None,
                "canonical_version": None,
                "tables_merged": [],
                "skipped": True,
            }

    baseline = context.storage_root.read_object_version(relative_path)
    tables_merged: tuple[str, ...] = ()

    if baseline.exists:
        with tempfile.TemporaryDirectory() as tmp_dir:
            canonical_local = Path(tmp_dir) / "canonical.duckdb"
            canonical_local.write_bytes(read_bytes(context.storage_root.join(relative_path)))
            merged_local = Path(tmp_dir) / "merged.duckdb"
            merge_result = merge_candidate_into_canonical(source_path, canonical_local, merged_local)
            tables_merged = merge_result.tables_merged
            payload = merged_local.read_bytes()
    else:
        payload = source_path.read_bytes()

    size_bytes = len(payload)
    promotion = context.storage_root.stage_and_promote(
        relative_path, payload, expected_etag=baseline.etag
    )
    return {
        "layer": "silver_database",
        "path": promotion.canonical_path,
        "relative_path": relative_path,
        "size_bytes": size_bytes,
        "source_version": baseline.etag,
        "staged_checksum": hashlib.md5(payload).hexdigest(),
        "canonical_version": promotion.new_version.etag,
        "tables_merged": list(tables_merged),
    }


def _publish_silver_database_with_retry(context: WarehouseCommandContext) -> dict[str, Any] | None:
    """Retry _publish_silver_database_if_remote on a lost promotion race.

    Regression (2026-07-22): Ticket 20's strict release runs concurrent
    Distributed Map batches (MaxConcurrency=4) that all merge into and
    publish the same canonical silver.duckdb. PromotionConflictError's own
    docstring says it is "retryable: the staged object is left in place ...
    so a caller can re-read canonical, re-merge, and retry promotion" -- but
    no caller ever did, so the first batch to publish always won and every
    other concurrently-finishing batch failed outright, aborting the whole
    0%-tolerance release even though its work (fetch + merge) was otherwise
    complete. The merge/publish cycle re-downloads canonical, re-merges the
    original local candidate, re-uploads, and re-attempts the ETag-guarded
    promote. A sequence of sibling writers may legitimately win more than five
    times, so the default policy has no attempt ceiling. Operators may set a
    positive ``WAREHOUSE_PUBLISH_CONFLICT_ATTEMPTS`` to impose one explicitly.
    """
    from edgar_warehouse.infrastructure.object_storage import PromotionConflictError

    configured_attempts = int(os.environ.get("WAREHOUSE_PUBLISH_CONFLICT_ATTEMPTS", "0"))
    max_attempts = configured_attempts if configured_attempts > 0 else None
    backoff_base_seconds = float(os.environ.get("WAREHOUSE_PUBLISH_CONFLICT_RETRY_BASE_SECONDS", "1.0"))
    backoff_max_seconds = float(os.environ.get("WAREHOUSE_PUBLISH_CONFLICT_RETRY_MAX_SECONDS", "30.0"))
    attempt = 0
    while True:
        attempt += 1
        try:
            return _publish_silver_database_if_remote(context)
        except PromotionConflictError as exc:
            if max_attempts is not None and attempt >= max_attempts:
                raise
            import random
            import time as _time

            exponential_delay = backoff_base_seconds * (2 ** min(attempt - 1, 20))
            delay = min(backoff_max_seconds, exponential_delay) * (0.5 + random.random() / 2)
            _emit_pipeline_event(
                "silver_publish_conflict_retry",
                attempt=attempt,
                max_attempts=max_attempts or "unbounded",
                retry_delay_seconds=delay,
                error=str(exc),
            )
            _time.sleep(delay)


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

    # Delete any stale sidecar from a prior invocation up front (e.g. a
    # reused ECS task volume), matching _hydrate_silver_database_from_storage's
    # own safeguard -- "sidecar present" must always mean "this process
    # successfully hydrated this shard", never leftover state.
    _protected_fingerprint_sidecar_path(local_path).unlink(missing_ok=True)

    try:
        context.storage_root.download_file(relative_path, local_path)
    except (FileNotFoundError, OSError):
        return None

    # Snapshot the hydration-time fingerprint (release-readiness ticket 79's
    # skip-if-unchanged optimization, ported here 2026-08-19): most
    # BatchSilver batches during a reprocessing pass write zero new rows
    # (already-captured bronze, nothing to add), and _publish_shard_if_remote
    # now merges via merge_candidate_into_canonical on every publish with an
    # existing baseline -- a real memory/network cost bootstrap-batch's
    # medium (4096MB) profile has been observed OOMing near even without
    # this addition (see this repo's own Stage 14 execution history), so
    # skipping the whole merge/publish cycle on a provable no-op matters
    # here, not just as a cost optimization. Fail-open on any fingerprint
    # error, matching the monolith path's own handling.
    try:
        fingerprint = compute_silver_fingerprint(local_path)
    except Exception:
        fingerprint = None
    if fingerprint is not None:
        _write_fingerprint_sidecar(local_path, fingerprint)

    _emit_pipeline_event(
        "silver_shard_hydrated",
        shard_index=shard_index,
        path=remote_path,
        local_path=str(local_path),
        size_bytes=local_path.stat().st_size,
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
    """Merge the local shard candidate into canonical and publish it, safely.

    ETag-guarded via the shared ``stage_and_promote`` primitive (decoupled-
    bronze-pipeline ticket 01/09's identified gap: this previously called
    ``upload_file`` directly -- a blind overwrite with no version check at
    all). A concurrent writer to the same shard between this call's baseline
    read and its promote raises ``PromotionConflictError``.

    Merges via ``merge_candidate_into_canonical`` (the same function
    ``_publish_silver_database_if_remote`` uses for the monolith) whenever a
    canonical version of this shard already exists, instead of blindly
    uploading the local file's raw bytes -- see this function's own
    ``_publish_shard_if_remote_with_retry`` wrapper for why a blind overwrite
    is unsafe here (multiple concurrent writers legitimately land on the same
    shard index). New shards (no canonical object yet) skip the merge and
    upload the local candidate directly, matching the monolith path's
    ``baseline.exists`` branch.

    Also ports the monolith's skip-if-unchanged optimization (release-
    readiness ticket 79): a fingerprint comparison against
    ``_hydrate_shard_for_window``'s hydration-time snapshot skips the entire
    S3/merge cycle for a provable no-op, before any remote call at all.

    Parameters
    ----------
    context:
        The warehouse command context.
    shard_index:
        The zero-based shard index to publish.

    Returns
    -------
    dict | None
        A write-record dict (``layer``, ``shard_index``, ``path``,
        ``size_bytes``, ``source_version``, ``canonical_version``,
        ``tables_merged``, and ``skipped: True`` on the no-op fast path) if
        published, or ``None`` if storage is local.

    Raises
    ------
    WarehouseRuntimeError
        If the local shard file does not exist.
    PromotionConflictError
        If the shard's canonical object changed since this call's baseline
        read. Retryable -- see ``_publish_shard_if_remote_with_retry``.
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

    # Skip-if-unchanged (ported from _publish_silver_database_if_remote,
    # release-readiness ticket 79): before any S3 call, compare the current
    # fingerprint against the one snapshotted at hydration time
    # (_hydrate_shard_for_window). If identical, nothing this process wrote
    # can differ from canonical, so the whole download-canonical/merge/
    # upload/promote cycle -- newly real memory pressure against
    # bootstrap-batch's medium (4096MB) profile once this shard's merge
    # branch exists at all, see this function's own module-level context --
    # is skipped as a provable no-op. Missing sidecar (new shard, or
    # hydration wrote nothing) never causes a skip, only a provably-matching
    # fingerprint does.
    hydration_fingerprint = _read_fingerprint_sidecar(local_path)
    if hydration_fingerprint is not None:
        try:
            current_fingerprint = compute_silver_fingerprint(local_path)
        except Exception:
            current_fingerprint = None
        if current_fingerprint is not None and current_fingerprint == hydration_fingerprint:
            _emit_pipeline_event(
                "silver_shard_publish_skipped_noop",
                shard_index=shard_index,
                relative_path=relative_path,
                protected_tables=sorted(current_fingerprint["protected"]),
            )
            return {
                "layer": "silver_shard",
                "shard_index": shard_index,
                "path": context.storage_root.join(relative_path),
                "relative_path": relative_path,
                "size_bytes": local_path.stat().st_size,
                "source_version": None,
                "staged_checksum": None,
                "canonical_version": None,
                "tables_merged": [],
                "skipped": True,
            }

    baseline = context.storage_root.read_object_version(relative_path)
    tables_merged: tuple[str, ...] = ()

    if baseline.exists:
        with tempfile.TemporaryDirectory() as tmp_dir:
            canonical_local = Path(tmp_dir) / "canonical.duckdb"
            canonical_local.write_bytes(read_bytes(context.storage_root.join(relative_path)))
            merged_local = Path(tmp_dir) / "merged.duckdb"
            merge_result = merge_candidate_into_canonical(local_path, canonical_local, merged_local)
            tables_merged = merge_result.tables_merged
            payload = merged_local.read_bytes()
    else:
        payload = local_path.read_bytes()

    promotion = context.storage_root.stage_and_promote(
        relative_path, payload, expected_etag=baseline.etag
    )
    return {
        "layer": "silver_shard",
        "shard_index": shard_index,
        "path": promotion.canonical_path,
        "relative_path": relative_path,
        "size_bytes": len(payload),
        "source_version": baseline.etag,
        "staged_checksum": hashlib.md5(payload).hexdigest(),
        "canonical_version": promotion.new_version.etag,
        "tables_merged": list(tables_merged),
    }


def _publish_shard_if_remote_with_retry(
    context: WarehouseCommandContext,
    shard_index: int,
) -> dict[str, Any] | None:
    """Retry _publish_shard_if_remote on a lost promotion race.

    Regression (silver-snowflake-migration map, 2026-08-19): the CIK-sharded
    architecture's shard count (4) is fixed independently of
    ``bronze_seed_silver_gold``'s ``BatchSilver`` Distributed Map
    concurrency (``MaxConcurrency: 20``), so multiple concurrent Map items
    routinely land on the same shard index -- contradicting this function's
    former docstring claim that "each shard is owned by exactly one writer."
    Three real prod executions hit the identical
    ``PromotionConflictError``-on-``shard-0.duckdb`` failure at this
    concurrency (see the silver-snowflake-migration map's "Motivating
    evidence" and Ticket 12's Progress notes); with
    ``ToleratedFailurePercentage: 0`` on that Map, a single unretried
    conflict aborts the entire release.

    Mirrors ``_publish_silver_database_with_retry``'s exact pattern (same
    env vars, same unbounded-by-default policy, same exponential backoff
    with jitter): on ``PromotionConflictError``, ``_publish_shard_if_remote``
    itself re-reads the current canonical baseline and re-merges the local
    candidate into it (see that function's ``merge_candidate_into_canonical``
    branch), so simply calling it again re-runs the full read-merge-stage-
    promote cycle against whatever the conflicting writer just published --
    no separate re-merge step is needed here.
    """
    from edgar_warehouse.infrastructure.object_storage import PromotionConflictError

    configured_attempts = int(os.environ.get("WAREHOUSE_PUBLISH_CONFLICT_ATTEMPTS", "0"))
    max_attempts = configured_attempts if configured_attempts > 0 else None
    backoff_base_seconds = float(os.environ.get("WAREHOUSE_PUBLISH_CONFLICT_RETRY_BASE_SECONDS", "1.0"))
    backoff_max_seconds = float(os.environ.get("WAREHOUSE_PUBLISH_CONFLICT_RETRY_MAX_SECONDS", "30.0"))
    attempt = 0
    while True:
        attempt += 1
        try:
            return _publish_shard_if_remote(context, shard_index)
        except PromotionConflictError as exc:
            if max_attempts is not None and attempt >= max_attempts:
                raise
            import random
            import time as _time

            exponential_delay = backoff_base_seconds * (2 ** min(attempt - 1, 20))
            delay = min(backoff_max_seconds, exponential_delay) * (0.5 + random.random() / 2)
            _emit_pipeline_event(
                "silver_shard_publish_conflict_retry",
                shard_index=shard_index,
                attempt=attempt,
                max_attempts=max_attempts or "unbounded",
                retry_delay_seconds=delay,
                error=str(exc),
            )
            _time.sleep(delay)


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
        form_15_ciks: list[int] = []
        recurring_lookback_days = int(
            arguments.get("recurring_index_lookback_days") or 0
        )
        if recurring_lookback_days < 0:
            raise WarehouseRuntimeError(
                "--recurring-index-lookback-days must be a non-negative integer"
            )
        business_date_start = date.fromisoformat(scope["business_date_start"])
        business_date_end = date.fromisoformat(scope["business_date_end"])
        if recurring_lookback_days:
            business_date_start = business_date_end - timedelta(
                days=recurring_lookback_days - 1
            )
        required_accessions: set[str] | None = (
            set() if recurring_lookback_days else None
        )
        required_candidate_rows: dict[str, dict[str, Any]] | None = (
            {} if recurring_lookback_days else None
        )
        for target_date in _date_range(
            start=business_date_start,
            end=business_date_end,
        ):
            result = _load_daily_index_for_date(
                context=context,
                db=db,
                target_date=target_date,
                sync_run_id=sync_run_id,
                now=now,
                force=(True if recurring_lookback_days else bool(arguments.get("force"))),
            )
            raw_writes.extend(result["raw_writes"])
            metrics["rows_inserted"] += result["rows_written"]
            metrics["rows_skipped"] += result["rows_skipped"]
            _merge_capture_network_metrics(metrics, result)
            impacted_ciks.extend(result["impacted_ciks"])
            form_15_ciks.extend(result.get("form_15_ciks", []))
            if required_accessions is not None:
                required_accessions.update(result.get("accession_numbers", []))
                if required_candidate_rows is None:
                    raise WarehouseRuntimeError(
                        "recurring daily-index candidate metadata was not initialized"
                    )
                for row in result.get("candidate_rows", []):
                    accession = str(row.get("accession_number") or "").strip()
                    if accession:
                        required_candidate_rows[accession] = dict(row)
            if result["status"] in {"waiting_for_publish", "failed_retryable"}:
                if recurring_lookback_days:
                    raise WarehouseRuntimeError(
                        "recurring daily-index window is incomplete: "
                        f"{target_date.isoformat()}={result['status']}"
                    )
                metrics["sync_status"] = "partial"
                break
        impacted_ciks = _dedupe_ints(impacted_ciks)
        _seed_silver_tracking_status(db, impacted_ciks, tracking_status="active")
        _demote_deregistered_ciks(db, form_15_ciks, now)
        impacted_ciks = _filter_ciks_to_universe(impacted_ciks, db=db)
        cik_limit = arguments.get("cik_limit")
        cik_offset = int(arguments.get("cik_offset") or 0)
        _validate_window_args(cik_limit, cik_offset)
        selected_ciks = impacted_ciks[cik_offset:]
        if cik_limit is not None:
            selected_ciks = selected_ciks[:cik_limit]
        selected_ciks = db.claim_discovery_ciks(
            selected_ciks,
            discovery_source="daily_incremental",
            run_id=sync_run_id,
            claimed_at=now,
        )
        # A previously claimed CIK can still have a newly forced-index accession.
        # Recurring artifact work therefore follows the exact accession union even
        # when no submissions-refresh claim is available for this run.
        if selected_ciks or recurring_lookback_days:
            try:
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
                    recurring_mode=bool(recurring_lookback_days),
                    required_accessions=required_accessions,
                    required_candidate_rows=required_candidate_rows,
                    ownership_lookback_years=arguments.get("ownership_lookback_years"),
                    item_502_lookback_years=arguments.get("item_502_lookback_years"),
                )
            except Exception:
                if selected_ciks:
                    db.finish_discovery_ciks(
                        selected_ciks,
                        discovery_source="daily_incremental",
                        run_id=sync_run_id,
                        status="failed",
                        finished_at=now,
                    )
                raise
            if selected_ciks:
                db.finish_discovery_ciks(
                    selected_ciks,
                    discovery_source="daily_incremental",
                    run_id=sync_run_id,
                    status="succeeded",
                    finished_at=now,
                )
            raw_writes.extend(result["raw_writes"])
            metrics["rows_inserted"] += result["rows_written"]
            metrics["rows_skipped"] += result["rows_skipped"]
            _merge_capture_network_metrics(metrics, result)
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
        _merge_capture_network_metrics(metrics, result)
        if result["status"] in {"waiting_for_publish", "failed_retryable"}:
            metrics["sync_status"] = "partial"
        return raw_writes, metrics

    if command_name == "bootstrap":
        ciks = _resolve_bootstrap_target_ciks(
            db=db,
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
            ownership_lookback_years=arguments.get("ownership_lookback_years"),
            item_502_lookback_years=arguments.get("item_502_lookback_years"),
        )
        raw_writes.extend(result["raw_writes"])
        metrics["rows_inserted"] += result["rows_written"]
        metrics["rows_skipped"] += result["rows_skipped"]
        _merge_capture_network_metrics(metrics, result)
        return raw_writes, metrics

    if command_name == "bootstrap-full":
        ciks = _resolve_bootstrap_target_ciks(
            db=db,
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
            ownership_lookback_years=arguments.get("ownership_lookback_years"),
            item_502_lookback_years=arguments.get("item_502_lookback_years"),
        )
        raw_writes.extend(result["raw_writes"])
        metrics["rows_inserted"] += result["rows_written"]
        metrics["rows_skipped"] += result["rows_skipped"]
        _merge_capture_network_metrics(metrics, result)
        return raw_writes, metrics

    if command_name == "bootstrap-next":
        pending_pool_limit = int(scope.get("cik_limit") or 100)
        tracking_status_filter = str(scope.get("tracking_status_filter", "bootstrap_pending"))
        ciks = _resolve_bootstrap_target_ciks(
            db=db,
            raw_ciks=None,
            command_name=command_name,
            tracking_status_filter=tracking_status_filter,
            cik_limit=arguments.get("cik_limit"),
            cik_offset=int(arguments.get("cik_offset") or 0),
        )
        ciks = ciks[:pending_pool_limit]
        ciks = db.claim_discovery_ciks(
            ciks,
            discovery_source="bootstrap_next",
            run_id=sync_run_id,
            claimed_at=now,
        )
        if ciks:
            try:
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
                    ownership_lookback_years=arguments.get("ownership_lookback_years"),
                    item_502_lookback_years=arguments.get("item_502_lookback_years"),
                    filing_lookback_years=arguments.get("filing_lookback_years"),
                )
            except Exception:
                db.finish_discovery_ciks(
                    ciks,
                    discovery_source="bootstrap_next",
                    run_id=sync_run_id,
                    status="failed",
                    finished_at=now,
                )
                raise
            db.finish_discovery_ciks(
                ciks,
                discovery_source="bootstrap_next",
                run_id=sync_run_id,
                status="succeeded",
                finished_at=now,
            )
            raw_writes.extend(result["raw_writes"])
            metrics["rows_inserted"] += result["rows_written"]
            metrics["rows_skipped"] += result["rows_skipped"]
        _merge_capture_network_metrics(metrics, result)
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
            _merge_capture_network_metrics(metrics, result)
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
                conflict_skipped_accessions: list[str] = []
                for acc_index, accession_number in enumerate(accessions, start=1):
                    _emit_pipeline_event(
                        "accession_resync_progress",
                        accession_number=accession_number,
                        index=acc_index,
                        total=total_accessions,
                        run_id=sync_run_id,
                    )
                    try:
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
                    except Exception as exc:
                        # release-readiness ticket 87: a single accession's
                        # immutable-object conflict (e.g. SEC-side byte drift
                        # on an already-captured document -- confirmed live,
                        # not a bug in this repo's byte-preserving capture
                        # path) must not abort the whole CIK resync. Isolate
                        # to this one accession and continue; any other
                        # exception type still fails the run as before.
                        if not _is_immutable_object_conflict(exc):
                            raise
                        conflict_skipped_accessions.append(accession_number)
                        _emit_pipeline_event(
                            "accession_resync_conflict_skipped",
                            accession_number=accession_number,
                            index=acc_index,
                            total=total_accessions,
                            error=repr(exc),
                            run_id=sync_run_id,
                        )
                        continue
                    raw_writes.extend(pipeline_result["raw_writes"])
                    metrics["rows_inserted"] += pipeline_result["rows_written"]
                metrics["accessions_conflict_skipped"] = len(conflict_skipped_accessions)
                _emit_pipeline_event(
                    "accession_resync_completed",
                    cik=_parse_cik(scope_key),
                    accession_count=total_accessions,
                    rows_written=metrics["rows_inserted"],
                    conflict_skipped_count=len(conflict_skipped_accessions),
                    conflict_skipped_accessions=conflict_skipped_accessions,
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
        _merge_capture_network_metrics(metrics, result)
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
        # Exclude companies already fully bootstrapped. MDM is the system of
        # record for company information (seed-universe-narrow-hydrate ticket
        # 05) -- its mdm_company.tracking_status mirrors silver's, kept
        # current by MdmSeedUniverse, and querying it (small, indexed
        # Postgres) needs no silver/duckdb hydrate at all, unlike the
        # previous db.get_active_ciks() silver read this replaced.
        active_ciks = set(_get_mdm_tracked_ciks("active"))
        if active_ciks:
            before = len(universe_rows)
            universe_rows = [row for row in universe_rows if int(row["cik"]) not in active_ciks]
            _emit_pipeline_event(
                "seed_universe_filtered",
                total_ciks=before,
                new_ciks=len(universe_rows),
                skipped_active=before - len(universe_rows),
                skipped_mdm_active=len(active_ciks),
            )
        if arguments.get("limit") is not None:
            universe_rows = universe_rows[: int(arguments["limit"])]
        _seed_silver_tracking_status(
            db,
            [int(row["cik"]) for row in universe_rows],
            tracking_status="bootstrap_pending",
        )
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
            ownership_lookback_years=arguments.get("ownership_lookback_years"),
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
            shard_aware=True,
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

    if command_name == "compute-remaining-batches":
        # pipeline-resumability ticket 02: automatic resume-batch filtering
        # for the default (non-release_mode) BatchSilver path, ahead of the
        # Map so already-done batches never launch a Fargate task just to
        # self-skip. Reuses the frozen original run's cik_batches.jsonl
        # (never regenerated -- the candidate set a resume may use) plus its
        # accumulated default_batch_done markers.
        from edgar_warehouse.application.batch_silver_resume import (
            compute_remaining_batches,
        )

        resume_ledger_run_id = str(arguments.get("resume_ledger_run_id") or "").strip()
        if not resume_ledger_run_id:
            raise WarehouseRuntimeError("compute-remaining-batches requires --resume-ledger-run-id")
        # Raises ResumeRunNotFoundError (a WarehouseRuntimeError) when the
        # pointer is bogus/missing/empty -- propagates out of run_command as
        # a nonzero exit, which is what makes this fail closed rather than
        # silently producing an empty Map indistinguishable from "all done."
        remaining, counts = compute_remaining_batches(
            bronze_root=context.bronze_root.root,
            resume_ledger_run_id=resume_ledger_run_id,
        )
        body = "".join(json.dumps(row, sort_keys=True) + "\n" for row in remaining)
        relative_path = default_path_resolver().cik_universe_batches_path(sync_run_id)
        cik_universe_path = context.bronze_root.write_text(relative_path, body)
        _emit_pipeline_event(
            "compute_remaining_batches_completed",
            resume_ledger_run_id=resume_ledger_run_id,
            run_id=sync_run_id,
            **counts,
        )
        metrics.update(counts)
        metrics["resume_ledger_run_id"] = resume_ledger_run_id
        metrics["cik_universe_path"] = cik_universe_path
        return raw_writes, metrics

    if command_name == "bootstrap-batch":
        cik_list = list(arguments.get("cik_list") or [])
        include_pagination = bool(arguments.get("include_pagination", True))
        release_mode = bool(arguments.get("release_mode", False))
        candidate_manifest_path = str(arguments.get("candidate_manifest") or "").strip()
        repair_manifest_path = str(arguments.get("repair_manifest") or "").strip()
        required_accessions: set[str] | None = None
        required_candidate_rows: dict[str, dict[str, Any]] | None = None
        repair_accessions: set[str] | None = None
        if release_mode:
            if not candidate_manifest_path:
                raise WarehouseRuntimeError(
                    "bootstrap-batch --release-mode requires --candidate-manifest"
                )
            from edgar_warehouse.application.relationship_bulk_load import (
                candidate_inventory_from_manifest,
                select_required_accessions,
            )

            prefilled_accession_outcomes: dict[str, Any] = {}
            freeze_prefix = ""
            try:
                candidate_payload = json.loads(
                    read_bytes(candidate_manifest_path).decode("utf-8")
                )
                candidate_inventory = candidate_inventory_from_manifest(
                    candidate_payload,
                    ciks={int(cik) for cik in cik_list},
                    require_strict_agent_windows=True,
                )
                required_candidates = [
                    candidate
                    for candidate in candidate_inventory.candidates
                    if candidate.artifact_required
                ]
                required_accessions = {
                    candidate.accession_number for candidate in required_candidates
                }
                required_candidate_rows = {
                    candidate.accession_number: {
                        "accession_number": candidate.accession_number,
                        "cik": candidate.cik,
                        "form": candidate.form,
                        "filing_date": candidate.filing_date,
                        "report_date": candidate.report_date,
                        "items": (
                            "5.02"
                            if candidate.candidate_reason == "item_5_02_metadata"
                            else None
                        ),
                    }
                    for candidate in required_candidates
                }
                if repair_manifest_path:
                    repair_payload = json.loads(
                        read_bytes(repair_manifest_path).decode("utf-8")
                    )
                    repair_accessions = select_required_accessions(
                        repair_payload, ciks={int(cik) for cik in cik_list}
                    )
                # P1: load durable per-accession terminals from prior runs of this freeze.
                from edgar_warehouse.application.relationship_bulk_load import (
                    load_terminal_accession_outcomes,
                    release_freeze_prefix_from_path,
                )

                freeze_prefix = release_freeze_prefix_from_path(candidate_manifest_path)
                prefilled_accession_outcomes = load_terminal_accession_outcomes(
                    freeze_prefix=freeze_prefix,
                    candidates=candidate_inventory.candidates,
                    inventory_fingerprint=candidate_inventory.fingerprint,
                    generation_id=sync_run_id,
                    read_text=lambda path: read_bytes(path).decode("utf-8"),
                )
                # Explicit --force repair must re-process named accessions even if
                # a prior terminal marker exists under this freeze.
                if repair_accessions:
                    for accession in repair_accessions:
                        prefilled_accession_outcomes.pop(accession, None)
                if prefilled_accession_outcomes:
                    # Do not re-fetch artifacts or re-parse when a valid freeze
                    # marker already proves a terminal outcome.
                    required_accessions = {
                        accession
                        for accession in required_accessions
                        if accession not in prefilled_accession_outcomes
                    }
                    _emit_pipeline_event(
                        "release_accession_resume_loaded",
                        resumed_count=len(prefilled_accession_outcomes),
                        pending_required_count=len(required_accessions),
                        freeze_prefix=freeze_prefix,
                        run_id=sync_run_id,
                    )
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                raise WarehouseRuntimeError(
                    f"bootstrap-batch could not read bounded release manifest: {exc}"
                ) from exc
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
            parser_policy=(
                "branch_b_deferred"
                if release_mode
                else str(arguments.get("parser_policy") or "configured_forms")
            ),
            release_mode=release_mode,
            required_accessions=required_accessions,
            required_candidate_rows=required_candidate_rows,
            repair_manifest_accessions=repair_accessions,
            ownership_lookback_years=arguments.get("ownership_lookback_years"),
            item_502_lookback_years=arguments.get("item_502_lookback_years"),
        )
        raw_writes.extend(result["raw_writes"])
        metrics["rows_inserted"] += result["rows_written"]
        metrics["rows_skipped"] += result["rows_skipped"]
        _merge_capture_network_metrics(metrics, result)
        if not release_mode:
            # pipeline-resumability ticket 02: default-path done marker, a
            # weaker-guarantee sibling of release_mode's own
            # release_batch_done_marker below. Written under
            # resume_ledger_run_id (defaults to this run's own sync_run_id
            # when unset) rather than sync_run_id itself, so a LATER,
            # separate execution can resume this exact run's ledger by
            # passing --resume-ledger-run-id <this run's id> without
            # colliding with sync_run_id's other uses (promotion, manifest
            # paths, leases) -- see ticket 02's "Resolve --run-id vs.
            # effective_run_id" note.
            from edgar_warehouse.application.batch_silver_resume import (
                write_default_batch_done_marker,
            )

            resume_ledger_run_id = (
                str(arguments.get("resume_ledger_run_id") or "").strip() or sync_run_id
            )
            marker_path = write_default_batch_done_marker(
                bronze_root=context.bronze_root.root,
                ciks=cik_list,
                resume_ledger_run_id=resume_ledger_run_id,
                completed_at=now.isoformat().replace("+00:00", "Z"),
            )
            metrics["default_batch_done_marker_path"] = marker_path
            metrics["resume_ledger_run_id"] = resume_ledger_run_id
        if release_mode:
            from edgar_warehouse.application.relationship_bulk_load import (
                CandidateOutcome,
                accession_done_marker_path,
                batch_done_marker_path,
                batch_identity_for_ciks,
                build_accession_done_marker,
                build_batch_done_marker,
                candidate_inventory_from_manifest,
                reconcile_completion_ledger,
                release_freeze_prefix_from_path,
            )
            from edgar_warehouse.infrastructure.object_storage import write_uri_text

            inventory = candidate_inventory_from_manifest(
                candidate_payload,
                ciks={int(cik) for cik in cik_list},
                require_strict_agent_windows=True,
            )
            pending_candidates = [
                candidate
                for candidate in inventory.candidates
                if candidate.accession_number not in prefilled_accession_outcomes
            ]
            parser_outcomes = _run_release_branch_b_parsers(
                db=db,
                ciks=[int(cik) for cik in cik_list],
                candidates=pending_candidates,
                sync_run_id=sync_run_id,
            )
            artifact_outcomes = {
                row["accession_number"]: row
                for row in result.get("candidate_outcomes", [])
            }
            outcomes: list[CandidateOutcome] = []
            newly_completed: list[CandidateOutcome] = []
            for candidate in inventory.candidates:
                resumed = prefilled_accession_outcomes.get(candidate.accession_number)
                if resumed is not None:
                    outcomes.append(resumed)
                    continue
                artifact = artifact_outcomes.get(candidate.accession_number)
                if candidate.artifact_required and artifact is None:
                    raise WarehouseRuntimeError(
                        f"missing terminal outcome for required candidate {candidate.accession_number}"
                    )
                parser_outcome = parser_outcomes.get(candidate.accession_number)
                if candidate.artifact_required and parser_outcome is None:
                    raise WarehouseRuntimeError(
                        f"missing parser outcome for required candidate {candidate.accession_number}"
                    )
                status = (
                    str(parser_outcome["status"])
                    if parser_outcome is not None
                    else "not_applicable"
                )
                evidence_fingerprint = (
                    hashlib.sha256(
                        "|".join((
                            str(artifact["evidence_fingerprint"]),
                            status,
                            str(parser_outcome.get("reason") or ""),
                        )).encode("utf-8")
                    ).hexdigest()
                    if artifact is not None and parser_outcome is not None
                    else candidate.fingerprint
                )
                outcome = CandidateOutcome(
                    generation_id=sync_run_id,
                    accession_number=candidate.accession_number,
                    candidate_fingerprint=candidate.fingerprint,
                    status=status,
                    evidence_fingerprint=evidence_fingerprint,
                )
                outcomes.append(outcome)
                newly_completed.append(outcome)
            reconciliation = reconcile_completion_ledger(
                inventory, outcomes, generation_id=sync_run_id
            )
            batch_identity = batch_identity_for_ciks(cik_list)
            ledger_path = context.storage_root.write_json(
                f"release-evidence/{sync_run_id}/bulk-load-ledger-batches/{batch_identity}.json",
                {
                    "generation_id": reconciliation.generation_id,
                    "inventory_fingerprint": reconciliation.inventory_fingerprint,
                    "terminal_counts": reconciliation.terminal_counts,
                    "fingerprint": reconciliation.fingerprint,
                    "outcomes": [outcome.__dict__ for outcome in outcomes],
                },
            )
            metrics["bulk_load_ledger_path"] = ledger_path
            metrics["bulk_load_ledger_fingerprint"] = reconciliation.fingerprint
            metrics["release_accession_resumed_count"] = len(prefilled_accession_outcomes)
            metrics["release_accession_newly_completed_count"] = len(newly_completed)
            # P0: durable done marker under the freeze prefix so a later SF
            # execution can feed only remaining batches (same freeze, new run_id).
            freeze_prefix = freeze_prefix or release_freeze_prefix_from_path(
                candidate_manifest_path
            )
            completed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            # P1: persist per-accession terminals for mid-batch resume next run.
            for outcome in newly_completed:
                marker_path = accession_done_marker_path(
                    freeze_prefix, outcome.accession_number
                )
                write_uri_text(
                    marker_path,
                    json.dumps(
                        build_accession_done_marker(
                            accession_number=outcome.accession_number,
                            candidate_fingerprint=outcome.candidate_fingerprint,
                            inventory_fingerprint=reconciliation.inventory_fingerprint,
                            status=outcome.status,
                            evidence_fingerprint=outcome.evidence_fingerprint,
                            generation_id=sync_run_id,
                            completed_at=completed_at,
                        ),
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                )
            marker_path = batch_done_marker_path(freeze_prefix, batch_identity)
            marker_payload = build_batch_done_marker(
                batch_identity=batch_identity,
                ciks=cik_list,
                generation_id=sync_run_id,
                inventory_fingerprint=reconciliation.inventory_fingerprint,
                ledger_path=ledger_path,
                ledger_fingerprint=reconciliation.fingerprint,
                terminal_counts=reconciliation.terminal_counts,
                candidate_count=len(inventory.candidates),
                completed_at=completed_at,
            )
            write_uri_text(
                marker_path,
                json.dumps(marker_payload, indent=2, sort_keys=True) + "\n",
            )
            metrics["release_batch_done_marker_path"] = marker_path
            metrics["release_batch_identity"] = batch_identity
            _emit_pipeline_event(
                "release_batch_done_marker_written",
                batch_identity=batch_identity,
                marker_path=marker_path,
                ledger_path=ledger_path,
                candidate_count=len(inventory.candidates),
                resumed_count=len(prefilled_accession_outcomes),
                newly_completed_count=len(newly_completed),
                run_id=sync_run_id,
            )
        return raw_writes, metrics

    if command_name == "ingest-relationship-sources":
        manifest_path = str(arguments.get("source_manifest") or "").strip()
        if not manifest_path:
            raise WarehouseRuntimeError("--source-manifest is required")
        try:
            manifest = json.loads(read_bytes(manifest_path).decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise WarehouseRuntimeError(f"could not read relationship source manifest: {exc}") from exc
        sources = manifest.get("sources") if isinstance(manifest, dict) else None
        if not isinstance(sources, list):
            raise WarehouseRuntimeError("relationship source manifest requires a sources list")
        # An empty sources list is a valid no-op, not an error -- fetch-adv-bulk
        # (and any other manifest producer) legitimately has nothing new on most
        # runs (e.g. daily_incremental's cheap check finding nothing to fetch).
        # Only a malformed manifest (missing/non-list "sources") fails closed.
        rows_written = 0
        for source in sources:
            if not isinstance(source, dict):
                raise WarehouseRuntimeError("relationship source manifest rows must be objects")
            kind = str(source.get("kind") or "")
            storage_path = str(source.get("storage_path") or "")
            expected_sha = str(source.get("sha256") or "").lower()
            if not storage_path or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
                raise WarehouseRuntimeError(f"{kind or 'source'} requires storage_path and SHA-256")
            payload = read_bytes(storage_path)
            actual_sha = hashlib.sha256(payload).hexdigest()
            if actual_sha != expected_sha:
                raise WarehouseRuntimeError(
                    f"relationship source hash mismatch for {storage_path}: {actual_sha}"
                )
            if kind == "iapd_adv_bulk":
                from edgar_warehouse.application.adv_bulk_ingest import ingest_adv_bulk_archive
                counts = ingest_adv_bulk_archive(
                    db, payload, dataset_period=str(source.get("dataset_period") or ""),
                    source_sha256=actual_sha, sync_run_id=sync_run_id,
                )
                rows_written += sum(counts.values())
            elif kind == "iapd_firm_roster":
                from edgar_warehouse.application.adv_firm_roster_ingest import (
                    ingest_firm_roster_archive,
                )
                counts = ingest_firm_roster_archive(
                    db, payload, dataset_period=str(source.get("dataset_period") or ""),
                    source_sha256=actual_sha, sync_run_id=sync_run_id,
                )
                rows_written += sum(counts.values())
            elif kind == "sec_subsidiary_exhibit":
                from edgar_warehouse.application.subsidiary_exhibits import (
                    ingest_subsidiary_parse_result, parse_subsidiary_exhibit,
                )
                parsed = parse_subsidiary_exhibit(
                    accession_number=str(source.get("accession_number") or ""),
                    registrant_cik=int(source.get("registrant_cik") or 0),
                    document_name=str(source.get("document_name") or ""),
                    document_type=str(source.get("document_type") or ""), content=payload,
                    report_date=date.fromisoformat(str(source.get("report_date") or "")),
                    source_sha256=actual_sha,
                )
                if parsed.outcome == "unresolved":
                    raise WarehouseRuntimeError(
                        f"unresolved subsidiary artifact {storage_path}: {parsed.reason}"
                    )
                rows_written += ingest_subsidiary_parse_result(db, parsed, sync_run_id=sync_run_id)
            elif kind == "sec_auditor_filing":
                from edgar_warehouse.application.auditor_evidence import (
                    ingest_auditor_parse_result, parse_auditor_evidence,
                )
                parsed = parse_auditor_evidence(
                    accession_number=str(source.get("accession_number") or ""),
                    registrant_cik=int(source.get("registrant_cik") or 0),
                    form_type=str(source.get("form_type") or ""),
                    document_name=str(source.get("document_name") or ""), content=payload,
                    audited_period_end=date.fromisoformat(
                        str(source.get("audited_period_end") or "")
                    ),
                    filing_date=date.fromisoformat(str(source.get("filing_date") or "")),
                    source_sha256=actual_sha,
                )
                if parsed.outcome != "applicable_loaded":
                    raise WarehouseRuntimeError(
                        f"unresolved auditor artifact {storage_path}: {parsed.reason}"
                    )
                rows_written += ingest_auditor_parse_result(db, parsed, sync_run_id=sync_run_id)
            elif kind == "pcaob_firm_registry":
                from edgar_warehouse.application.auditor_evidence import parse_pcaob_firm_registry
                identities = parse_pcaob_firm_registry(
                    payload, snapshot_uri=str(source.get("source_uri") or storage_path),
                    snapshot_sha256=actual_sha,
                )
                if not identities:
                    raise WarehouseRuntimeError("PCAOB firm registry is empty")
                from dataclasses import asdict
                rows_written += db.merge_pcaob_firm_identities(
                    [asdict(identity) for identity in identities], sync_run_id
                )
            else:
                raise WarehouseRuntimeError(f"unsupported relationship source kind: {kind!r}")
        metrics["rows_inserted"] += rows_written
        metrics["relationship_source_count"] = len(sources)
        return raw_writes, metrics

    if command_name == "fetch-adv-bulk":
        from edgar_warehouse.application.adv_bulk_fetch import (
            build_source_manifest,
            fetch_adv_bulk_sources,
            fetch_archive_bytes,
            fetch_reports_metadata_bytes,
        )

        forced_period = str(arguments.get("dataset_period") or "").strip() or None
        force = bool(arguments.get("force"))
        if force and forced_period is None:
            raise WarehouseRuntimeError("--force requires --dataset-period")

        # sec_adv_filing has no source_dataset_period column (a pre-existing
        # gap: ingest_adv_bulk_archive's filing_rows never carries it, unlike
        # fund_rows -- see the adv-pipeline map ticket 06 for the flagged
        # follow-up). Querying sec_adv_private_fund instead is safe in the
        # direction that matters: a period where every filer happened to
        # report zero private funds would read as "not yet ingested" and get
        # harmlessly re-fetched/re-ingested (merge is idempotent) -- never a
        # silent skip of real work.
        already_ingested = {
            str(row["source_dataset_period"])
            for row in db.fetch(
                "SELECT DISTINCT source_dataset_period FROM sec_adv_private_fund "
                "WHERE source_dataset_period IS NOT NULL"
            )
        }

        def _fetch_metadata() -> bytes:
            return fetch_reports_metadata_bytes(context.identity)

        def _fetch_archive(year: str, file_name: str) -> bytes:
            return fetch_archive_bytes(context.identity, year, file_name)

        def _upload(file_name: str, content: bytes) -> str:
            relative = f"runs/{command_name}/{sync_run_id}/{file_name}"
            return context.bronze_root.write_bytes(relative, content)

        sources, not_yet_published = fetch_adv_bulk_sources(
            already_ingested=already_ingested,
            as_of=now.date(),
            forced_period=forced_period,
            force=force,
            fetch_metadata=_fetch_metadata,
            fetch_archive=_fetch_archive,
            upload=_upload,
        )

        manifest = build_source_manifest(sources)
        # A distinct filename from the generic run-audit manifest.json the
        # planned_manifest_paths framework writes to the same run-id-derived
        # directory -- sharing the name causes a silent overwrite (caught by
        # tests/application/test_fetch_adv_bulk_command.py).
        manifest_relative = f"runs/{command_name}/{sync_run_id}/source_manifest.json"
        manifest_path = context.bronze_root.write_json(manifest_relative, manifest)
        raw_writes.append({"layer": "bronze", "path": manifest_path, "relative_path": manifest_relative})

        metrics["adv_bulk_fetch_sources_found"] = len(sources)
        metrics["adv_bulk_fetch_not_yet_published"] = not_yet_published
        metrics["adv_bulk_fetch_manifest_path"] = manifest_path
        return raw_writes, metrics

    if command_name == "fetch-firm-roster":
        from edgar_warehouse.application.firm_roster_fetch import (
            build_source_manifest,
            fetch_archive_bytes,
            fetch_firm_roster_sources,
            fetch_listing_bytes,
        )

        forced_period = str(arguments.get("dataset_period") or "").strip() or None
        force = bool(arguments.get("force"))
        if force and forced_period is None:
            raise WarehouseRuntimeError("--force requires --dataset-period")

        # Unlike sec_adv_private_fund (which has no dataset_period column, only
        # source_dataset_period -- see the fetch-adv-bulk block above),
        # sec_adv_firm_roster's dataset_period is its own real business-key
        # column (ticket 01), so this reads it directly.
        already_ingested = {
            str(row["dataset_period"])
            for row in db.fetch(
                "SELECT DISTINCT dataset_period FROM sec_adv_firm_roster "
                "WHERE dataset_period IS NOT NULL"
            )
        }

        def _fetch_listing() -> bytes:
            return fetch_listing_bytes(context.identity)

        def _fetch_archive(href: str) -> bytes:
            return fetch_archive_bytes(context.identity, href)

        def _upload(file_name: str, content: bytes) -> str:
            relative = f"runs/{command_name}/{sync_run_id}/{file_name}"
            return context.bronze_root.write_bytes(relative, content)

        sources, latest_period = fetch_firm_roster_sources(
            already_ingested=already_ingested,
            forced_period=forced_period,
            force=force,
            fetch_listing=_fetch_listing,
            fetch_archive=_fetch_archive,
            upload=_upload,
        )

        manifest = build_source_manifest(sources)
        # A distinct filename from the generic run-audit manifest.json, matching
        # fetch-adv-bulk's own reasoning above.
        manifest_relative = f"runs/{command_name}/{sync_run_id}/source_manifest.json"
        manifest_path = context.bronze_root.write_json(manifest_relative, manifest)
        raw_writes.append({"layer": "bronze", "path": manifest_path, "relative_path": manifest_relative})

        metrics["firm_roster_fetch_sources_found"] = len(sources)
        metrics["firm_roster_fetch_latest_period"] = latest_period
        metrics["firm_roster_fetch_manifest_path"] = manifest_path
        return raw_writes, metrics

    if command_name == "reconcile-relationship-release":
        manifest_path = str(arguments.get("candidate_manifest") or "").strip()
        if not manifest_path:
            raise WarehouseRuntimeError("--candidate-manifest is required")
        try:
            candidate_payload = json.loads(read_bytes(manifest_path).decode("utf-8"))
            from edgar_warehouse.application.relationship_bulk_load import (
                batch_identity_from_done_marker_name,
                build_required_relationship_bulk_load_evidence,
                candidate_inventory_from_manifest,
                reconcile_completion_ledger_batches,
                release_freeze_prefix_from_path,
                validate_and_rebind_done_batch_ledger,
            )
            from edgar_warehouse.infrastructure.object_storage import (
                list_uri_child_names,
            )

            inventory = candidate_inventory_from_manifest(
                candidate_payload, require_strict_agent_windows=True
            )
            ledger_paths = context.storage_root.find_existing(
                f"release-evidence/{sync_run_id}/bulk-load-ledger-batches/*.json"
            )
            batch_ledgers_by_identity = {
                str(path).rsplit("/", 1)[-1].removesuffix(".json"):
                    json.loads(read_bytes(path).decode("utf-8"))
                for path in ledger_paths
            }

            # P0 resume runs only unfinished batches under a fresh execution
            # name. Fan in prior ledgers exclusively through same-freeze done
            # markers, validating all marker/ledger bindings before rebinding
            # copied outcomes to this execution's evidence generation. A
            # current-run ledger wins if an operator deliberately reran a
            # previously completed batch.
            freeze_prefix = release_freeze_prefix_from_path(manifest_path)
            done_prefix = f"{freeze_prefix}batch_done/"
            for marker_name in list_uri_child_names(done_prefix):
                batch_identity = batch_identity_from_done_marker_name(marker_name)
                if batch_identity is None or batch_identity in batch_ledgers_by_identity:
                    continue
                marker = json.loads(
                    read_bytes(f"{done_prefix}{marker_name}").decode("utf-8")
                )
                if str(marker.get("batch_identity") or "") != batch_identity:
                    raise WarehouseRuntimeError(
                        f"batch done marker identity mismatch: {marker_name}"
                    )
                prior_ledger_path = str(marker.get("ledger_path") or "").strip()
                if not prior_ledger_path:
                    raise WarehouseRuntimeError(
                        f"batch done marker has no ledger path: {marker_name}"
                    )
                prior_ledger = json.loads(
                    read_bytes(prior_ledger_path).decode("utf-8")
                )
                batch_ledgers_by_identity[batch_identity] = (
                    validate_and_rebind_done_batch_ledger(
                        marker,
                        prior_ledger,
                        inventory_fingerprint=inventory.fingerprint,
                        generation_id=sync_run_id,
                    )
                )
            if not batch_ledgers_by_identity:
                raise WarehouseRuntimeError("no distributed bulk-load batch ledgers found")
            batch_ledgers = list(batch_ledgers_by_identity.values())
            reconciliation = reconcile_completion_ledger_batches(
                inventory, batch_ledgers, generation_id=sync_run_id
            )
            from edgar_warehouse.application.relationship_bulk_load import (
                parse_attestations_json,
            )

            attestations_raw = arguments.get("attestations")
            if attestations_raw is None:
                attestations_raw = arguments.get("attestations_json")
            # Enumerate the Release-Owner-accepted Item 5.02 unresolved
            # candidates from the batch ledgers so evidence names every one
            # (and the builder enforces the bounded rate fail-closed).
            accepted_unresolved = sorted({
                str(row.get("accession_number") or "")
                for ledger in batch_ledgers
                for row in (ledger.get("outcomes") or [])
                if isinstance(row, dict)
                and str(row.get("status") or "") == "unresolved_accepted"
            } - {""})
            item502_candidate_count = sum(
                1 for c in inventory.candidates if c.form in ("8-K", "8-K/A")
            )
            # Ticket 21: optional insider-coverage artifact (produced by
            # `mdm verify-insider-coverage --output ...`). When supplied,
            # the evidence builder fail-closes on any unresolved insider.
            insider_coverage_path = str(
                arguments.get("insider_coverage") or ""
            ).strip()
            insider_coverage = (
                json.loads(read_bytes(insider_coverage_path).decode("utf-8"))
                if insider_coverage_path
                else None
            )
            evidence = build_required_relationship_bulk_load_evidence(
                generation_id=sync_run_id,
                inventory_fingerprint=reconciliation.inventory_fingerprint,
                watermark=inventory.watermark,
                coverage_start=inventory.coverage_start,
                coverage_by_document_type=inventory.coverage_by_document_type,
                candidate_count=len(inventory.candidates),
                terminal_counts=reconciliation.terminal_counts,
                ledger_fingerprint=reconciliation.fingerprint,
                batch_ledger_count=len(batch_ledgers),
                attestations=parse_attestations_json(attestations_raw),
                image_digest=str(arguments.get("image_digest") or "").strip() or None,
                execution_arn=str(arguments.get("execution_arn") or "").strip() or None,
                accepted_unresolved_accessions=accepted_unresolved,
                item502_candidate_count=item502_candidate_count,
                insider_coverage=insider_coverage,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            if isinstance(exc, WarehouseRuntimeError):
                raise
            raise WarehouseRuntimeError(f"relationship release reconciliation failed: {exc}") from exc
        output_path = context.storage_root.write_json(
            f"release-evidence/{sync_run_id}/bulk-load-completion-ledger.json",
            {
                "generation_id": reconciliation.generation_id,
                "inventory_fingerprint": reconciliation.inventory_fingerprint,
                "candidate_count": len(inventory.candidates),
                "batch_ledger_count": len(batch_ledgers),
                "terminal_counts": reconciliation.terminal_counts,
                "fingerprint": reconciliation.fingerprint,
                "coverage_by_document_type": inventory.coverage_by_document_type,
                "watermark": inventory.watermark.isoformat(),
                "status": "pass",
            },
        )
        evidence_path = context.storage_root.write_json(
            f"release-evidence/{sync_run_id}/required_relationship_bulk_load_evidence.json",
            evidence,
        )
        metrics["bulk_load_completion_ledger_path"] = output_path
        metrics["bulk_load_completion_ledger_fingerprint"] = reconciliation.fingerprint
        metrics["required_relationship_bulk_load_evidence_path"] = evidence_path
        metrics["required_relationship_bulk_load_evidence_fingerprint"] = evidence[
            "evidence_fingerprint"
        ]
        metrics["ticket20_pass_claim"] = evidence["pass_claim"]
        return raw_writes, metrics

    if command_name == "gold-refresh":
        # Bronze and silver are already complete. _execute_warehouse (the caller)
        # will build gold tables and write Snowflake export manifests because
        # gold-refresh is in SOURCE_EXPORT_COMMANDS. Nothing to do here.
        _emit_pipeline_event("gold_refresh_started", run_id=sync_run_id)
        return raw_writes, metrics

    if command_name == "compute-windows":
        window_size = int(arguments.get("window_size") or 500)
        if window_size <= 0:
            raise WarehouseRuntimeError(
                f"--window-size must be a positive integer, got {window_size}"
            )
        total_cik_limit_raw = arguments.get("total_cik_limit")
        total_cik_limit = int(total_cik_limit_raw) if total_cik_limit_raw not in (None, "", 0, "0") else None
        if total_cik_limit is not None and total_cik_limit <= 0:
            raise WarehouseRuntimeError(
                f"--total-cik-limit must be a positive integer, got {total_cik_limit}"
            )
        ciks = db.get_tracked_ciks(LOAD_HISTORY_TRACKING_STATUS_FILTER)
        if total_cik_limit is not None:
            # Bound the CIK universe BEFORE window slicing so every downstream stage
            # (WindowedBootstrap, FetchEntityFacts/FetchPerFilingFundamentals/
            # FetchThirteenFHoldings) — which independently re-query the same
            # ordered tracked-CIK list by offset/limit against cik_windows.jsonl's
            # window descriptors — only ever sees windows within the capped set.
            # This scopes a whole load_history run to ~N companies (e.g. an
            # investigative sample) without mutating shared MDM tracking_status.
            ciks = ciks[:total_cik_limit]
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

        # Company Identity Hydrate Elimination map, ticket 03: sync reference
        # data (company_tickers/company_tickers_exchange) exactly once here
        # rather than once per bootstrap window -- this run's single
        # canonical source for that data, mirroring compute-identity-refresh-
        # window's own single upstream sync. stage0-stage1-consolidation
        # wayfinder map, ticket 02/04: these rows now publish straight to
        # canonical (see the removed compute-windows entry from the
        # identity-refresh publish special-case below) instead of via a
        # reducer -- Stage0CompanyIdentity/ReduceIdentityRefresh, the only
        # thing that used to merge this sync into canonical, no longer exist.
        reference_result = _sync_reference_data(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            fetch_date=now.date(),
        )
        raw_writes.extend(reference_result["raw_writes"])
        metrics["rows_inserted"] += reference_result["rows_written"]
        metrics["rows_skipped"] += reference_result["rows_skipped"]

        _emit_pipeline_event(
            "compute_windows_completed",
            run_id=sync_run_id,
            cik_count=len(ciks),
            window_count=len(window_descs),
            window_size=window_size,
            total_cik_limit=total_cik_limit,
            reference_rows_written=reference_result["rows_written"],
        )
        metrics["cik_count"] = len(ciks)
        metrics["window_count"] = len(window_descs)
        return raw_writes, metrics

    if command_name == "compute-identity-refresh-window":
        # Shared pre-stage for both scheduled identity modes. Daily mode
        # force-rechecks the trailing indexes; backstop mode skips filing
        # discovery and selects the complete company-eligible universe.
        refresh_started_at = datetime.now(UTC)
        refresh_mode = str(scope.get("mode") or "daily").strip()
        if refresh_mode not in {"daily", "backstop"}:
            raise WarehouseRuntimeError(
                "compute-identity-refresh-window requires --mode of "
                f"'daily' or 'backstop', got {refresh_mode!r}"
            )
        lookback_days = int(scope["lookback_days"])
        batch_size = int(scope["batch_size"])
        end_date = now.date()
        start_date = end_date - timedelta(days=lookback_days - 1)
        impacted_ciks: list[int] = []
        if refresh_mode == "daily":
            for target_date in _date_range(start=start_date, end=end_date):
                result = _load_daily_index_for_date(
                    context=context,
                    db=db,
                    target_date=target_date,
                    sync_run_id=sync_run_id,
                    now=now,
                    force=True,
                )
                raw_writes.extend(result["raw_writes"])
                metrics["rows_inserted"] += result["rows_written"]
                metrics["rows_skipped"] += result["rows_skipped"]
                _merge_capture_network_metrics(metrics, result)
                impacted_ciks.extend(result["impacted_ciks"])
            impacted_ciks = _dedupe_ints(impacted_ciks)
        reference_result = _sync_reference_data(
            context=context,
            db=db,
            sync_run_id=sync_run_id,
            fetch_date=now.date(),
        )
        raw_writes.extend(reference_result["raw_writes"])
        metrics["rows_inserted"] += reference_result["rows_written"]
        metrics["rows_skipped"] += reference_result["rows_skipped"]
        tracked_active_ciks = db.get_tracked_ciks("active")
        company_eligible_ciks = db.get_company_identity_ciks("active")
        if refresh_mode == "backstop":
            input_cik_count = len(tracked_active_ciks)
            selected_ciks = company_eligible_ciks
        else:
            input_cik_count = len(impacted_ciks)
            company_eligible_set = set(company_eligible_ciks)
            selected_ciks = sorted(
                cik for cik in impacted_ciks if cik in company_eligible_set
            )
        excluded_cik_count = input_cik_count - len(selected_ciks)
        cik_digest = _cik_set_digest(selected_ciks)
        batches_path = _write_cik_universe_batches(
            context=context,
            rows=[{"cik": cik} for cik in selected_ciks],
            fetch_date=now.date(),
            sync_run_id=sync_run_id,
            batch_size=batch_size,
        )
        duration_seconds = (
            datetime.now(UTC) - refresh_started_at
        ).total_seconds()
        selection_evidence = {
            "refresh_mode": refresh_mode,
            "cik_count": len(selected_ciks),
            "lookback_days": lookback_days,
            "batch_size": batch_size,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "input_cik_count": input_cik_count,
            "tracked_active_cik_count": len(tracked_active_ciks),
            "company_eligible_universe_cik_count": len(company_eligible_ciks),
            "excluded_cik_count": excluded_cik_count,
            "selected_cik_digest": cik_digest,
            "reference_snapshot_identity": reference_result.get(
                "reference_snapshot_identity"
            ),
            "prestage_duration_seconds": duration_seconds,
        }
        selection_evidence["_identity_refresh_batches"] = [
            selected_ciks[index : index + batch_size]
            for index in range(0, len(selected_ciks), batch_size)
        ]
        _emit_pipeline_event(
            "compute_identity_refresh_window_completed",
            run_id=sync_run_id,
            **selection_evidence,
        )
        metrics.update(selection_evidence)
        metrics["cik_universe_path"] = batches_path
        return raw_writes, metrics

    if command_name == "acquire-identity-refresh-lease":
        # Run-level lease shared by the Daily Identity Refresh and the Identity
        # Backstop Sweep (release-readiness ticket 45/49) so only one of the
        # two ever runs at a time. ecs:runTask.sync doesn't surface this
        # command's app-level stdout/metrics to a Step Functions Choice state,
        # so lease_result.json (written to S3 below) -- not metrics["lease_
        # acquired"] -- is the source of truth the state machine reads via
        # s3:getObject; the metric is telemetry only, kept in sync but never
        # consulted by the SFN.
        requested_mode = str(scope["mode"] or "").strip()
        if requested_mode not in {"daily", "backstop"}:
            raise WarehouseRuntimeError(
                f"acquire-identity-refresh-lease requires --mode of 'daily' or 'backstop', got {requested_mode!r}"
            )
        # An overdue backstop (persisted on pipeline_run_lease, set when a
        # prior 'backstop' attempt was deferred) takes priority over
        # whatever this trigger's own regular schedule slot requested --
        # release-readiness ticket 45's "prioritize the next available
        # slot" requirement. The persisted flag decides the effective mode,
        # not the caller's --mode; lease_result.json (below) carries that
        # resolved value, and the state machine's ApplyEffectiveRefreshMode
        # step overwrites $.refresh_mode with it before RefreshMode dispatches.
        lease_before = db.get_pipeline_run_lease(IDENTITY_REFRESH_LEASE_NAME)
        overdue_before = bool(lease_before and lease_before.get("backstop_overdue"))
        effective_mode = "backstop" if overdue_before else requested_mode
        acquired = db.acquire_pipeline_run_lease(
            lease_name=IDENTITY_REFRESH_LEASE_NAME,
            run_id=sync_run_id,
            mode=effective_mode,
            acquired_at=now,
        )
        held = db.get_pipeline_run_lease(IDENTITY_REFRESH_LEASE_NAME)
        if acquired:
            _emit_pipeline_event(
                "identity_refresh_lease_acquired",
                run_id=sync_run_id,
                mode=effective_mode,
                requested_mode=requested_mode,
            )
        else:
            if effective_mode == "backstop":
                db.mark_pipeline_run_lease_backstop_overdue(lease_name=IDENTITY_REFRESH_LEASE_NAME)
            _emit_pipeline_event(
                "identity_refresh_lease_deferred",
                run_id=sync_run_id,
                mode=effective_mode,
                requested_mode=requested_mode,
                held_by_run_id=held.get("run_id") if held else None,
                held_since=str(held.get("acquired_at")) if held else None,
                backstop_overdue=(effective_mode == "backstop"),
            )
        metrics["lease_acquired"] = acquired
        metrics["effective_refresh_mode"] = effective_mode
        lease_result_rel = default_path_resolver().identity_refresh_lease_path(sync_run_id)
        context.bronze_root.write_json(
            lease_result_rel,
            {
                "lease_acquired": acquired,
                "mode": effective_mode,
                "backstop_overdue": bool((not acquired) and effective_mode == "backstop"),
                "held_by_run_id": (held.get("run_id") if held else None),
            },
        )
        return raw_writes, metrics

    if command_name == "release-identity-refresh-lease":
        db.release_pipeline_run_lease(
            lease_name=IDENTITY_REFRESH_LEASE_NAME,
            run_id=sync_run_id,
            released_at=now,
        )
        _emit_pipeline_event("identity_refresh_lease_released", run_id=sync_run_id)
        return raw_writes, metrics

    if command_name == "acquire-sec-fetch-lease":
        # Cross-command SEC-fetch mutual exclusion (release-readiness ticket
        # 80). No mode/backstop concept here -- unlike the identity-refresh
        # lease, there's no priority-scheduling policy to resolve server-side;
        # a caller either gets the lease or is deferred. lease_result.json (not
        # metrics["lease_acquired"]) is the source of truth a Step Functions
        # Choice state reads, matching the identity-refresh lease's own
        # ecs:runTask.sync limitation.
        #
        # stale_after_seconds is 16h, not the 20h identity-refresh default:
        # ticket 84 sized it against real measured prod runtimes for the 5
        # SEC-fetching commands (daily-incremental ~7h7m, bootstrap ~4h10m)
        # plus the worst documented related-pipeline run (13h20m, the
        # pre-fix daily accession-expansion case in CLAUDE.md) with ~2h40m
        # margin over that -- the same bound-plus-margin reasoning the
        # existing 18h/20h identity-refresh pair used. This lease's
        # acquired_at is never renewed during a hold (no heartbeat), so this
        # value is a hard cap on how long a protected run may take before a
        # waiting command can reclaim the lease out from under it.
        acquired = db.acquire_pipeline_run_lease(
            lease_name=SEC_FETCH_LEASE_NAME,
            run_id=sync_run_id,
            mode="fetch",
            acquired_at=now,
            stale_after_seconds=SEC_FETCH_LEASE_STALE_AFTER_SECONDS,
        )
        held = db.get_pipeline_run_lease(SEC_FETCH_LEASE_NAME)
        if acquired:
            _emit_pipeline_event("sec_fetch_lease_acquired", run_id=sync_run_id)
        else:
            _emit_pipeline_event(
                "sec_fetch_lease_deferred",
                run_id=sync_run_id,
                held_by_run_id=held.get("run_id") if held else None,
                held_since=str(held.get("acquired_at")) if held else None,
            )
        metrics["lease_acquired"] = acquired
        lease_result_rel = default_path_resolver().sec_fetch_lease_path(sync_run_id)
        context.bronze_root.write_json(
            lease_result_rel,
            {
                "lease_acquired": acquired,
                "held_by_run_id": (held.get("run_id") if held else None),
            },
        )
        return raw_writes, metrics

    if command_name == "release-sec-fetch-lease":
        db.release_pipeline_run_lease(
            lease_name=SEC_FETCH_LEASE_NAME,
            run_id=sync_run_id,
            released_at=now,
        )
        _emit_pipeline_event("sec_fetch_lease_released", run_id=sync_run_id)
        return raw_writes, metrics

    if command_name == "write-run-summary":
        # Derive both manifest paths from sync_run_id via the canonical resolver --
        # the single source of truth for these keys (matches compute-windows' own
        # write path). Previously this key was hand-built in the calling ASL and
        # passed in as --from-windows-key, which drifted out of sync with
        # WAREHOUSE_BRONZE_ROOT's own "warehouse/bronze" prefix and produced a
        # doubled-prefix key that could never resolve.
        windows_rel = default_path_resolver().cik_windows_path(sync_run_id)
        windows_full_path = context.bronze_root.join(windows_rel)
        try:
            windows_bytes = read_bytes(windows_full_path)
        except (FileNotFoundError, OSError) as exc:
            raise WarehouseRuntimeError(
                f"write-run-summary: cik_windows.jsonl not found at S3 key '{windows_rel}'"
            ) from exc
        windows_text = windows_bytes.decode("utf-8")
        window_lines = [line for line in windows_text.splitlines() if line.strip()]
        if not window_lines:
            raise WarehouseRuntimeError(
                f"write-run-summary: cik_windows.jsonl at '{windows_rel}' is empty"
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
        "network_fetches": int(result.get("network_fetches", 0) or 0),
        "silver_skips": int(result.get("silver_skips", 0) or 0),
        "accessions_with_network": int(result.get("accessions_with_network", 0) or 0),
        "accessions_silver_skip": int(result.get("accessions_silver_skip", 0) or 0),
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
    release_mode: bool = False,
    recurring_mode: bool = False,
    required_accessions: set[str] | None = None,
    required_candidate_rows: Mapping[str, Mapping[str, Any]] | None = None,
    repair_manifest_accessions: set[str] | None = None,
    ownership_lookback_years: Any = None,
    item_502_lookback_years: Any = None,
    filing_lookback_years: Any = None,
) -> dict[str, Any]:
    """Capture every selected SEC submission into bronze before applying silver."""
    if release_mode and recurring_mode:
        raise WarehouseRuntimeError(
            "submission processing cannot be both release and recurring mode"
        )
    filing_min_date = _ownership_min_filing_date(_resolve_filing_lookback_years(filing_lookback_years))
    total_ciks = len(ciks)
    bronze_started_at = datetime.now(UTC)
    _emit_pipeline_event(
        "bronze_capture_started",
        cik_count=total_ciks,
        include_pagination=include_pagination,
        load_mode=load_mode,
        run_id=sync_run_id,
    )

    def _emit_bronze_progress(captured: int) -> None:
        if captured == total_ciks or captured % 10 == 0:
            _emit_pipeline_event(
                "bronze_capture_progress",
                captured=captured,
                cik_count=total_ciks,
                run_id=sync_run_id,
            )

    bronze_snapshots = _capture_submission_bronze_snapshots(
        context=context,
        db=db,
        ciks=ciks,
        include_pagination=include_pagination,
        fetch_date=fetch_date,
        force=force,
        on_progress=_emit_bronze_progress,
    )
    raw_writes = [
        write_record
        for snapshot in bronze_snapshots
        for write_record in snapshot["raw_writes"]
    ]
    # Ticket 05: count catalog network vs cache hits from write_record.cached
    catalog_network = 0
    catalog_skips = 0
    for write_record in raw_writes:
        if write_record.get("cached"):
            catalog_skips += 1
        else:
            catalog_network += 1
    _emit_pipeline_event(
        "bronze_capture_completed",
        cik_count=total_ciks,
        duration_seconds=(datetime.now(UTC) - bronze_started_at).total_seconds(),
        raw_object_count=len(raw_writes),
        catalog_network_fetches=catalog_network,
        catalog_silver_skips=catalog_skips,
        run_id=sync_run_id,
    )

    rows_written = 0
    rows_skipped = 0
    recent_accessions: list[str] = []
    pagination_accessions: list[str] = []
    filtered_by_lookback_count = 0
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
            filing_min_date=filing_min_date,
        )
        rows_written += int(result["rows_written"])
        rows_skipped += int(result["rows_skipped"])
        recent_accessions.extend(result["recent_accessions"])
        pagination_accessions.extend(result["pagination_accessions"])
        filtered_by_lookback_count += int(result.get("filtered_by_lookback_count", 0) or 0)
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
    if filtered_by_lookback_count:
        _emit_pipeline_event(
            "filing_lookback_filtered",
            skipped_count=filtered_by_lookback_count,
            lookback_years=_resolve_filing_lookback_years(filing_lookback_years),
            min_filing_date=filing_min_date.isoformat() if filing_min_date else None,
            run_id=sync_run_id,
        )

    observed_accessions = _dedupe_strings([*recent_accessions, *pagination_accessions])
    if release_mode or recurring_mode:
        required = set(required_accessions or ())
        missing = sorted(required - set(observed_accessions))
        if missing:
            seed_rows: list[dict[str, Any]] = []
            unavailable_metadata: list[str] = []
            for accession in missing:
                if db.get_filing(accession) is not None:
                    continue
                candidate_row = (required_candidate_rows or {}).get(accession)
                if candidate_row is None:
                    unavailable_metadata.append(accession)
                    continue
                seed_rows.append(dict(candidate_row))
            if unavailable_metadata:
                candidate_kind = "daily-index" if recurring_mode else "relationship"
                raise WarehouseRuntimeError(
                    f"required {candidate_kind} candidates missing frozen index metadata: "
                    f"{unavailable_metadata}"
                )
            if seed_rows:
                rows_written += int(db.merge_filings(seed_rows, sync_run_id))
            unresolved = [accession for accession in missing if db.get_filing(accession) is None]
            if unresolved:
                candidate_kind = "daily-index" if recurring_mode else "relationship"
                raise WarehouseRuntimeError(
                    f"required {candidate_kind} candidates could not be staged: {unresolved}"
                )
        artifact_accessions = [
            accession for accession in observed_accessions if accession in required
        ]
        artifact_accessions.extend(
            accession for accession in missing if accession not in artifact_accessions
        )
    else:
        artifact_accessions = observed_accessions

    if recurring_mode:
        required = set(required_accessions or ())
        bounded = set(artifact_accessions)
        out_of_union = bounded - required
        _emit_pipeline_event(
            "daily_artifact_boundary_applied",
            daily_index_accession_count=len(required),
            daily_index_accession_digest=_accession_set_digest(required),
            recent_source_count=len(set(recent_accessions)),
            pagination_source_count=len(set(pagination_accessions)),
            observed_source_count=len(set(observed_accessions)),
            bounded_candidate_count=len(bounded),
            historical_candidates_excluded_count=len(set(observed_accessions) - required),
            seeded_candidate_count=len(set(missing)),
            out_of_union_count=len(out_of_union),
            run_id=sync_run_id,
        )
        if out_of_union:
            raise WarehouseRuntimeError(
                "daily artifact expansion-contract violation before configured-form selection"
            )

    artifact_result = _run_configured_form_artifact_pipeline(
        context=context,
        db=db,
        sync_run_id=sync_run_id,
        accession_numbers=artifact_accessions,
        artifact_policy=artifact_policy,
        parser_policy=parser_policy,
        force=force,
        release_mode=release_mode,
        recurring_mode=recurring_mode,
        accession_boundary=(set(required_accessions or ()) if recurring_mode else None),
        repair_manifest_accessions=repair_manifest_accessions,
        ownership_lookback_years=ownership_lookback_years,
        item_502_lookback_years=item_502_lookback_years,
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
        "candidate_outcomes": artifact_result.get("candidate_outcomes", []),
        "network_fetches": int(artifact_result.get("network_fetches", 0) or 0),
        "silver_skips": int(artifact_result.get("silver_skips", 0) or 0),
        "accessions_with_network": int(artifact_result.get("accessions_with_network", 0) or 0),
        "accessions_silver_skip": int(artifact_result.get("accessions_silver_skip", 0) or 0),
        "catalog_network_fetches": catalog_network,
        "catalog_silver_skips": catalog_skips,
    }


def _is_transient_artifact_error(exc: BaseException) -> bool:
    """Return whether an artifact failure is safe to retry without changing inputs."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    transient_names = {
        "connecterror",
        "connectionerror",
        "connecttimeout",
        "gaierror",
        "networkerror",
        "protocolerror",
        "readtimeout",
        "remotedisconnected",
        "timeouterror",
        "transientfilingcontenterror",
    }
    # 403 included: SEC EDGAR is unauthenticated, so a 403 on a validly-built
    # archive URL is its edge/WAF rate-limit signal, not a permission denial
    # (Ticket 20 regression 2026-07-21 -- a single 403 fetching a quarterly
    # full-index file aborted an entire 116-batch strict release under 0%
    # tolerance; confirmed transient both by an immediate manual re-fetch
    # succeeding and by three concurrent sibling batches completing the same
    # window with zero errors, ruling out a sustained/concurrency-driven block).
    transient_statuses = {403, 408, 429, 500, 502, 503, 504}

    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, (TimeoutError, ConnectionError)):
            return True
        error_names = {error_type.__name__.lower() for error_type in type(current).__mro__}
        if any(
            error_name in transient_names or error_name.endswith("timeout")
            for error_name in error_names
        ):
            return True

        response = getattr(current, "response", None)
        if getattr(response, "status_code", None) in transient_statuses:
            return True
        for nested in (
            getattr(current, "__cause__", None),
            getattr(current, "__context__", None),
            getattr(current, "reason", None),
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return False


def _is_immutable_object_conflict(exc: BaseException) -> bool:
    """Classify immutable content conflicts as operator-repair dispositions."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        message = str(current).lower()
        if "immutable object" in message and "different content" in message:
            return True
        for nested in (getattr(current, "__cause__", None), getattr(current, "__context__", None)):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return False


def _reset_edgartools_client_after_pool_timeout(exc: BaseException) -> bool:
    """Discard edgartools' process-wide client when its connection pool is exhausted."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if any(
            error_type.__name__.lower() == "pooltimeout"
            for error_type in type(current).__mro__
        ):
            from edgar.httpclient import close_clients

            close_clients()
            return True
        for nested in (
            getattr(current, "__cause__", None),
            getattr(current, "__context__", None),
            getattr(current, "reason", None),
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return False


def _reset_edgartools_filing_cache_after_transient_content_error(exc: BaseException) -> bool:
    """Evict edgartools' cached Filing after a transient SEC content-degradation error.

    `edgar.get_by_accession_number` resolves through `get_filing_by_accession`, which
    is wrapped in `@cache_except_none(maxsize=16)` (edgar/core.py) -- once it returns a
    Filing object for an accession, that *same instance* is replayed on every later
    call in-process, including our own retry attempts. `Filing.sgml()` then also
    caches on `self._sgml`, so a Filing whose SGML fetch degraded to the homepage
    fallback (see TransientFilingContentError) keeps returning that identical
    degraded result forever within this process -- retrying without busting this
    cache is a no-op that always replays the same bad response. Mirrors
    `_reset_edgartools_client_after_pool_timeout`'s HTTP-client-reuse fix for the
    same "edgartools reuses internal state across calls" class of issue.
    """
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if any(
            error_type.__name__.lower() == "transientfilingcontenterror"
            for error_type in type(current).__mro__
        ):
            from edgar._filings import get_filing_by_accession

            get_filing_by_accession.cache_clear()
            return True
        for nested in (
            getattr(current, "__cause__", None),
            getattr(current, "__context__", None),
            getattr(current, "reason", None),
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return False



def _merge_capture_network_metrics(metrics: dict[str, Any], result: dict[str, Any]) -> None:
    """Fold network_fetches / silver_skips from a pipeline result into command metrics."""
    for key in (
        "network_fetches",
        "silver_skips",
        "accessions_with_network",
        "accessions_silver_skip",
        "catalog_network_fetches",
        "catalog_silver_skips",
    ):
        if key in result:
            metrics[key] = int(metrics.get(key, 0) or 0) + int(result.get(key, 0) or 0)


def _run_configured_form_artifact_pipeline(
    *,
    context: WarehouseCommandContext,
    db: SilverDatabase,
    sync_run_id: str,
    accession_numbers: list[str],
    artifact_policy: str,
    parser_policy: str,
    force: bool,
    release_mode: bool = False,
    recurring_mode: bool = False,
    accession_boundary: set[str] | None = None,
    repair_manifest_accessions: set[str] | None = None,
    ownership_lookback_years: Any = None,
    item_502_lookback_years: Any = None,
) -> dict[str, Any]:
    if release_mode and recurring_mode:
        raise WarehouseRuntimeError(
            "artifact processing cannot be both release and recurring mode"
        )
    if recurring_mode and accession_boundary is None:
        raise WarehouseRuntimeError(
            "recurring artifact processing requires an exact daily-index accession boundary"
        )
    if release_mode and force and not repair_manifest_accessions:
        raise WarehouseRuntimeError("release --force requires an explicit bounded repair manifest")
    fetch_artifacts = _artifact_policy_fetches(artifact_policy)
    branch_b_deferred = _normalize_policy(parser_policy) == "branch_b_deferred"
    run_parsers = _parser_policy_runs(parser_policy)
    if release_mode and (not fetch_artifacts or not (run_parsers or branch_b_deferred)):
        raise WarehouseRuntimeError(
            "release mode requires artifact fetch and parser policies"
        )
    _empty_network = {
        "network_fetches": 0,
        "silver_skips": 0,
        "accessions_with_network": 0,
        "accessions_silver_skip": 0,
    }
    if not fetch_artifacts and not run_parsers:
        return {"raw_writes": [], "rows_written": 0, "rows_skipped": 0, **_empty_network}

    selection_metrics: dict[str, Any] = {}
    selected_accessions = _configured_parser_accessions(
        db,
        accession_numbers,
        ownership_lookback_years=ownership_lookback_years,
        item_502_lookback_years=item_502_lookback_years,
        selection_metrics=selection_metrics,
    )
    out_of_union: list[str] = []
    if recurring_mode:
        out_of_union = sorted(set(selected_accessions) - set(accession_boundary or ()))
        _emit_pipeline_event(
            "daily_artifact_selection_completed",
            daily_index_accession_count=len(accession_boundary or ()),
            daily_index_accession_digest=_accession_set_digest(accession_boundary or ()),
            out_of_union_count=len(out_of_union),
            run_id=sync_run_id,
            **selection_metrics,
        )
        if out_of_union:
            _emit_pipeline_event(
                "daily_artifact_expansion_contract_violation",
                out_of_union_count=len(out_of_union),
                out_of_union_digest=_accession_set_digest(out_of_union),
                run_id=sync_run_id,
            )
            raise WarehouseRuntimeError(
                "daily artifact expansion-contract violation; configured candidates "
                f"outside forced-index accession union: {out_of_union}"
            )
    if release_mode and force:
        unapproved = sorted(set(selected_accessions) - set(repair_manifest_accessions or ()))
        if unapproved:
            raise WarehouseRuntimeError(f"release force includes accessions outside repair manifest: {unapproved}")
    if not selected_accessions and not recurring_mode:
        return {"raw_writes": [], "rows_written": 0, "rows_skipped": 0, **_empty_network}

    resume_manifest: dict[str, Any] | None = None
    repair_required: list[str] = []
    resumed_accessions = 0
    if recurring_mode and hasattr(context, "storage_root"):
        from edgar_warehouse.application.daily_artifact_resume import prepare_resume

        selected_before_resume = list(selected_accessions)
        selected_accessions, repair_required, resume_manifest = prepare_resume(
            context.storage_root,
            run_id=sync_run_id,
            # Production task definitions inject the immutable digest; the
            # sentinel exists only for isolated local tests.
            image_identity=os.environ.get("WAREHOUSE_IMAGE_REF", "").strip() or "local-development",
            daily_index_accessions=accession_boundary or (),
            selected_accessions=selected_accessions,
        )
        resumed_accessions = len(selected_before_resume) - len(selected_accessions) - len(repair_required)
        _emit_pipeline_event(
            "daily_artifact_resume_loaded",
            run_id=sync_run_id,
            resumed_accession_count=resumed_accessions,
            pending_accession_count=len(selected_accessions),
            terminal_repair_count=len(repair_required),
        )

    _emit_pipeline_event(
        "filing_artifact_pipeline_started",
        accession_count=len(selected_accessions),
        artifact_policy=artifact_policy,
        parser_policy=parser_policy,
        run_id=sync_run_id,
    )
    artifact_started_at = datetime.now(UTC)
    import time as _time
    _CONSECUTIVE_ERROR_LIMIT = int(os.environ.get("WAREHOUSE_ARTIFACT_CIRCUIT_BREAKER", "20"))
    raw_writes: list[dict[str, Any]] = []
    candidate_outcomes: list[dict[str, str]] = []
    rows_written = 0
    errors = 0
    consecutive_errors = 0
    conflict_skipped_count = 0
    circuit_opened = False
    retry_count = 0
    processed_accessions = 0
    attempted_accessions = 0
    fast_parse_skips = 0
    artifact_attempts = 1
    from edgar_warehouse.infrastructure.capture_metrics import CaptureNetworkMetrics

    capture_network = CaptureNetworkMetrics()
    progress_every = max(1, int(os.environ.get("WAREHOUSE_ARTIFACT_PROGRESS_EVERY", "100")))

    def emit_partial(*, reason: str, processed: int, remaining: int) -> None:
        _emit_pipeline_event(
            "filing_artifact_pipeline_partial",
            accession_count=len(selected_accessions),
            attempted_accessions=attempted_accessions,
            processed_accessions=processed,
            remaining_accessions=remaining,
            errors=errors,
            retry_count=retry_count,
            fast_parse_skips=fast_parse_skips,
            circuit_breaker_disposition=(
                "open" if reason == "circuit_open" else "closed"
            ),
            reason=reason,
            duration_seconds=(datetime.now(UTC) - artifact_started_at).total_seconds(),
            run_id=sync_run_id,
            **capture_network.as_dict(),
        )

    for accession_index, accession_number in enumerate(selected_accessions, start=1):
        if consecutive_errors >= _CONSECUTIVE_ERROR_LIMIT:
            remaining_accessions = len(selected_accessions) - processed_accessions
            circuit_opened = True
            _emit_pipeline_event(
                "filing_artifact_circuit_open",
                consecutive_errors=consecutive_errors,
                attempted_accessions=attempted_accessions,
                processed_accessions=processed_accessions,
                remaining_accessions=remaining_accessions,
                run_id=sync_run_id,
            )
            if release_mode or recurring_mode:
                emit_partial(
                    reason="circuit_open",
                    processed=processed_accessions,
                    remaining=remaining_accessions,
                )
                raise WarehouseRuntimeError(
                    "artifact circuit breaker left "
                    f"{remaining_accessions} unresolved candidates"
                )
            break
        attempted_accessions = accession_index
        try:
            # Ticket 03: silver-once ownership skip (accession + parser_version).
            # When silver already has a successful ownership parse at the current
            # parser_version and force is false, skip network + re-parse.
            # strict_release still requires hashed evidence if raw objects missing.
            ownership_skip = False
            if not force:
                filing_meta = db.get_filing(accession_number) or {}
                form_type = str(filing_meta.get("form") or "")
                parser_name, parser_version, form_family = _parser_metadata(
                    form_type, items=filing_meta.get("items")
                )
                if form_family == "ownership":
                    from edgar_warehouse.infrastructure.silver_once import (
                        has_successful_ownership_parse,
                    )

                    if has_successful_ownership_parse(
                        db,
                        accession_number=accession_number,
                        parser_name=parser_name,
                        parser_version=parser_version,
                    ):
                        needs_evidence = False
                        if release_mode:
                            attachments = db.get_filing_attachments(accession_number)
                            needs_evidence = not any(
                                (db.get_raw_object(str(a.get("raw_object_id"))) or {}).get("sha256")
                                for a in attachments
                                if a.get("raw_object_id")
                            )
                        if not needs_evidence:
                            ownership_skip = True
                            fast_parse_skips += 1
                            capture_network.record_artifact_result({"network_fetches": 0})
                            consecutive_errors = 0
                            if release_mode:
                                evidence_parts: list[str] = []
                                for attachment in db.get_filing_attachments(accession_number):
                                    raw_object_id = attachment.get("raw_object_id")
                                    raw_object = (
                                        db.get_raw_object(str(raw_object_id)) if raw_object_id else None
                                    )
                                    if raw_object and raw_object.get("sha256"):
                                        evidence_parts.append(str(raw_object["sha256"]))
                                if evidence_parts:
                                    candidate_outcomes.append({
                                        "accession_number": accession_number,
                                        "status": (
                                            "artifacts_loaded"
                                            if branch_b_deferred
                                            else "applicable_loaded"
                                        ),
                                        "evidence_fingerprint": hashlib.sha256(
                                            "|".join(sorted(evidence_parts)).encode("utf-8")
                                        ).hexdigest(),
                                    })
                            processed_accessions += 1
                            if (
                                accession_index % progress_every == 0
                                or accession_index == len(selected_accessions)
                            ):
                                _emit_pipeline_event(
                                    "filing_artifact_pipeline_progress",
                                    processed=accession_index,
                                    accession_count=len(selected_accessions),
                                    rows_written=rows_written,
                                    errors=errors,
                                    retry_count=retry_count,
                                    fast_parse_skips=fast_parse_skips,
                                    progress_every=progress_every,
                                    run_id=sync_run_id,
                                    **capture_network.as_dict(),
                                )
                            continue

            if fetch_artifacts:
                from edgar_warehouse.infrastructure.filing_artifact_service import refresh_filing_artifacts

                if release_mode:
                    artifact_attempts = max(
                        1,
                        int(os.environ.get("WAREHOUSE_RELEASE_ARTIFACT_ATTEMPTS", "3")),
                    )
                elif recurring_mode:
                    artifact_attempts = max(
                        1,
                        int(os.environ.get("WAREHOUSE_RECURRING_ARTIFACT_ATTEMPTS", "3")),
                    )
                else:
                    artifact_attempts = 1
                artifact_retry_base_seconds = float(
                    os.environ.get(
                        (
                            "WAREHOUSE_RELEASE_ARTIFACT_RETRY_BASE_SECONDS"
                            if release_mode
                            else "WAREHOUSE_RECURRING_ARTIFACT_RETRY_BASE_SECONDS"
                        ),
                        "1.0",
                    )
                )
                for artifact_attempt in range(1, artifact_attempts + 1):
                    try:
                        artifact_result = refresh_filing_artifacts(
                            context=context,
                            db=db,
                            accession_number=accession_number,
                            sync_run_id=sync_run_id,
                            force=force,
                        )
                        break
                    except Exception as exc:
                        if (
                            artifact_attempt >= artifact_attempts
                            or not _is_transient_artifact_error(exc)
                        ):
                            raise
                        retry_delay = artifact_retry_base_seconds * (2 ** (artifact_attempt - 1))
                        client_reset = _reset_edgartools_client_after_pool_timeout(exc)
                        filing_cache_reset = _reset_edgartools_filing_cache_after_transient_content_error(exc)
                        retry_count += 1
                        _emit_pipeline_event(
                            "filing_artifact_retry",
                            accession_number=accession_number,
                            attempt=artifact_attempt,
                            max_attempts=artifact_attempts,
                            retry_delay_seconds=retry_delay,
                            error_type=type(exc).__name__,
                            error=repr(exc),
                            edgartools_client_reset=client_reset,
                            edgartools_filing_cache_reset=filing_cache_reset,
                            run_id=sync_run_id,
                        )
                        _time.sleep(retry_delay)
                raw_writes.extend(artifact_result["raw_writes"])
                rows_written += int(artifact_result["attachment_count"])
                capture_network.record_artifact_result(artifact_result)
                # Throttle only when a real SEC network fetch occurred. On the
                # idempotent cache-hit path (immutable, already-captured artifacts)
                # no request was made, so the SEC rate-limit sleep is pure dead time
                # — e.g. 5,583 cached accessions x 1s = ~93 min of no-op throttle on a
                # re-run. Default to throttling if the flag is absent (conservative).
                # See CLAUDE.md artifact-throttle 5-whys.
                #
                # Default lowered 1.0 -> 0.2: sec_client.py's pyrate_limiter bucket
                # (9 req/sec, matching EDGAR_RATE_LIMIT_PER_SEC) already throttles every
                # individual SEC request; this sleep is a second, per-accession-level
                # throttle on top of it, not the primary safety net. 0.2s keeps a
                # conservative floor without adding multi-second dead time per fetch.
                if int(artifact_result.get("network_fetches", 1)) > 0:
                    _time.sleep(float(os.environ.get("WAREHOUSE_ARTIFACT_REQUEST_DELAY", "0.2")))
            if run_parsers:
                rows_written += _run_parse_pipeline(
                    db=db,
                    accession_number=accession_number,
                    sync_run_id=sync_run_id,
                    fail_closed=release_mode,
                )
            if release_mode:
                evidence_parts = []
                for attachment in db.get_filing_attachments(accession_number):
                    raw_object_id = attachment.get("raw_object_id")
                    raw_object = db.get_raw_object(str(raw_object_id)) if raw_object_id else None
                    if raw_object and raw_object.get("sha256"):
                        evidence_parts.append(str(raw_object["sha256"]))
                if not evidence_parts:
                    raise WarehouseRuntimeError(
                        f"required artifact candidate {accession_number} has no hashed evidence"
                    )
                candidate_outcomes.append({
                    "accession_number": accession_number,
                    "status": "artifacts_loaded" if branch_b_deferred else "applicable_loaded",
                    "evidence_fingerprint": hashlib.sha256(
                        "|".join(sorted(evidence_parts)).encode("utf-8")
                    ).hexdigest(),
                })
            if recurring_mode and resume_manifest is not None:
                from edgar_warehouse.application.daily_artifact_resume import record_succeeded

                record_succeeded(
                    context.storage_root,
                    run_id=sync_run_id,
                    accession=accession_number,
                    manifest=resume_manifest or {},
                )
            consecutive_errors = 0
            processed_accessions += 1
        except Exception as exc:
            errors += 1
            # release-readiness ticket 93: an immutable-object conflict (SEC-side
            # byte drift on an already-captured document, e.g. a trailing-newline
            # change -- confirmed live, not a repo-side bug, see ticket 87) is an
            # isolated, individually-recoverable condition on this one accession,
            # not a signal of systemic failure. Counting it toward the circuit
            # breaker's consecutive-error streak let a cluster of these (43 in one
            # observed run) trip the breaker and silently abandon thousands of
            # unrelated, healthy candidates while still exiting 0. Still counted in
            # `errors`/logged via filing_artifact_failed below, just excluded from
            # the streak that trips the breaker -- mirrors ticket 87's
            # skip-and-continue isolation for targeted-resync.
            if _is_immutable_object_conflict(exc):
                conflict_skipped_count += 1
                consecutive_errors = 0
            else:
                consecutive_errors += 1
            _emit_pipeline_event(
                "filing_artifact_failed",
                accession_number=accession_number,
                error_type=type(exc).__name__,
                error=repr(exc),
                run_id=sync_run_id,
            )
            if recurring_mode and resume_manifest is not None and _is_immutable_object_conflict(exc):
                from edgar_warehouse.application.daily_artifact_resume import record_terminal_repair

                record_terminal_repair(
                    context.storage_root,
                    run_id=sync_run_id,
                    accession=accession_number,
                    manifest=resume_manifest or {},
                    error_type=type(exc).__name__,
                    error=repr(exc),
                )
            if release_mode:
                raise WarehouseRuntimeError(
                    f"required artifact candidate {accession_number} failed"
                ) from exc
            if recurring_mode and consecutive_errors >= _CONSECUTIVE_ERROR_LIMIT:
                remaining_accessions = len(selected_accessions) - processed_accessions
                circuit_opened = True
                _emit_pipeline_event(
                    "filing_artifact_circuit_open",
                    consecutive_errors=consecutive_errors,
                    attempted_accessions=attempted_accessions,
                    processed_accessions=processed_accessions,
                    remaining_accessions=remaining_accessions,
                    run_id=sync_run_id,
                )
                emit_partial(
                    reason="circuit_open",
                    processed=processed_accessions,
                    remaining=remaining_accessions,
                )
                raise WarehouseRuntimeError(
                    "artifact circuit breaker left "
                    f"{remaining_accessions} unresolved candidates"
                ) from exc
            if recurring_mode and _is_transient_artifact_error(exc):
                remaining_accessions = len(selected_accessions) - processed_accessions
                emit_partial(
                    reason="retry_exhausted",
                    processed=processed_accessions,
                    remaining=remaining_accessions,
                )
                raise WarehouseRuntimeError(
                    "recurring artifact retry exhausted for "
                    f"{accession_number} after {artifact_attempts} attempts"
                ) from exc
        # P2: mid-pass progress so operators can see resume/cache work without
        # waiting for the whole batch to finish (start/complete-only was silent
        # for multi-hour StrictBatchSilver loops).
        if accession_index % progress_every == 0 or accession_index == len(selected_accessions):
            _emit_pipeline_event(
                "filing_artifact_pipeline_progress",
                processed=accession_index,
                attempted_accessions=attempted_accessions,
                processed_accessions=processed_accessions,
                accession_count=len(selected_accessions),
                rows_written=rows_written,
                errors=errors,
                progress_every=progress_every,
                run_id=sync_run_id,
                **capture_network.as_dict(),
            )
    if recurring_mode and (errors or repair_required):
        remaining_accessions = len(selected_accessions) - processed_accessions
        emit_partial(
            reason="candidate_failures",
            processed=processed_accessions,
            remaining=remaining_accessions,
        )
        raise WarehouseRuntimeError(
            f"recurring artifact pipeline had {errors} failed candidates and "
            f"{len(repair_required)} terminal repair candidates"
        )
    network_metrics = capture_network.as_dict()
    _emit_pipeline_event(
        "filing_artifact_pipeline_completed",
        accession_count=len(selected_accessions),
        raw_object_count=len(raw_writes),
        rows_written=rows_written,
        errors=errors,
        retry_count=retry_count,
        fast_parse_skips=fast_parse_skips,
        attempted_accessions=attempted_accessions,
        processed_accessions=processed_accessions,
        remaining_accessions=len(selected_accessions) - processed_accessions,
        circuit_breaker_disposition="open" if circuit_opened else "closed",
        conflict_skipped_count=conflict_skipped_count,
        duration_seconds=(datetime.now(UTC) - artifact_started_at).total_seconds(),
        run_id=sync_run_id,
        **network_metrics,
    )
    return {
        "raw_writes": raw_writes,
        "rows_written": rows_written,
        "rows_skipped": errors,
        "candidate_outcomes": candidate_outcomes,
        "retry_count": retry_count,
        "fast_parse_skips": fast_parse_skips,
        "conflict_skipped_count": conflict_skipped_count,
        "attempted_accessions": attempted_accessions,
        "processed_accessions": processed_accessions,
        "remaining_accessions": len(selected_accessions) - processed_accessions,
        **network_metrics,
    }


def _run_release_branch_b_parsers(
    *,
    db: SilverDatabase,
    ciks: list[int],
    candidates: Iterable[Any],
    sync_run_id: str,
) -> dict[str, dict[str, str]]:
    """Run strict Branch B parsers and return one terminal outcome per required accession."""
    from edgar_warehouse.application.workflows.fundamentals_ingest import (
        BRANCH_B_13F_FORMS,
        BRANCH_B_FILING_FORMS,
        run_bootstrap_fundamentals_per_filing,
        run_bootstrap_thirteenf,
    )

    required = [candidate for candidate in candidates if candidate.artifact_required]
    per_filing = {
        candidate.accession_number
        for candidate in required
        if candidate.form in BRANCH_B_FILING_FORMS
    }
    thirteenf = {
        candidate.accession_number
        for candidate in required
        if candidate.form in BRANCH_B_13F_FORMS
    }
    unsupported = sorted(
        candidate.accession_number
        for candidate in required
        if candidate.form not in BRANCH_B_FILING_FORMS | BRANCH_B_13F_FORMS
    )
    if unsupported:
        raise WarehouseRuntimeError(f"unsupported release relationship candidates: {unsupported}")

    rows: list[dict[str, str]] = []
    if per_filing:
        metrics = run_bootstrap_fundamentals_per_filing(
            cik_list=ciks,
            source=db,
            db=db,
            sync_run_id=sync_run_id,
            release_mode=True,
            candidate_accessions=per_filing,
        )
        rows.extend(metrics.get("candidate_outcomes", []))
    if thirteenf:
        metrics = run_bootstrap_thirteenf(
            cik_list=ciks,
            source=db,
            db=db,
            sync_run_id=sync_run_id,
            release_mode=True,
            candidate_accessions=thirteenf,
        )
        rows.extend(metrics.get("candidate_outcomes", []))

    outcomes: dict[str, dict[str, str]] = {}
    for row in rows:
        accession = str(row.get("accession_number") or "")
        if not accession or accession in outcomes:
            raise WarehouseRuntimeError(f"duplicate or invalid Branch B outcome: {accession}")
        outcomes[accession] = row
    missing = sorted((per_filing | thirteenf) - set(outcomes))
    if missing:
        raise WarehouseRuntimeError(f"missing Branch B terminal outcomes: {missing}")
    return outcomes


def _resolve_nonneg_lookback_years(
    raw: Any,
    *,
    default: int,
    env_name: str,
    field_name: str,
) -> int:
    """Shared integer lookback resolver. 0 disables the window (full history)."""
    if raw is not None and str(raw).strip() != "":
        try:
            years = int(raw)
        except (TypeError, ValueError) as exc:
            raise WarehouseRuntimeError(
                f"{field_name} must be an integer >= 0, got {raw!r}"
            ) from exc
    else:
        env = os.environ.get(env_name, "").strip()
        if env:
            try:
                years = int(env)
            except ValueError as exc:
                raise WarehouseRuntimeError(
                    f"{env_name} must be an integer >= 0, got {env!r}"
                ) from exc
        else:
            years = default
    if years < 0:
        raise WarehouseRuntimeError(f"{field_name} must be >= 0")
    return years


def _resolve_ownership_lookback_years(raw: Any = None) -> int:
    """Resolve Form 3/4/5 lookback years. Default 2; 0 disables the window (full history)."""
    return _resolve_nonneg_lookback_years(
        raw,
        default=DEFAULT_OWNERSHIP_LOOKBACK_YEARS,
        env_name="WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS",
        field_name="ownership_lookback_years",
    )


def _resolve_filing_lookback_years(raw: Any = None) -> int:
    """Resolve the general filing-discovery lookback (10-K/10-Q/8-K/DEF 14A/
    13F/ADV/etc). Default 0 (disabled, full history) -- unlike ownership/
    Item 5.02, this gates bronze discovery itself, so it stays opt-in."""
    return _resolve_nonneg_lookback_years(
        raw,
        default=DEFAULT_FILING_LOOKBACK_YEARS,
        env_name="WAREHOUSE_FILING_LOOKBACK_YEARS",
        field_name="filing_lookback_years",
    )


def _resolve_item_502_lookback_years(
    raw: Any = None,
    *,
    ownership_lookback_years: Any = None,
) -> int:
    """Resolve Item 5.02 8-K lookback years.

    Precedence: explicit arg → WAREHOUSE_ITEM_502_LOOKBACK_YEARS → ownership
    lookback (so one CLI knob bounds both sources on the integrated load) →
    DEFAULT_ITEM_502_LOOKBACK_YEARS (2).
    """
    if raw is not None and str(raw).strip() != "":
        return _resolve_nonneg_lookback_years(
            raw,
            default=DEFAULT_ITEM_502_LOOKBACK_YEARS,
            env_name="WAREHOUSE_ITEM_502_LOOKBACK_YEARS",
            field_name="item_502_lookback_years",
        )
    env = os.environ.get("WAREHOUSE_ITEM_502_LOOKBACK_YEARS", "").strip()
    if env:
        return _resolve_nonneg_lookback_years(
            None,
            default=DEFAULT_ITEM_502_LOOKBACK_YEARS,
            env_name="WAREHOUSE_ITEM_502_LOOKBACK_YEARS",
            field_name="item_502_lookback_years",
        )
    if ownership_lookback_years is not None and str(ownership_lookback_years).strip() != "":
        return _resolve_ownership_lookback_years(ownership_lookback_years)
    if os.environ.get("WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS", "").strip():
        return _resolve_ownership_lookback_years(None)
    return DEFAULT_ITEM_502_LOOKBACK_YEARS


def _ownership_min_filing_date(
    lookback_years: int,
    *,
    as_of: date | None = None,
) -> date | None:
    """Earliest filing_date included for ownership/Item 5.02 loads, or None when disabled."""
    if lookback_years == 0:
        return None
    as_of = as_of or date.today()
    try:
        return as_of.replace(year=as_of.year - lookback_years)
    except ValueError:
        # Feb 29 → Feb 28 on non-leap targets
        return as_of.replace(year=as_of.year - lookback_years, day=28)


def _ownership_filing_date(filing: Mapping[str, Any] | dict[str, Any] | None) -> date | None:
    """Prefer filing_date, fall back to report_date."""
    if not filing:
        return None
    for key in ("filing_date", "report_date"):
        value = filing.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            continue
    return None


def _ownership_within_lookback(
    filing: Mapping[str, Any] | dict[str, Any] | None,
    *,
    min_filing_date: date | None,
) -> bool:
    """True when filing is in-window (or undated / lookback disabled)."""
    if min_filing_date is None:
        return True
    filing_date = _ownership_filing_date(filing)
    if filing_date is None:
        # Undated rows are rare; keep them so a missing date does not silently drop data.
        return True
    return filing_date >= min_filing_date


def _is_item_502_candidate_form(form_type: Any, items: Any = None) -> bool:
    """True for 8-K/8-K/A with Item 5.02 declared or missing/ambiguous items."""
    normalized = str(form_type or "").strip().upper()
    if normalized not in {"8-K", "8-K/A"}:
        return False
    normalized_items = str(items or "").strip()
    if not normalized_items:
        return True
    return bool(re.search(r"(?:^|[^0-9])5\s*\.\s*02(?:[^0-9]|$)", normalized_items, re.I))


def _configured_parser_accessions(
    db: SilverDatabase,
    accession_numbers: list[str],
    *,
    ownership_lookback_years: Any = None,
    item_502_lookback_years: Any = None,
    as_of: date | None = None,
    selection_metrics: dict[str, Any] | None = None,
) -> list[str]:
    ownership_years = _resolve_ownership_lookback_years(ownership_lookback_years)
    item_502_years = _resolve_item_502_lookback_years(
        item_502_lookback_years,
        ownership_lookback_years=ownership_lookback_years,
    )
    ownership_min = _ownership_min_filing_date(ownership_years, as_of=as_of)
    item_502_min = _ownership_min_filing_date(item_502_years, as_of=as_of)
    selected: list[str] = []
    missing_metadata = 0
    rejected_unconfigured_form = 0
    skipped_ownership_lookback = 0
    skipped_item_502_lookback = 0
    selected_form_counts: dict[str, int] = {}
    deduped_accessions = _dedupe_strings(accession_numbers)
    for accession_number in deduped_accessions:
        filing = db.get_filing(accession_number)
        if filing is None:
            missing_metadata += 1
            continue
        form = filing.get("form")
        if not _is_configured_parser_form(form, filing.get("items")):
            rejected_unconfigured_form += 1
            continue
        normalized = str(form or "").strip().upper()
        if normalized in OWNERSHIP_FORMS and not _ownership_within_lookback(
            filing, min_filing_date=ownership_min
        ):
            skipped_ownership_lookback += 1
            continue
        if _is_item_502_candidate_form(form, filing.get("items")) and not _ownership_within_lookback(
            filing, min_filing_date=item_502_min
        ):
            skipped_item_502_lookback += 1
            continue
        selected.append(accession_number)
        form_name = str(form or "").strip().upper() or "UNKNOWN"
        selected_form_counts[form_name] = selected_form_counts.get(form_name, 0) + 1
    if selection_metrics is not None:
        selection_metrics.update(
            {
                "input_accession_count": len(deduped_accessions),
                "missing_metadata_count": missing_metadata,
                "configured_form_rejected_count": rejected_unconfigured_form,
                "ownership_lookback_rejected_count": skipped_ownership_lookback,
                "item_502_lookback_rejected_count": skipped_item_502_lookback,
                "configured_candidate_count": len(selected),
                "configured_form_counts": selected_form_counts,
            }
        )
    if skipped_ownership_lookback:
        _emit_pipeline_event(
            "ownership_lookback_filtered",
            skipped_count=skipped_ownership_lookback,
            lookback_years=ownership_years,
            min_filing_date=ownership_min.isoformat() if ownership_min else None,
        )
    if skipped_item_502_lookback:
        _emit_pipeline_event(
            "item_502_lookback_filtered",
            skipped_count=skipped_item_502_lookback,
            lookback_years=item_502_years,
            min_filing_date=item_502_min.isoformat() if item_502_min else None,
        )
    return selected


def _is_item_202_candidate_form(form_type: Any, items: Any = None) -> bool:
    """True for 8-K/8-K/A with Item 2.02 (earnings results) declared.

    Unlike ``_is_item_502_candidate_form``, blank/ambiguous items do not
    qualify here — the item-502 predicate already owns that ambiguous-items
    catch-all bucket, and earnings 8-Ks are always explicitly item-tagged by
    SEC filers.
    """
    normalized = str(form_type or "").strip().upper()
    if normalized not in {"8-K", "8-K/A"}:
        return False
    normalized_items = str(items or "").strip()
    if not normalized_items:
        return False
    return bool(re.search(r"(?:^|[^0-9])2\s*\.\s*02(?:[^0-9]|$)", normalized_items, re.I))


def _is_configured_parser_form(form_type: Any, items: Any = None) -> bool:
    normalized = str(form_type or "").strip().upper()
    if normalized in OWNERSHIP_FORMS or normalized in ADV_FORMS:
        return True
    if normalized in {"DEF 14A", "DEF 14A/A", "DEFA14A", "PRE 14A", "13F-HR", "13F-HR/A"}:
        return True
    if _is_item_502_candidate_form(form_type, items):
        return True
    if _is_item_202_candidate_form(form_type, items):
        return True
    return False


def _run_parse_ownership_bronze(
    *,
    context: "WarehouseCommandContext",
    db: "SilverDatabase",
    sync_run_id: str,
    metrics: dict[str, Any],
    limit: int | None = None,
    accession_list: list[str] | None = None,
    ownership_lookback_years: Any = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Parse Form 3/4/5 ownership XMLs that already exist in bronze into silver.

    Reads primary XML through the artifact registry (sec_filing_attachment +
    sec_raw_object + read_bytes) — no S3 prefix listing, no SEC API calls.
    Idempotent: skips accessions already present in sec_ownership_reporting_owner.
    Default lookback is past 2 years of Form 3/4/5 filings (filing_date).

    Args:
        context: Warehouse command context (bronze_root, silver_root, etc.)
        db: Silver database connection for queries and merges.
        sync_run_id: Run ID for audit trail and event payloads.
        metrics: Mutable dict; populated with parsed/skipped/errors/missing_artifacts/rows_written.
        limit: Optional cap on the number of accessions to process.
        accession_list: Optional explicit list of accession numbers to process
            (filters the sec_company_filing query result to this set).
        ownership_lookback_years: Years of Form 3/4/5 history to parse (default 2;
            0 = full history). Env WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS also accepted.
    """
    from edgar_warehouse.parsers.ownership import parse_ownership

    lookback_years = _resolve_ownership_lookback_years(ownership_lookback_years)
    min_filing_date = _ownership_min_filing_date(lookback_years)

    filings = db.fetch(
        """
        SELECT f.accession_number, f.cik, f.form, f.filing_date, f.report_date
        FROM sec_company_filing f
        WHERE f.form IN ('3','3/A','4','4/A','5','5/A')
        ORDER BY f.cik, f.report_date
        """
    )

    # Apply optional accession filter
    if accession_list is not None:
        allowed = set(accession_list)
        filings = [f for f in filings if f["accession_number"] in allowed]

    pre_lookback = len(filings)
    filings = [
        f for f in filings if _ownership_within_lookback(f, min_filing_date=min_filing_date)
    ]
    lookback_skipped = pre_lookback - len(filings)

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
        ownership_lookback_years=lookback_years,
        ownership_min_filing_date=min_filing_date.isoformat() if min_filing_date else None,
        ownership_lookback_skipped=lookback_skipped,
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
    metrics["ownership_lookback_years"] = lookback_years
    metrics["ownership_min_filing_date"] = (
        min_filing_date.isoformat() if min_filing_date else None
    )
    metrics["ownership_lookback_skipped"] = lookback_skipped
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
    if normalized in {"none", "skip", "disabled", "off", "branch_b_deferred"}:
        return False
    if normalized == "configured_forms":
        return True
    raise WarehouseRuntimeError(f"Unsupported parser_policy: {policy}")


def _normalize_policy(policy: str) -> str:
    return str(policy or "").strip().lower().replace("-", "_")


# Ticket 78 (pipeline-throughput-architecture ticket 06): bounded worker pool
# for the concurrent submissions bronze-capture batch below. Same bound/
# reasoning as ticket 77's WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY.
_DEFAULT_SUBMISSIONS_FETCH_CONCURRENCY: Final = 5


def _submissions_fetch_concurrency() -> int:
    raw = os.environ.get(
        "WAREHOUSE_SUBMISSIONS_FETCH_CONCURRENCY", str(_DEFAULT_SUBMISSIONS_FETCH_CONCURRENCY)
    )
    return max(1, int(raw))


def _dispatch_to_worker_pool(
    items: list[Any],
    worker_count_hint: int,
    fn: "Callable[[Any], dict[str, Any]]",
    *,
    on_complete: "Callable[[], None] | None" = None,
) -> tuple[dict[Any, dict[str, Any]], dict[Any, BaseException]]:
    """Run ``fn`` over ``items`` on a bounded thread pool, keyed by item.

    ``fn`` must do network I/O + storage writes only -- no db access (a
    single SilverDatabase DuckDB connection is not safe for concurrent use,
    ticket 03). ``on_complete`` runs on the main thread (inside
    ``as_completed``'s iteration), never on a worker thread.
    """
    results: dict[Any, dict[str, Any]] = {}
    errors: dict[Any, BaseException] = {}
    if not items:
        return results, errors
    worker_count = min(len(items), worker_count_hint)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_item = {executor.submit(fn, item): item for item in items}
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                results[item] = future.result()
            except BaseException as exc:  # noqa: BLE001 -- re-raised by the caller, want the original type
                errors[item] = exc
            else:
                if on_complete is not None:
                    on_complete()
    return results, errors


def _capture_submission_bronze_snapshots(
    *,
    context: WarehouseCommandContext,
    db: "SilverDatabase",
    ciks: list[int],
    include_pagination: bool,
    fetch_date: date,
    force: bool,
    on_progress: "Callable[[int], None] | None" = None,
) -> list[dict[str, Any]]:
    """Capture bronze submissions snapshots for every CIK, running real SEC
    fetches through a bounded worker pool instead of one CIK at a time.

    Ticket 78 (pipeline-throughput-architecture ticket 06): this is the
    shared function behind all 5 SEC-fetching commands
    (daily_incremental/bootstrap/bootstrap_full/targeted_resync/
    bootstrap_batch), replacing the sequential per-CIK loop that was
    daily-incremental's single biggest measured cost after the artifact-fetch
    loop (ticket 01: 48.3min / 10,491 CIKs at 1 SEC call/CIK).

    Two-wave shape, since a CIK's pagination file names aren't known until
    its main submissions payload is in hand:
      wave 0 (main thread): cache-check every CIK's submissions_main.
      wave 1 (pool): fetch the cache misses -- network + bronze write only.
      wave 2, only if include_pagination: cache-check every CIK's pagination
        files (main thread), then fetch the misses through the pool,
        flattened across all CIKs rather than nested per-CIK, to maximize
        concurrency for heavy filers too.
    Results are assembled back into ``ciks`` order regardless of completion
    order, so callers see an identical shape/order to the old sequential
    implementation.

    Progress (``on_progress``) is driven by wave 0+1 completions, which
    reach ``len(ciks)`` before wave 2 (pagination) begins -- for
    include_pagination=True runs, the terminal 100% marker fires once mains
    are resolved, before pagination fetches finish. Accepted tradeoff:
    daily-incremental (the measured bottleneck this ticket targets) always
    runs with include_pagination=False, so this never applies to it.
    """
    worker_count_hint = _submissions_fetch_concurrency()
    main_progress = 0

    def _bump_main_progress() -> None:
        nonlocal main_progress
        main_progress += 1
        if on_progress is not None:
            on_progress(main_progress)

    main_cache_by_cik: dict[int, dict[str, Any]] = {}
    pending_main_ciks: list[int] = []
    if force:
        pending_main_ciks = list(ciks)
    else:
        # Phase 1 (main thread, DB-only, fast): resolve checkpoint refs for
        # every CIK -- a plain SELECT, must stay single-threaded (SilverDatabase
        # wraps one shared duckdb connection, ticket 03). Phase 2 (worker pool):
        # the actual file read/verify. Ticket 11 follow-up
        # (pipeline-throughput-architecture): this used to run every cache-hit
        # read sequentially on the main thread even though it's pure S3 I/O with
        # no external rate limit -- unlike a genuine SEC fetch there's no reason
        # to serialize it, and bootstrap-batch's --artifact-policy skip guarantees
        # every CIK is a cache hit in exactly the pipeline this cost the most in.
        main_checkpoint_by_cik = {
            cik: _resolve_submissions_main_checkpoint_only(db=db, cik=cik, fetch_date=fetch_date)
            for cik in ciks
        }
        main_cache_results, main_cache_errors = _dispatch_to_worker_pool(
            ciks,
            worker_count_hint,
            lambda cik: _read_submissions_main_cached_payload(
                context=context,
                cik=cik,
                fetch_date=fetch_date,
                checkpoint=main_checkpoint_by_cik[cik],
            ),
        )
        if main_cache_errors:
            first_failed_cik = min(main_cache_errors, key=ciks.index)
            raise main_cache_errors[first_failed_cik]
        for cik in ciks:
            cached = main_cache_results.get(cik)
            if cached is not None:
                main_cache_by_cik[cik] = cached
                _bump_main_progress()
            else:
                pending_main_ciks.append(cik)

    main_fetch_results, main_fetch_errors = _dispatch_to_worker_pool(
        pending_main_ciks,
        worker_count_hint,
        lambda cik: _fetch_submissions_main_snapshot(context=context, cik=cik, fetch_date=fetch_date),
        on_complete=_bump_main_progress,
    )
    if main_fetch_errors:
        first_failed_cik = min(main_fetch_errors, key=ciks.index)
        raise main_fetch_errors[first_failed_cik]

    main_snapshot_by_cik: dict[int, dict[str, Any]] = {**main_cache_by_cik, **main_fetch_results}

    pagination_manifest_by_cik: dict[int, list[str]] = {
        cik: (_pagination_file_names(main_snapshot_by_cik[cik]["payload"]) if include_pagination else [])
        for cik in ciks
    }

    pagination_cache_by_key: dict[tuple[int, str], dict[str, Any]] = {}
    pending_pagination_keys: list[tuple[int, str]] = []
    all_pagination_keys = [
        (cik, file_name) for cik in ciks for file_name in pagination_manifest_by_cik[cik]
    ]
    if force:
        pending_pagination_keys = list(all_pagination_keys)
    else:
        # Same checkpoint/read split as the main-submissions wave above (ticket
        # 11 follow-up).
        pagination_checkpoint_by_key = {
            key: _resolve_submissions_pagination_checkpoint_only(
                db=db, cik=key[0], file_name=key[1], fetch_date=fetch_date,
            )
            for key in all_pagination_keys
        }
        pagination_cache_results, pagination_cache_errors = _dispatch_to_worker_pool(
            all_pagination_keys,
            worker_count_hint,
            lambda key: _read_submissions_pagination_cached_payload(
                context=context,
                cik=key[0],
                file_name=key[1],
                fetch_date=fetch_date,
                checkpoint=pagination_checkpoint_by_key[key],
            ),
        )
        if pagination_cache_errors:
            first_failed_key = min(pagination_cache_errors, key=all_pagination_keys.index)
            raise pagination_cache_errors[first_failed_key]
        for key in all_pagination_keys:
            cached = pagination_cache_results.get(key)
            if cached is not None:
                pagination_cache_by_key[key] = cached
            else:
                pending_pagination_keys.append(key)

    pagination_fetch_results, pagination_fetch_errors = _dispatch_to_worker_pool(
        pending_pagination_keys,
        worker_count_hint,
        lambda key: _fetch_submissions_pagination_snapshot(
            context=context, cik=key[0], file_name=key[1], fetch_date=fetch_date
        ),
    )
    if pagination_fetch_errors:
        first_failed_key = min(pagination_fetch_errors, key=all_pagination_keys.index)
        raise pagination_fetch_errors[first_failed_key]

    pagination_snapshot_by_key: dict[tuple[int, str], dict[str, Any]] = {
        **pagination_cache_by_key,
        **pagination_fetch_results,
    }

    snapshots: list[dict[str, Any]] = []
    for cik in ciks:
        main_snapshot = main_snapshot_by_cik[cik]
        raw_writes = [main_snapshot["write_record"]]
        manifest_file_names = pagination_manifest_by_cik[cik]
        pagination_snapshots: list[dict[str, Any]] = []
        for file_name in manifest_file_names:
            snapshot = pagination_snapshot_by_key[(cik, file_name)]
            pagination_snapshots.append(
                {
                    "file_name": file_name,
                    "payload": snapshot["payload"],
                    "write_record": snapshot["write_record"],
                }
            )
            raw_writes.append(snapshot["write_record"])
        snapshots.append(
            {
                "cik": cik,
                "include_pagination": include_pagination,
                "main_payload": main_snapshot["payload"],
                "main_write_record": main_snapshot["write_record"],
                "manifest_file_names": manifest_file_names,
                "pagination_snapshots": pagination_snapshots,
                "raw_writes": raw_writes,
            }
        )
    return snapshots


def _apply_submission_snapshot_to_silver(
    *,
    db: SilverDatabase,
    sync_run_id: str,
    snapshot: dict[str, Any],
    force: bool,
    load_mode: str,
    recent_limit: int | None,
    now: datetime,
    filing_min_date: date | None = None,
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
        recent_rows = filter_rows_by_min_filing_date(
            stage_recent_filing_loader(
                main_payload,
                cik,
                sync_run_id,
                main_write_record["sha256"],
                load_mode,
                recent_limit=recent_limit,
            ),
            filing_min_date,
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
            filing_min_date=filing_min_date,
        )
        rows_written += int(result["rows_written"])

    # Unfiltered by filing_min_date on purpose -- company_sync_state's
    # latest_filing_date_seen/latest_acceptance_datetime_seen must reflect
    # the company's true most-recent filing regardless of the discovery
    # lookback window, not the filtered view. stage_recent_filing_loader is
    # a pure function of main_payload, so recomputing it fresh here (rather
    # than reusing result["recent_rows"], which may have been lookback-
    # filtered) costs nothing extra -- no I/O, no re-fetch.
    all_filing_rows = list(
        stage_recent_filing_loader(
            main_payload, cik, sync_run_id, main_write_record["sha256"], load_mode,
            recent_limit=recent_limit,
        )
    )
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
    elif tracking_status not in {"active", "paused", "historical_complete", "error", "deregistered"}:
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
    filtered_pagination_accessions = _dedupe_strings(
        [
            row["accession_number"]
            for row in filter_rows_by_min_filing_date(pagination_rows_for_accessions, filing_min_date)
            if row.get("accession_number")
        ]
    )
    filtered_by_lookback_count = 0
    if filing_min_date is not None:
        unfiltered_count = len({
            row["accession_number"] for row in all_filing_rows if row.get("accession_number")
        })
        kept_count = len(set(result["recent_accessions"]) | set(filtered_pagination_accessions))
        filtered_by_lookback_count = max(0, unfiltered_count - kept_count)
    return {
        "raw_writes": raw_writes,
        "rows_written": rows_written,
        "rows_skipped": rows_skipped,
        "recent_accessions": _dedupe_strings(result["recent_accessions"]),
        "pagination_accessions": filtered_pagination_accessions,
        "filtered_by_lookback_count": filtered_by_lookback_count,
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
    reference_snapshot_identity: dict[str, str] | None = None
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
        if spec.source_name == "company_tickers":
            reference_snapshot_identity = {
                "source_name": spec.source_name,
                "sha256": str(write_record["sha256"]),
                "path": str(write_record["path"]),
            }
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
            db.seed_company_sync_state_bulk([int(row["cik"]) for row in rows])

    return {
        "raw_writes": raw_writes,
        "rows_written": rows_written,
        "rows_skipped": rows_skipped,
        "seed_document": seed_document,
        "reference_snapshot_identity": reference_snapshot_identity,
    }



def _write_cik_universe_batches(
    context: WarehouseCommandContext,
    rows: list[dict[str, Any]],
    fetch_date: date,
    sync_run_id: str,
    batch_size: int = 100,
    shard_aware: bool = False,
) -> str:
    """Write the CIK universe as pre-batched JSON Lines to the bronze root.

    Each line is {"cik_list": "cik1,cik2,..."} for use by the Distributed Map
    bootstrap-batch iterator.

    Path uses run_id only (no date component) so the Step Function can construct
    the key deterministically from $$.Execution.Name without date extraction.

    ``shard_aware`` (ticket 12, pipeline-throughput-architecture): when True,
    split ``rows`` by shard band first and round-robin interleave each
    shard's batches before writing, so consecutive lines cycle across shard
    files instead of exhausting one shard before touching the next -- lets a
    Distributed Map's concurrent slots land on different shard files rather
    than repeatedly racing the same one. Only the ``seed-bronze-batches``
    caller opts in; the other callers of this function have their own
    ordering dependents (e.g. a downstream reducer that re-derives the same
    batch boundaries) and must keep today's plain ascending-order behavior.
    Falls back to plain ascending batching -- identical to ``shard_aware=False``
    -- when remote storage isn't in use or no shard manifest exists yet,
    mirroring the read-side fallback (``shard_manifest_missing_monolith_fallback``).

    Returns the full S3/local path to the JSON Lines file.
    """
    relative_path = default_capture_spec_factory().cik_universe_batches(sync_run_id).relative_path
    ciks = [str(row["cik"]) for row in rows]

    per_shard_ciks = _shard_partition_ciks(context, ciks) if shard_aware else None
    if per_shard_ciks is None:
        batches = [ciks[i : i + batch_size] for i in range(0, len(ciks), batch_size)]
    else:
        per_shard_batches = [
            [shard_ciks[i : i + batch_size] for i in range(0, len(shard_ciks), batch_size)]
            for shard_ciks in per_shard_ciks
        ]
        batches = _interleave_round_robin(per_shard_batches)

    lines = [json.dumps({"cik_list": ",".join(batch)}) for batch in batches]
    content = "\n".join(lines) + ("\n" if lines else "")
    return context.bronze_root.write_text(relative_path, content)


def _shard_partition_ciks(
    context: WarehouseCommandContext, ciks: list[str]
) -> list[list[str]] | None:
    """Split ``ciks`` (already sorted ascending) into per-shard sublists.

    Returns None -- caller should fall back to plain ascending batching --
    when remote storage isn't in use or no shard manifest exists yet.
    Ordering within each shard's sublist is preserved (still ascending),
    only the shard-to-shard grouping changes.
    """
    if not context.storage_root.is_remote:
        return None

    from edgar_warehouse.application.sharding.shard_manifest import band_for_cik

    try:
        manifest = _read_shard_manifest(context)
    except (FileNotFoundError, OSError):
        _emit_pipeline_event(
            "shard_manifest_missing_monolith_fallback",
            command="seed-bronze-batches",
        )
        return None

    shard_count = int(manifest["shard_count"])
    per_shard_ciks: list[list[str]] = [[] for _ in range(shard_count)]
    for cik in ciks:
        shard_index = band_for_cik(manifest, int(cik))
        per_shard_ciks[shard_index].append(cik)
    return per_shard_ciks


def _interleave_round_robin(per_shard_batches: list[list[list[str]]]) -> list[list[str]]:
    """Round-robin flatten per-shard batch lists (ticket 12): shard0-batch1,
    shard1-batch1, ..., shard0-batch2, ... A shard whose batches are
    exhausted is simply skipped in later rounds -- no special-casing needed.
    """
    result: list[list[str]] = []
    max_len = max((len(shard_batches) for shard_batches in per_shard_batches), default=0)
    for round_index in range(max_len):
        for shard_batches in per_shard_batches:
            if round_index < len(shard_batches):
                result.append(shard_batches[round_index])
    return result


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


def _resolve_submissions_main_cached_snapshot(
    *,
    context: WarehouseCommandContext,
    db: "SilverDatabase",
    cik: int,
    fetch_date: date,
) -> "dict[str, Any] | None":
    """Cache-check only (db + storage reads, no network).

    Ticket 78: split out of ``_capture_submissions_main`` so the concurrent
    batch capture (``_capture_submission_bronze_snapshots``) can resolve
    cache hits sequentially on the main thread before dispatching real
    fetches to a worker pool.
    """
    capture_spec = default_capture_spec_factory().submissions_main(cik, fetch_date)

    # Idempotency: consult the silver checkpoint before hitting the SEC API.
    # If force=False and the bronze file we wrote last time is still intact,
    # reuse it.  This prevents duplicate bronze files across bootstrap re-runs
    # and eliminates redundant SEC API calls for data that hasn't changed.
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
    return _read_bronze_by_glob_if_present(
        bronze_root=context.bronze_root,
        source_name=capture_spec.source_name,
        source_url=capture_spec.source_url or "",
        relative_glob=default_path_resolver().submissions_main_glob(cik),
        cik=cik,
    )


def _resolve_submissions_main_checkpoint_only(
    *,
    db: "SilverDatabase",
    cik: int,
    fetch_date: date,
) -> "tuple[str, str] | None":
    """DB-only half of the main-submissions cache check (ticket 11 follow-up,
    pipeline-throughput-architecture): a single checkpoint SELECT. Must stay on
    the main thread -- ``SilverDatabase`` wraps one shared duckdb connection that
    is not safe for concurrent use (ticket 03). Returns (bronze_path, last_sha256)
    or None; the actual file read/verify is done separately in
    ``_read_submissions_main_cached_payload`` so it can run in the worker pool.
    """
    capture_spec = default_capture_spec_factory().submissions_main(cik, fetch_date)
    checkpoint = db.get_source_checkpoint(capture_spec.source_name, f"cik:{cik}")
    if checkpoint is None:
        return None
    bronze_path: str | None = checkpoint.get("bronze_path")
    last_sha256: str | None = checkpoint.get("last_sha256")
    if not bronze_path or not last_sha256:
        return None
    return (bronze_path, last_sha256)


def _read_submissions_main_cached_payload(
    *,
    context: WarehouseCommandContext,
    cik: int,
    fetch_date: date,
    checkpoint: "tuple[str, str] | None",
) -> "dict[str, Any] | None":
    """I/O-only: read+verify a pre-resolved checkpoint, or fall back to a glob
    search. No ``db`` access -- safe to run concurrently, unlike the checkpoint
    lookup itself (ticket 11 follow-up). Mirrors
    ``_resolve_submissions_main_cached_snapshot``'s checkpoint-then-glob order.
    """
    capture_spec = default_capture_spec_factory().submissions_main(cik, fetch_date)
    if checkpoint is not None:
        bronze_path, last_sha256 = checkpoint
        cached = _read_bronze_by_checkpoint(
            bronze_path=bronze_path,
            last_sha256=last_sha256,
            source_name=capture_spec.source_name,
            source_url=capture_spec.source_url or "",
            relative_path=capture_spec.relative_path,
            cik=cik,
        )
        if cached is not None:
            return cached
    return _read_bronze_by_glob_if_present(
        bronze_root=context.bronze_root,
        source_name=capture_spec.source_name,
        source_url=capture_spec.source_url or "",
        relative_glob=default_path_resolver().submissions_main_glob(cik),
        cik=cik,
    )


def _fetch_submissions_main_snapshot(
    *,
    context: WarehouseCommandContext,
    cik: int,
    fetch_date: date,
) -> dict[str, Any]:
    """Network fetch + bronze write only -- no db access.

    Ticket 78: safe to run on a worker thread.
    """
    capture_spec = default_capture_spec_factory().submissions_main(cik, fetch_date)
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


def _capture_submissions_main(
    *,
    context: WarehouseCommandContext,
    db: "SilverDatabase",
    cik: int,
    fetch_date: date,
    force: bool,
) -> dict[str, Any]:
    if not force:
        cached = _resolve_submissions_main_cached_snapshot(
            context=context, db=db, cik=cik, fetch_date=fetch_date
        )
        if cached is not None:
            return cached
    return _fetch_submissions_main_snapshot(context=context, cik=cik, fetch_date=fetch_date)


def _resolve_submissions_pagination_cached_snapshot(
    *,
    context: WarehouseCommandContext,
    db: "SilverDatabase",
    cik: int,
    file_name: str,
    fetch_date: date,
) -> "dict[str, Any] | None":
    """Cache-check only (db + storage reads, no network). See
    ``_resolve_submissions_main_cached_snapshot`` (ticket 78)."""
    capture_spec = default_capture_spec_factory().submissions_pagination(cik, file_name, fetch_date)
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
    return _read_bronze_by_glob_if_present(
        bronze_root=context.bronze_root,
        source_name=capture_spec.source_name,
        source_url=capture_spec.source_url or "",
        relative_glob=default_path_resolver().submissions_pagination_glob(cik, file_name),
        cik=cik,
    )


def _resolve_submissions_pagination_checkpoint_only(
    *,
    db: "SilverDatabase",
    cik: int,
    file_name: str,
    fetch_date: date,
) -> "tuple[str, str] | None":
    """DB-only half of the pagination cache check. See
    ``_resolve_submissions_main_checkpoint_only`` (ticket 11 follow-up)."""
    capture_spec = default_capture_spec_factory().submissions_pagination(cik, file_name, fetch_date)
    checkpoint = db.get_source_checkpoint(capture_spec.source_name, f"file:{file_name}")
    if checkpoint is None:
        return None
    bronze_path: str | None = checkpoint.get("bronze_path")
    last_sha256: str | None = checkpoint.get("last_sha256")
    if not bronze_path or not last_sha256:
        return None
    return (bronze_path, last_sha256)


def _read_submissions_pagination_cached_payload(
    *,
    context: WarehouseCommandContext,
    cik: int,
    file_name: str,
    fetch_date: date,
    checkpoint: "tuple[str, str] | None",
) -> "dict[str, Any] | None":
    """I/O-only pagination cache read/glob-fallback. See
    ``_read_submissions_main_cached_payload`` (ticket 11 follow-up)."""
    capture_spec = default_capture_spec_factory().submissions_pagination(cik, file_name, fetch_date)
    if checkpoint is not None:
        bronze_path, last_sha256 = checkpoint
        cached = _read_bronze_by_checkpoint(
            bronze_path=bronze_path,
            last_sha256=last_sha256,
            source_name=capture_spec.source_name,
            source_url=capture_spec.source_url or "",
            relative_path=capture_spec.relative_path,
            cik=cik,
        )
        if cached is not None:
            return cached
    return _read_bronze_by_glob_if_present(
        bronze_root=context.bronze_root,
        source_name=capture_spec.source_name,
        source_url=capture_spec.source_url or "",
        relative_glob=default_path_resolver().submissions_pagination_glob(cik, file_name),
        cik=cik,
    )


def _fetch_submissions_pagination_snapshot(
    *,
    context: WarehouseCommandContext,
    cik: int,
    file_name: str,
    fetch_date: date,
) -> dict[str, Any]:
    """Network fetch + bronze write only -- no db access. See
    ``_fetch_submissions_main_snapshot`` (ticket 78)."""
    capture_spec = default_capture_spec_factory().submissions_pagination(cik, file_name, fetch_date)
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
    if not force:
        cached = _resolve_submissions_pagination_cached_snapshot(
            context=context, db=db, cik=cik, file_name=file_name, fetch_date=fetch_date
        )
        if cached is not None:
            return cached
    return _fetch_submissions_pagination_snapshot(
        context=context, cik=cik, file_name=file_name, fetch_date=fetch_date
    )


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


def _read_bronze_by_checkpoint(
    *,
    bronze_path: str,
    last_sha256: str,
    source_name: str,
    source_url: str,
    relative_path: str,
    cik: int | None = None,
) -> "dict[str, Any] | None":
    """I/O-only half of ``_read_bronze_if_cached``: read+verify an already-resolved
    checkpoint (bronze_path, last_sha256). No ``db`` access, so unlike the checkpoint
    lookup itself this is safe to run concurrently across worker threads (ticket 11
    follow-up: pipeline-throughput-architecture). Returns None on a missing/corrupt file.
    """
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
    return _read_bronze_by_checkpoint(
        bronze_path=bronze_path,
        last_sha256=last_sha256,
        source_name=source_name,
        source_url=source_url,
        relative_path=relative_path,
        cik=cik,
    )


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
            "accession_numbers": [],
            "candidate_rows": [],
            "status": "skipped_non_business_day",
        }

    if not force and existing and existing.get("status") == "succeeded":
        rows = db.get_daily_index_filings(target_date.isoformat())
        return {
            "raw_writes": [],
            "rows_written": 0,
            "rows_skipped": 1,
            "impacted_ciks": _dedupe_ints([int(row["cik"]) for row in rows if row.get("cik") is not None]),
            "accession_numbers": _dedupe_strings(
                [str(row["accession_number"]) for row in rows if row.get("accession_number")]
            ),
            "candidate_rows": _daily_index_candidate_rows(rows),
            "form_15_ciks": _ciks_filing_form15(rows),
            "status": "succeeded",
            # Ticket 05: finalized dates are catalog silver-skips (no network)
            "network_fetches": 0,
            "silver_skips": 1,
            "catalog_silver_skips": 1,
            "catalog_network_fetches": 0,
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
            "accession_numbers": [],
            "candidate_rows": [],
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
            "accession_numbers": _dedupe_strings(
                [str(row["accession_number"]) for row in rows if row.get("accession_number")]
            ),
            "candidate_rows": _daily_index_candidate_rows(rows),
            "form_15_ciks": _ciks_filing_form15(rows),
            "status": "succeeded",
            "network_fetches": 1,
            "silver_skips": 0,
            "catalog_network_fetches": 1,
            "catalog_silver_skips": 0,
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
            "accession_numbers": [],
            "candidate_rows": [],
            "status": "failed_retryable",
        }


def _daily_index_candidate_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return filing metadata sufficient to keep exact index accessions selectable."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        accession = str(row.get("accession_number") or "").strip()
        if not accession or accession in seen:
            continue
        seen.add(accession)
        candidates.append(
            {
                "accession_number": accession,
                "cik": row.get("cik"),
                "form": row.get("form"),
                "filing_date": row.get("filing_date"),
                "report_date": None,
                "items": None,
            }
        )
    return candidates


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
            force=force,
        )
        raw_writes.extend(artifact_result["raw_writes"])
        rows_written += int(artifact_result["attachment_count"])
    if include_text:
        from edgar_warehouse.infrastructure.filing_artifact_service import extract_filing_text

        text_row = extract_filing_text(
            context=context, db=db, accession_number=accession_number, sync_run_id=sync_run_id
        )
        rows_written += 1 if text_row else 0
    if include_parsers:
        rows_written += _run_parse_pipeline(db=db, accession_number=accession_number, sync_run_id=sync_run_id)
    return {"raw_writes": raw_writes, "rows_written": rows_written}


def _run_parse_pipeline(
    *,
    db: SilverDatabase,
    accession_number: str,
    sync_run_id: str,
    fail_closed: bool = False,
) -> int:
    filing = db.get_filing(accession_number)
    if filing is None:
        return 0
    form_type = str(filing.get("form") or "").strip()
    parser_name, parser_version, form_family = _parser_metadata(
        form_type, items=filing.get("items")
    )
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
        # Item 5.02 is integrated into Branch A configured-forms loads so the
        # ownership + employment load share one artifact pass (2y agent window).
        if form_family == "item_502":
            rows_written = _parse_item_502_accession(
                db=db,
                filing=filing,
                accession_number=accession_number,
                sync_run_id=sync_run_id,
            )
            db.complete_parse_run(parse_run_id, status="succeeded", rows_written=rows_written)
            return rows_written
        if form_family == "generic":
            db.complete_parse_run(parse_run_id, status="skipped", rows_written=0)
            if fail_closed:
                raise WarehouseRuntimeError(
                    f"no release parser registered for required accession {accession_number} "
                    f"with form {form_type}"
                )
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
        if fail_closed:
            raise WarehouseRuntimeError(
                f"parser failed for required accession {accession_number}: {exc}"
            ) from exc
        return 0


def _parse_item_502_accession(
    *,
    db: SilverDatabase,
    filing: Mapping[str, Any],
    accession_number: str,
    sync_run_id: str,
) -> int:
    """Parse one Item 5.02 candidate 8-K into sec_employment_event (no SEC calls)."""
    from edgar_warehouse.parsers.item_502 import PARSER_VERSION, parse_item_502

    payload = _read_primary_artifact_bytes(db, accession_number)
    content = payload.decode("utf-8", errors="replace")
    cik = int(filing.get("cik") or 0)
    filing_date = _ownership_filing_date(filing) or date.today()
    result = parse_item_502(
        accession_number=accession_number,
        cik=cik,
        filing_date=filing_date,
        content=content,
    )
    event_rows = [
        {
            "accession_number": event.accession_number,
            "event_index": index,
            "cik": event.cik,
            "event_type": event.event_type,
            "person_name": event.person_name,
            "exec_role": event.role,
            "previous_role": event.previous_role,
            "compensation_amount": event.compensation_amount,
            "effective_date": event.effective_date,
            "parser_version": PARSER_VERSION,
        }
        for index, event in enumerate(result.events, start=1)
    ]
    rows_written = db.merge_employment_events(event_rows, sync_run_id)
    _emit_pipeline_event(
        "item_502_parsed",
        accession_number=accession_number,
        cik=cik,
        applicability=result.applicability,
        reason=result.reason_code,
        events=len(event_rows),
        rows_written=rows_written,
        run_id=sync_run_id,
    )
    return rows_written


def _read_primary_artifact_bytes(db: SilverDatabase, accession_number: str) -> bytes:
    attachments = db.get_filing_attachments(accession_number)
    primary = next((row for row in attachments if row.get("is_primary")), None)
    if primary is None or not primary.get("raw_object_id"):
        raise WarehouseRuntimeError(f"No primary attachment found for accession {accession_number}")
    raw_object = db.get_raw_object(str(primary["raw_object_id"]))
    if raw_object is None:
        raise WarehouseRuntimeError(f"Missing raw object for accession {accession_number}")
    return read_bytes(str(raw_object["storage_path"]))


def _parser_metadata(form_type: str, items: Any = None) -> tuple[str, str, str]:
    if form_type in OWNERSHIP_FORMS:
        module = importlib.import_module("edgar_warehouse.parsers.ownership")
        return str(module.PARSER_NAME), str(module.PARSER_VERSION), "ownership"
    if form_type in ADV_FORMS:
        module = importlib.import_module("edgar_warehouse.parsers.adv")
        return str(module.PARSER_NAME), str(module.PARSER_VERSION), "adv"
    if _is_item_502_candidate_form(form_type, items):
        module = importlib.import_module("edgar_warehouse.parsers.item_502")
        return str(module.PARSER_NAME), str(module.PARSER_VERSION), "item_502"
    return "generic_text_v1", "1", "generic"


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
    """Ticket 07: catalog SEC network goes through the edgartools gateway."""
    return _gateway_download_bytes(url, identity)


def _require_cik_list(raw_ciks: Any, command_name: str) -> list[int]:
    if not raw_ciks:
        raise WarehouseRuntimeError(f"{command_name} requires --cik-list or a seeded tracked universe")
    return [_parse_cik(value) for value in raw_ciks]


def _parse_cik(value: Any) -> int:
    return parse_cik(value)


def _get_mdm_tracked_ciks(status_filter: str) -> list[int]:
    """Query MDM for explicit MDM workflows.

    Warehouse pipeline orchestration reads sec_company_sync_state instead.
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

    Retained for explicit MDM workflows; warehouse commands update
    sec_company_sync_state directly.
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
    db: SilverDatabase,
    raw_ciks: Any,
    command_name: str,
    tracking_status_filter: str,
    cik_limit: int | None = None,
    cik_offset: int = 0,
) -> list[int]:
    """Resolve CIKs from silver tracking state. SEC bronze is not consulted for scope.

    Applies deterministic windowing (cik_offset then cik_limit) after silver lookup.
    """
    _validate_window_args(cik_limit, cik_offset)
    if raw_ciks:
        ciks = [_parse_cik(value) for value in raw_ciks]
    else:
        ciks = db.get_tracked_ciks(tracking_status_filter)
        if not ciks:
            raise WarehouseRuntimeError(
                f"{command_name} found no companies with tracking_status='{tracking_status_filter}' "
                "in silver tracking state. Run 'edgar-warehouse seed-universe' first."
            )
    # Apply windowing: offset first, then limit
    ciks = ciks[cik_offset:]
    if cik_limit is not None:
        ciks = ciks[:cik_limit]
    return ciks


def _resolve_reconcile_ciks(
    *,
    db: SilverDatabase,
    raw_ciks: Any,
    sample_limit: int | None,
) -> list[int]:
    ciks = [_parse_cik(value) for value in raw_ciks] if raw_ciks else db.get_tracked_ciks("active")
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


def _filter_ciks_to_universe(impacted_ciks: list[int], *, db: SilverDatabase) -> list[int]:
    """Return only CIKs that are active in silver tracking state.

    Falls through to all impacted_ciks if silver returns an empty active universe
    (cold-start guard so daily-incremental can run before the first seed).
    """
    tracked = db.get_tracked_ciks("active")
    if not tracked:
        return impacted_ciks
    tracked_set = set(tracked)
    return [c for c in impacted_ciks if c in tracked_set]


def _cik_set_digest(ciks: Iterable[int]) -> str:
    """Return a stable digest for an exact ordered CIK set."""
    normalized = ",".join(str(cik) for cik in sorted(set(ciks)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _accession_set_digest(accessions: Iterable[str]) -> str:
    """Return a stable digest for an exact accession set."""
    normalized = ",".join(sorted(set(accessions)))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _seed_silver_tracking_status(
    db: SilverDatabase,
    ciks: list[int],
    *,
    tracking_status: str,
) -> None:
    """Create silver tracking-state rows for newly discovered CIKs.

    Existing rows keep their current status so paused or completed companies are
    not accidentally reactivated by discovery.
    """
    now = datetime.now(UTC)
    for cik in _dedupe_ints(ciks):
        if db.get_company_sync_state(cik) is not None:
            continue
        db.upsert_company_sync_state(
            {
                "cik": cik,
                "tracking_status": tracking_status,
                "last_main_sync_at": now,
                "last_error_message": None,
            }
        )


# Real EDGAR daily-index form-type strings for deregistration (confirmed live
# against https://www.sec.gov/Archives/edgar/daily-index/2026/QTR2/form.*.idx):
# 15-12B/15-12G/15-15D (domestic), 15F-12B/15F-12G/15F-15D (foreign private
# issuer), amendments suffixed "/A". Form 25 (exchange delisting) is
# deliberately NOT included -- seed-universe ticket 03 decided many Form 25
# companies keep filing periodic reports as OTC stocks, so demoting on Form 25
# alone risked losing tracking on companies still actually filing. Form 15 is
# the SEC-recognized end of reporting obligations.
def _ciks_filing_form15(rows: list[dict[str, Any]]) -> list[int]:
    ciks: list[int] = []
    for row in rows:
        form = str(row.get("form") or "").upper()
        if form.startswith("15-") or form.startswith("15F-"):
            cik = row.get("cik")
            if cik is not None:
                ciks.append(int(cik))
    return _dedupe_ints(ciks)


def _demote_deregistered_ciks(db: SilverDatabase, ciks: list[int], now: datetime) -> None:
    """Demote CIKs with a Form 15 deregistration filing (seed-universe ticket
    03). Unlike _seed_silver_tracking_status, this always overwrites --
    upsert_company_sync_state's ON CONFLICT unconditionally sets
    tracking_status, so a company re-registering later would need an explicit
    reactivation path (not built here; out of scope for this ticket)."""
    for cik in _dedupe_ints(ciks):
        db.upsert_company_sync_state(
            {
                "cik": cik,
                "tracking_status": "deregistered",
                "last_main_sync_at": now,
                "last_error_message": None,
            }
        )


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
    registration = acquisition_command_registration(command_name)
    if registration is not None:
        return registration.resolve_scope(
            arguments=arguments,
            now=now,
            silver_root=silver_root,
        )
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

    if command_name == "reconcile-relationship-release":
        return {"candidate_manifest": arguments.get("candidate_manifest")}

    if command_name == "ingest-relationship-sources":
        return {"source_manifest": arguments.get("source_manifest")}

    if command_name == "acquire-identity-refresh-lease":
        return {"mode": arguments.get("mode")}

    if command_name == "release-identity-refresh-lease":
        return {}

    if command_name == "acquire-sec-fetch-lease":
        return {}

    if command_name == "release-sec-fetch-lease":
        return {}

    if command_name == "backfill-mdm-entity-ids":
        # mdm-ahead-of-silver map, Phase B: sweeps every shard uniformly;
        # no meaningful CIK range/date/etc scope to report.
        return {}

    if command_name == "backfill-silver-landing-company-metadata":
        # duckdb-retirement map: one-time full-universe seed; no meaningful
        # CIK range/date/etc scope to report.
        return {}

    if command_name == "fetch-adv-bulk":
        return {
            "dataset_period": arguments.get("dataset_period"),
            "force": bool(arguments.get("force")),
        }

    if command_name == "fetch-firm-roster":
        return {
            "dataset_period": arguments.get("dataset_period"),
            "force": bool(arguments.get("force")),
        }

    if command_name == "bootstrap-fundamentals":
        # Branch B counterpart of bootstrap-batch. CIK list + mode dispatch.
        return {
            "cik_list": arguments.get("cik_list") or [],
            "mode": arguments.get("mode") or "per-filing",
        }

    if command_name == "gold-refresh":
        # Scope is empty — bronze/silver are already complete.
        # _execute_warehouse builds gold because gold-refresh is in SOURCE_EXPORT_COMMANDS.
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

    if command_name == "compute-remaining-batches":
        return {
            "resume_ledger_run_id": arguments.get("resume_ledger_run_id") or "",
        }

    if command_name == "parse-ownership-bronze":
        return {
            "limit": arguments.get("limit"),
            "accession_list": arguments.get("accession_list"),
            "ownership_lookback_years": _resolve_ownership_lookback_years(
                arguments.get("ownership_lookback_years")
            ),
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
            "total_cik_limit": arguments.get("total_cik_limit"),
        }

    if command_name == "compute-identity-refresh-window":
        return {
            "mode": str(arguments.get("mode") or "daily"),
            "lookback_days": int(arguments.get("lookback_days") or 7),
            "batch_size": int(arguments.get("batch_size") or 500),
        }

    if command_name == "reduce-identity-refresh":
        return {
            "run_id": arguments.get("run_id"),
            "max_attempts": int(arguments.get("max_attempts") or 3),
        }

    if command_name == "write-run-summary":
        return {}

    if command_name == "verify-pipeline-run":
        return {
            "run_id": arguments.get("run_id"),
        }

    if command_name == "validate-data-quality":
        return {}

    raise WarehouseRuntimeError(f"Unsupported warehouse command: {command_name}")


def _planned_writes(command_name: str, command_path: str, run_id: str, scope: dict[str, Any]) -> dict[str, str]:
    registration = acquisition_command_registration(command_name)
    if registration is not None:
        return registration.planned_writes(
            command_path=command_path,
            run_id=run_id,
            scope=scope,
        )
    return planned_writes(command_name, command_path, run_id, scope)


def _planned_pipeline_writes(
    *,
    context: WarehouseCommandContext,
    command_name: str,
    command_path: str,
    run_id: str,
    scope: dict[str, Any],
    now: datetime,
    include_snowflake_export_manifest: bool,
    include_gold_manifest: bool,
    shard_index: int | None,
) -> list[dict[str, Any]]:
    writes: list[dict[str, Any]] = []
    for layer, relative_path in _planned_writes_for_publication(
        command_name=command_name,
        command_path=command_path,
        run_id=run_id,
        scope=scope,
        include_gold=include_gold_manifest,
    ).items():
        target = context.bronze_root if layer == "bronze" else context.storage_root
        writes.append(
            {
                "layer": layer,
                "path": target.join(relative_path),
                "relative_path": relative_path,
                "planned": True,
            }
        )

    run_manifest_relative_path = _run_manifest_relative_path(command_path, run_id)
    writes.append(
        {
            "layer": "run_manifest",
            "path": context.bronze_root.join(run_manifest_relative_path),
            "relative_path": run_manifest_relative_path,
            "planned": True,
        }
    )

    if include_snowflake_export_manifest and context.snowflake_export_root is not None:
        export_business_date = _resolve_export_business_date(
            command_name=command_name,
            scope=scope,
            now=now,
        )
        relative_path = _snowflake_export_run_manifest_relative_path(
            workflow_name=command_name.replace("-", "_"),
            business_date=export_business_date,
            run_id=run_id,
        )
        writes.append(
            {
                "layer": "snowflake_export_manifest",
                "path": context.snowflake_export_root.join(relative_path),
                "relative_path": relative_path,
                "planned": True,
            }
        )

    if context.storage_root.is_remote:
        if shard_index is None:
            layer = "silver_database"
            relative_path = "silver/sec/silver.duckdb"
        else:
            layer = "silver_shard"
            relative_path = f"silver/sec/shards/shard-{shard_index}.duckdb"
        writes.append(
            {
                "layer": layer,
                "path": context.storage_root.join(relative_path),
                "relative_path": relative_path,
                "planned": True,
            }
        )

    return writes


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


def _run_manifest_relative_path(command_path: str, run_id: str) -> str:
    return run_manifest_relative_path(command_path, run_id)


def _write_consolidated_run_manifest(
    *,
    context: WarehouseCommandContext,
    command_name: str,
    command_path: str,
    run_id: str,
    arguments: dict[str, Any],
    scope: dict[str, Any],
    now: datetime,
    manifest_writes: list[dict[str, Any]],
    metrics: dict[str, Any] | None = None,
    raw_writes: list[dict[str, Any]] | None = None,
    silver_table_counts: dict[str, int] | None = None,
    gold_row_counts: dict[str, int] | None = None,
    serving_export_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    relative_path = _run_manifest_relative_path(command_path, run_id)
    metrics = metrics or {}
    raw_writes = raw_writes or []
    row_counts = _consolidated_run_row_counts(
        metrics=metrics,
        raw_writes=raw_writes,
        silver_table_counts=silver_table_counts,
        gold_row_counts=gold_row_counts,
        serving_export_counts=serving_export_counts,
    )
    payload = run_manifest(
        command_name=command_name,
        run_id=run_id,
        command_path=command_path,
        arguments=arguments,
        scope=scope,
        now=now,
        runtime_mode=context.runtime_mode,
        environment_name=context.environment_name,
        manifest_writes=manifest_writes,
        row_counts=row_counts,
        layer_row_counts=_consolidated_layer_row_counts(
            row_counts=row_counts,
            silver_table_counts=silver_table_counts,
            gold_row_counts=gold_row_counts,
            serving_export_counts=serving_export_counts,
        ),
    )
    return {
        "layer": "run_manifest",
        "path": context.bronze_root.write_json(relative_path, payload),
        "relative_path": relative_path,
    }


def _consolidated_run_row_counts(
    *,
    metrics: dict[str, Any],
    raw_writes: list[dict[str, Any]],
    silver_table_counts: dict[str, int] | None,
    gold_row_counts: dict[str, int] | None,
    serving_export_counts: dict[str, int] | None,
) -> dict[str, Any]:
    return {
        "gold_row_counts": gold_row_counts or {},
        "raw_write_count": len(raw_writes),
        "rows_inserted": int(metrics.get("rows_inserted", 0) or 0),
        "rows_skipped": int(metrics.get("rows_skipped", 0) or 0),
        "serving_export_row_counts": serving_export_counts or {},
        "silver_table_counts": silver_table_counts or {},
    }


def _consolidated_layer_row_counts(
    *,
    row_counts: dict[str, Any],
    silver_table_counts: dict[str, int] | None,
    gold_row_counts: dict[str, int] | None,
    serving_export_counts: dict[str, int] | None,
) -> dict[str, dict[str, Any]]:
    capture_counts = {
        "rows_inserted": row_counts["rows_inserted"],
        "rows_skipped": row_counts["rows_skipped"],
    }
    return {
        "artifacts": {"raw_write_count": row_counts["raw_write_count"]},
        "bronze": capture_counts,
        "gold": gold_row_counts or {},
        "silver": silver_table_counts or {},
        "snowflake_export": serving_export_counts or {},
        "snowflake_export_manifest": serving_export_counts or {},
        "staging": capture_counts,
    }


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
