"""Warehouse runtime helpers for infrastructure-oriented command execution."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from edgar_warehouse.application.context_builder import build_warehouse_context
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.run_context import WarehouseCommandContext
from edgar_warehouse.domain.policy.calendar import (
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
from edgar_warehouse.domain.policy.scope import (
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
    stage_address_loader,
    stage_company_loader,
    stage_daily_index_filing_loader,
    stage_former_name_loader,
    stage_manifest_loader,
    stage_pagination_filing_loader,
    stage_recent_filing_loader,
)
from edgar_warehouse.reconcile import (
    build_reconcile_findings,
    mark_findings_for_resync,
    mark_findings_resolved,
)
from edgar_warehouse.infrastructure.manifest_service import (
    SNOWFLAKE_EXPORT_TABLES,
    layer_manifest,
    planned_writes,
    snowflake_export_manifest,
    snowflake_export_run_manifest,
    snowflake_export_run_manifest_relative_path,
    snowflake_export_run_manifest_table,
    warehouse_success_message,
)
from edgar_warehouse.infrastructure.sec_client import (
    build_company_tickers_exchange_url as sec_build_company_tickers_exchange_url,
    build_company_tickers_url as sec_build_company_tickers_url,
    build_daily_index_url as sec_build_daily_index_url,
    build_submission_pagination_url as sec_build_submission_pagination_url,
    build_submissions_url as sec_build_submissions_url,
    download_sec_bytes,
)
from edgar_warehouse.infrastructure.storage import StorageLocation, read_bytes
from edgar_warehouse.silver_support.session import open_silver_database, reset_submission_state

if TYPE_CHECKING:
    from edgar_warehouse.silver import SilverDatabase

GOLD_AFFECTING_COMMANDS = {
    "bootstrap-full",
    "bootstrap-recent-10",
    "bootstrap-batch",
    "daily-incremental",
    "targeted-resync",
    "full-reconcile",
}

SNOWFLAKE_EXPORT_COMMANDS = GOLD_AFFECTING_COMMANDS | {"seed-universe"}

WAREHOUSE_RUNTIME_MODES = {
    "bronze_capture",
    "infrastructure_validation",
}

OWNERSHIP_FORMS = {"3", "3/A", "4", "4/A", "5", "5/A"}
ADV_FORMS = {"ADV", "ADV/A", "ADV-E", "ADV-E/A", "ADV-H", "ADV-H/A", "ADV-NR", "ADV-W", "ADV-W/A"}

_DAILY_INDEX_LINE_PATTERN = re.compile(
    r"^.+?\s{2,}(?P<cik>\d{4,10})\s+(?:\d{8}|\d{4}-\d{2}-\d{2})\s+edgar/data/"
)


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
    """Seed the tracked-universe table from a local SEC reference JSON file."""
    try:
        from edgar_warehouse.silver import _parse_company_ticker_rows

        limit = _resolve_seed_limit(getattr(args, "limit", None))
        silver_root = _resolve_seed_silver_root(args)
        source_label, document = _resolve_seed_document(args)
        rows = _parse_company_ticker_rows(document)
        if not rows:
            raise WarehouseRuntimeError(f"No company ticker rows found in {source_label}")
        if limit is not None:
            rows = rows[:limit]

        db = _open_silver_database(StorageLocation(silver_root))
        try:
            rows_seeded = db.seed_tracked_universe_rows(rows)
            tracked_universe_count = db.get_tracked_universe_count()
        finally:
            db.close()
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
                "silver_db_path": str(Path(silver_root) / "silver" / "sec" / "silver.duckdb"),
                "source": source_label,
                "status": "ok",
                "tracked_universe_count": tracked_universe_count,
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
    scope = _resolve_scope(command_name=command_name, arguments=arguments, now=now, silver_root=context.silver_root)
    db = _open_silver_database(context.silver_root)
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
    silver_table_counts: dict[str, int] | None = None
    try:
        raw_writes, metrics = _capture_bronze_raw(
            context=context,
            db=db,
            command_name=command_name,
            arguments=arguments,
            scope=scope,
            now=now,
            sync_run_id=run_id,
        )
        silver_table_counts = db.get_table_counts()
        if context.snowflake_export_root is not None and command_name in GOLD_AFFECTING_COMMANDS:
            from edgar_warehouse.gold import (
                build_gold,
                write_gold_to_snowflake_export,
                write_gold_to_storage,
            )

            gold_tables = build_gold(db)
            gold_row_counts = write_gold_to_storage(gold_tables, context.storage_root, run_id)
            export_business_date = _resolve_export_business_date(command_name=command_name, scope=scope, now=now)
            snowflake_export_counts = write_gold_to_snowflake_export(
                gold_tables,
                context.snowflake_export_root,
                run_id,
                export_business_date,
            )
        db.complete_sync_run(
            run_id,
            status=str(metrics.get("sync_status", "succeeded")),
            rows_inserted=int(metrics.get("rows_inserted", 0) or 0),
            rows_skipped=int(metrics.get("rows_skipped", 0) or 0),
        )
    except Exception as exc:
        db.complete_sync_run(run_id, status="failed", error_message=str(exc))
        raise

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

    ticker_reference_rows = metrics.pop("_ticker_reference_rows", None)
    if (
        context.snowflake_export_root is not None
        and command_name == "seed-universe"
        and ticker_reference_rows is not None
    ):
        from edgar_warehouse.gold import (
            build_ticker_reference_table,
            write_ticker_reference_to_snowflake_export,
        )

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


def _apply_silver_from_submissions(
    db: SilverDatabase,
    sync_run_id: str,
    cik: int,
    raw_object_id: str,
    load_mode: str,
    main_payload: dict[str, Any],
    pagination_payloads: list[tuple[str, dict[str, Any]]],
    recent_limit: int | None = None,
) -> dict[str, Any]:
    """Write silver rows for one company from its parsed submissions JSON payloads."""
    company_rows = stage_company_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
    address_rows = stage_address_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
    former_name_rows = stage_former_name_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
    manifest_rows = stage_manifest_loader(main_payload, cik, sync_run_id, raw_object_id, load_mode)
    recent_rows = stage_recent_filing_loader(
        main_payload, cik, sync_run_id, raw_object_id, load_mode, recent_limit=recent_limit
    )

    reset_submission_state(db, cik)
    rows_written = 0
    rows_written += db.merge_company(company_rows, sync_run_id)
    rows_written += db.merge_addresses(address_rows, sync_run_id)
    rows_written += db.merge_former_names(former_name_rows, sync_run_id)
    rows_written += db.merge_submission_files(manifest_rows, sync_run_id)
    rows_written += db.merge_filings(recent_rows, sync_run_id)

    pagination_accessions: list[str] = []
    for _file_name, pagination_payload in pagination_payloads:
        pagination_rows = stage_pagination_filing_loader(pagination_payload, cik, sync_run_id, raw_object_id, load_mode)
        rows_written += db.merge_filings(pagination_rows, sync_run_id)
        pagination_accessions.extend(
            row["accession_number"]
            for row in pagination_rows
            if row.get("accession_number")
        )
    return {
        "rows_written": rows_written,
        "recent_rows": recent_rows,
        "manifest_rows": manifest_rows,
        "recent_accessions": [
            row["accession_number"]
            for row in recent_rows
            if row.get("accession_number")
        ],
        "pagination_accessions": pagination_accessions,
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
    """Capture and apply bronze/silver workflow state for a warehouse command."""
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
        db.auto_enroll_tracked_universe(impacted_ciks, scope_reason="daily_index")
        impacted_ciks = _filter_ciks_to_universe(impacted_ciks, db)
        selected_ciks = _apply_bronze_cik_limit(impacted_ciks)
        if selected_ciks:
            for cik in selected_ciks:
                result = submissions_orchestrator(
                    context=context,
                    db=db,
                    sync_run_id=sync_run_id,
                    cik=cik,
                    include_pagination=False,
                    fetch_date=now.date(),
                    force=bool(arguments.get("force")),
                    load_mode="daily_incremental",
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

    if command_name == "bootstrap-recent-10":
        ciks = _resolve_target_ciks(
            db=db,
            raw_ciks=scope.get("cik_list"),
            command_name=command_name,
            tracking_status_filter=str(scope.get("tracking_status_filter", "active")),
        )
        for cik in ciks:
            result = submissions_orchestrator(
                context=context,
                db=db,
                sync_run_id=sync_run_id,
                cik=cik,
                include_pagination=False,
                fetch_date=now.date(),
                force=bool(arguments.get("force")),
                load_mode="bootstrap_recent_10",
                recent_limit=arguments.get("recent_limit"),
            )
            raw_writes.extend(result["raw_writes"])
            metrics["rows_inserted"] += result["rows_written"]
            metrics["rows_skipped"] += result["rows_skipped"]
        return raw_writes, metrics

    if command_name == "bootstrap-full":
        ciks = _resolve_target_ciks(
            db=db,
            raw_ciks=scope.get("cik_list"),
            command_name=command_name,
            tracking_status_filter=str(scope.get("tracking_status_filter", "active")),
        )
        for cik in ciks:
            result = submissions_orchestrator(
                context=context,
                db=db,
                sync_run_id=sync_run_id,
                cik=cik,
                include_pagination=True,
                fetch_date=now.date(),
                force=bool(arguments.get("force")),
                load_mode="bootstrap_full",
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
                for accession_number in result["recent_accessions"]:
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
                cik=cik,
                fetch_date=now.date(),
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

    if command_name == "bootstrap-batch":
        cik_list = list(arguments.get("cik_list") or [])
        include_pagination = bool(arguments.get("include_pagination", True))
        for cik in cik_list:
            result = submissions_orchestrator(
                context=context,
                db=db,
                sync_run_id=sync_run_id,
                cik=cik,
                include_pagination=include_pagination,
                fetch_date=now.date(),
                force=bool(arguments.get("force", False)),
                load_mode="bootstrap_batch",
            )
            raw_writes.extend(result["raw_writes"])
            metrics["rows_inserted"] += result["rows_written"]
            metrics["rows_skipped"] += result["rows_skipped"]
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
    """Fetch one submissions main file, stage rowsets, and merge silver state."""
    raw_writes: list[dict[str, Any]] = []
    rows_written = 0
    rows_skipped = 0
    now = datetime.now(UTC)
    existing_state = db.get_company_sync_state(cik) or {"tracking_status": "bootstrap_pending"}

    main_snapshot = _capture_submissions_main(context=context, cik=cik, fetch_date=fetch_date)
    raw_writes.append(main_snapshot["write_record"])
    main_payload = main_snapshot["payload"]
    pagination_payloads: list[tuple[str, dict[str, Any]]] = []
    pagination_write_records: list[dict[str, Any]] = []
    pagination_same = True

    manifest_file_names = _pagination_file_names(main_payload) if include_pagination else []
    for file_name in manifest_file_names:
        pagination_snapshot = _capture_submissions_pagination(
            context=context,
            cik=cik,
            file_name=file_name,
            fetch_date=fetch_date,
        )
        pagination_write_records.append(pagination_snapshot["write_record"])
        raw_writes.append(pagination_snapshot["write_record"])
        pagination_payloads.append((file_name, pagination_snapshot["payload"]))
        checkpoint = db.get_source_checkpoint("submissions_pagination", f"file:{file_name}")
        if force or checkpoint is None or checkpoint.get("last_sha256") != pagination_snapshot["write_record"]["sha256"]:
            pagination_same = False

    main_checkpoint = db.get_source_checkpoint("submissions_main", f"cik:{cik}")
    main_same = (
        (not force)
        and main_checkpoint is not None
        and main_checkpoint.get("last_sha256") == main_snapshot["write_record"]["sha256"]
    )
    all_same = main_same and pagination_same

    for write_record in [main_snapshot["write_record"], *pagination_write_records]:
        source_name = write_record["source_name"]
        source_key = f"cik:{cik}" if source_name == "submissions_main" else f"file:{Path(write_record['relative_path']).name}"
        db.upsert_source_checkpoint(
            {
                "source_name": source_name,
                "source_key": source_key,
                "raw_object_id": write_record["sha256"],
                "last_success_at": now,
                "last_sha256": write_record["sha256"],
            }
        )

    result: dict[str, Any]
    if all_same:
        rows_skipped = 1 + len(pagination_payloads)
        recent_rows = stage_recent_filing_loader(
            main_payload,
            cik,
            sync_run_id,
            main_snapshot["write_record"]["sha256"],
            load_mode,
            recent_limit=recent_limit,
        )
        result = {
            "rows_written": 0,
            "recent_rows": recent_rows,
            "manifest_rows": stage_manifest_loader(main_payload, cik, sync_run_id, main_snapshot["write_record"]["sha256"], load_mode),
            "recent_accessions": [
                row["accession_number"]
                for row in recent_rows
                if row.get("accession_number")
            ],
            "pagination_accessions": [],
        }
    else:
        result = _apply_silver_from_submissions(
            db=db,
            sync_run_id=sync_run_id,
            cik=cik,
            raw_object_id=main_snapshot["write_record"]["sha256"],
            load_mode=load_mode,
            main_payload=main_payload,
            pagination_payloads=pagination_payloads,
            recent_limit=recent_limit,
        )
        rows_written += int(result["rows_written"])

    all_filing_rows = list(result["recent_rows"])
    for _file_name, pagination_payload in pagination_payloads:
        all_filing_rows.extend(
            stage_pagination_filing_loader(
                pagination_payload,
                cik,
                sync_run_id,
                main_snapshot["write_record"]["sha256"],
                load_mode,
            )
        )

    latest_filing_date = _latest_filing_date(all_filing_rows)
    latest_acceptance_datetime = _latest_acceptance_datetime(all_filing_rows)
    pagination_files_expected = len(manifest_file_names)
    pagination_files_loaded = len(manifest_file_names) if include_pagination else 0
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
            "last_main_raw_object_id": main_snapshot["write_record"]["sha256"],
            "last_main_sha256": main_snapshot["write_record"]["sha256"],
            "latest_filing_date_seen": latest_filing_date,
            "latest_acceptance_datetime_seen": latest_acceptance_datetime,
            "pagination_files_expected": pagination_files_expected if include_pagination else 0,
            "pagination_files_loaded": pagination_files_loaded if include_pagination else 0,
            "pagination_completed_at": pagination_completed_at,
            "next_sync_after": now + timedelta(days=1),
            "last_error_message": None,
        }
    )
    return {
        "raw_writes": raw_writes,
        "rows_written": rows_written,
        "rows_skipped": rows_skipped,
        "recent_accessions": _dedupe_strings(result["recent_accessions"]),
        "pagination_accessions": _dedupe_strings(result["pagination_accessions"]),
    }


def _sync_reference_data(
    *,
    context: WarehouseCommandContext,
    db: SilverDatabase,
    sync_run_id: str,
    fetch_date: date,
    source_names: list[str] | None = None,
) -> dict[str, Any]:
    selected_sources = source_names or ["company_tickers", "company_tickers_exchange"]
    day_parts = fetch_date.strftime("%Y/%m/%d")
    raw_writes: list[dict[str, Any]] = []
    rows_written = 0
    rows_skipped = 0
    seed_document: dict[str, Any] | None = None
    now = datetime.now(UTC)

    definitions = {
        "company_tickers": (
            _build_company_tickers_url(),
            f"reference/sec/company_tickers/{day_parts}/company_tickers.json",
        ),
        "company_tickers_exchange": (
            _build_company_tickers_exchange_url(),
            f"reference/sec/company_tickers_exchange/{day_parts}/company_tickers_exchange.json",
        ),
    }

    for source_name in selected_sources:
        if source_name not in definitions:
            raise WarehouseRuntimeError(f"Unsupported reference scope_key: {source_name}")
        source_url, relative_path = definitions[source_name]
        payload = _download_sec_bytes(url=source_url, identity=context.identity)
        write_record = _write_bronze_object(
            context=context,
            relative_path=relative_path,
            source_name=source_name,
            source_url=source_url,
            payload=payload,
        )
        raw_writes.append(write_record)
        document = _decode_json_bytes(payload, source_url)
        from edgar_warehouse.silver import _parse_company_ticker_rows

        rows = _parse_company_ticker_rows(document)
        checkpoint = db.get_source_checkpoint(source_name, "global")
        if checkpoint and checkpoint.get("last_sha256") == write_record["sha256"]:
            rows_skipped += 1
        else:
            rows_written += db.replace_company_tickers(rows, sync_run_id, source_name=source_name)
        db.upsert_source_checkpoint(
            {
                "source_name": source_name,
                "source_key": "global",
                "raw_object_id": write_record["sha256"],
                "last_success_at": now,
                "last_sha256": write_record["sha256"],
            }
        )
        if rows and (source_name == "company_tickers_exchange" or seed_document is None):
            seed_document = document
        for row in rows:
            existing = db.get_company_sync_state(int(row["cik"]))
            db.upsert_company_sync_state(
                {
                    "cik": int(row["cik"]),
                    "tracking_status": existing.get("tracking_status", "bootstrap_pending") if existing else "bootstrap_pending",
                    "last_error_message": None,
                }
            )

    if seed_document is not None:
        db.seed_tracked_universe(seed_document)
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
    relative_path = f"reference/cik_universe/runs/{sync_run_id}/cik_batches.jsonl"
    lines = []
    ciks = [str(row["cik"]) for row in rows]
    for i in range(0, len(ciks), batch_size):
        batch = ciks[i : i + batch_size]
        lines.append(json.dumps({"cik_list": ",".join(batch)}))
    content = "\n".join(lines) + ("\n" if lines else "")
    return context.bronze_root.write_text(relative_path, content)


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
    cik: int,
    fetch_date: date,
) -> dict[str, Any]:
    day_parts = fetch_date.strftime("%Y/%m/%d")
    main_file_name = f"CIK{cik:010d}.json"
    main_url = _build_submissions_url(cik)
    main_payload_bytes = _download_sec_bytes(url=main_url, identity=context.identity)
    write_record = _write_bronze_object(
        context=context,
        relative_path=f"submissions/sec/cik={cik}/main/{day_parts}/{main_file_name}",
        source_name="submissions_main",
        source_url=main_url,
        payload=main_payload_bytes,
        cik=cik,
    )
    return {
        "payload": _decode_json_bytes(main_payload_bytes, main_url),
        "write_record": write_record,
    }


def _capture_submissions_pagination(
    *,
    context: WarehouseCommandContext,
    cik: int,
    file_name: str,
    fetch_date: date,
) -> dict[str, Any]:
    day_parts = fetch_date.strftime("%Y/%m/%d")
    pagination_url = _build_submission_pagination_url(file_name)
    payload_bytes = _download_sec_bytes(url=pagination_url, identity=context.identity)
    write_record = _write_bronze_object(
        context=context,
        relative_path=f"submissions/sec/cik={cik}/pagination/{day_parts}/{file_name}",
        source_name="submissions_pagination",
        source_url=pagination_url,
        payload=payload_bytes,
        cik=cik,
    )
    return {
        "payload": _decode_json_bytes(payload_bytes, pagination_url),
        "write_record": write_record,
    }


def _capture_reconcile_snapshot(
    *,
    context: WarehouseCommandContext,
    cik: int,
    fetch_date: date,
) -> dict[str, Any]:
    snapshot = _capture_submissions_main(context=context, cik=cik, fetch_date=fetch_date)
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
    source_url = _build_daily_index_url(target_date)
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
        payload = _download_sec_bytes(url=source_url, identity=context.identity)
        date_parts = target_date.strftime("%Y/%m/%d")
        file_name = f"form.{target_date:%Y%m%d}.idx"
        write_record = _write_bronze_object(
            context=context,
            relative_path=f"daily_index/sec/{date_parts}/{file_name}",
            source_name="daily_index",
            source_url=source_url,
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
        from edgar_warehouse.infrastructure.artifact_service import refresh_filing_artifacts

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
        from edgar_warehouse.infrastructure.artifact_service import extract_filing_text

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
    day_parts = fetch_date.strftime("%Y/%m/%d")
    sources = (
        (
            "company_tickers",
            _build_company_tickers_url(),
            f"reference/sec/company_tickers/{day_parts}/company_tickers.json",
        ),
        (
            "company_tickers_exchange",
            _build_company_tickers_exchange_url(),
            f"reference/sec/company_tickers_exchange/{day_parts}/company_tickers_exchange.json",
        ),
    )
    return [
        _write_bronze_object(
            context=context,
            relative_path=relative_path,
            source_name=source_name,
            source_url=source_url,
            payload=_download_sec_bytes(url=source_url, identity=context.identity),
        )
        for source_name, source_url, relative_path in sources
    ]


def _capture_daily_index_file(context: WarehouseCommandContext, target_date: date) -> tuple[dict[str, Any], list[int]]:
    date_parts = target_date.strftime("%Y/%m/%d")
    file_name = f"form.{target_date:%Y%m%d}.idx"
    source_url = _build_daily_index_url(target_date)
    payload = _download_sec_bytes(url=source_url, identity=context.identity)
    record = _write_bronze_object(
        context=context,
        relative_path=f"daily_index/sec/{date_parts}/{file_name}",
        source_name="daily_index",
        source_url=source_url,
        payload=payload,
        business_date=target_date.isoformat(),
    )
    return record, _extract_impacted_ciks_from_daily_index(payload=payload, source_url=source_url)


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
    day_parts = fetch_date.strftime("%Y/%m/%d")
    raw_writes: list[dict[str, Any]] = []
    silver_staging: list[tuple[int, str, dict[str, Any], list[tuple[str, dict[str, Any]]]]] = []

    for cik in ciks:
        main_file_name = f"CIK{cik:010d}.json"
        main_url = _build_submissions_url(cik)
        main_payload_bytes = _download_sec_bytes(url=main_url, identity=context.identity)
        write_record = _write_bronze_object(
            context=context,
            relative_path=f"submissions/sec/cik={cik}/main/{day_parts}/{main_file_name}",
            source_name="submissions_main",
            source_url=main_url,
            payload=main_payload_bytes,
            cik=cik,
        )
        raw_writes.append(write_record)
        raw_object_id = write_record["sha256"]
        main_document = _decode_json_bytes(main_payload_bytes, main_url)
        pagination_payloads: list[tuple[str, dict[str, Any]]] = []

        if include_pagination:
            for file_name in _pagination_file_names(main_document):
                pagination_url = _build_submission_pagination_url(file_name)
                pagination_payload_bytes = _download_sec_bytes(url=pagination_url, identity=context.identity)
                raw_writes.append(
                    _write_bronze_object(
                        context=context,
                        relative_path=f"submissions/sec/cik={cik}/pagination/{day_parts}/{file_name}",
                        source_name="submissions_pagination",
                        source_url=pagination_url,
                        payload=pagination_payload_bytes,
                        cik=cik,
                    )
                )
                pagination_payloads.append((file_name, _decode_json_bytes(pagination_payload_bytes, pagination_url)))

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


def _build_company_tickers_url() -> str:
    return sec_build_company_tickers_url()


def _build_company_tickers_exchange_url() -> str:
    return sec_build_company_tickers_exchange_url()


def _build_daily_index_url(target_date: date) -> str:
    return sec_build_daily_index_url(target_date)


def _build_submissions_url(cik: int) -> str:
    return sec_build_submissions_url(cik)


def _build_submission_pagination_url(file_name: str) -> str:
    return sec_build_submission_pagination_url(file_name)


def _sec_base_url() -> str:
    return os.environ.get("EDGAR_BASE_URL", "https://www.sec.gov").rstrip("/")


def _sec_data_url() -> str:
    return os.environ.get("EDGAR_DATA_URL", "https://data.sec.gov").rstrip("/")


def _sec_archive_url() -> str:
    return f"{_sec_base_url()}/Archives/edgar"


def _require_cik_list(raw_ciks: Any, command_name: str) -> list[int]:
    if not raw_ciks:
        raise WarehouseRuntimeError(f"{command_name} requires --cik-list or a seeded tracked universe")
    return [_parse_cik(value) for value in raw_ciks]


def _parse_cik(value: Any) -> int:
    return parse_cik(value)


def _resolve_target_ciks(
    *,
    db: SilverDatabase,
    raw_ciks: Any,
    command_name: str,
    tracking_status_filter: str,
) -> list[int]:
    if raw_ciks:
        return [_parse_cik(value) for value in raw_ciks]
    ciks = db.get_tracked_universe_ciks(status_filter=tracking_status_filter)
    if ciks:
        return ciks
    raise WarehouseRuntimeError(f"{command_name} requires --cik-list or a seeded tracked universe")


def _resolve_reconcile_ciks(
    *,
    db: SilverDatabase,
    raw_ciks: Any,
    sample_limit: int | None,
) -> list[int]:
    ciks = [_parse_cik(value) for value in raw_ciks] if raw_ciks else db.get_tracked_universe_ciks(status_filter="active")
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


def _filter_ciks_to_universe(impacted_ciks: list[int], db: "SilverDatabase | None") -> list[int]:
    """Return only CIKs that are in the active tracked universe.

    Falls through to all impacted_ciks if the universe is empty (cold-start)
    or if db is None (remote storage).
    """
    if db is None:
        return impacted_ciks
    tracked = db.get_tracked_universe_ciks(status_filter="active")
    if not tracked:
        return impacted_ciks  # cold-start: empty universe, pass all through
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
    if command_name == "bootstrap-recent-10":
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
