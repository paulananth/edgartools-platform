"""bootstrap-fundamentals command — Branch B silver ingestion.

This command is the Branch B counterpart of ``bootstrap-batch``/``bootstrap-next``
(Branch A).  Each Distributed/inline Map iteration calls this command with a
specific CIK batch (or window) and mode.

Modes
-----
per-filing   Process 8-K earnings releases + DEF 14A proxy filings from bronze.
             Output: sec_earnings_release, sec_executive_record.
             Reads filing/attachment/raw-object metadata from Branch A's ownership
             silver (see source reader below) — in ``load_history`` this mode runs
             AFTER Branch A completes, not concurrently, so that data exists.

entity-facts Fetch SEC companyfacts API for each CIK. No Branch A dependency — calls
             SEC directly via the shared SEC client. In ``load_history`` this mode
             still runs after Branch A because all Branch B modes publish the same
             canonical silver DuckDB artifact.
             Output: sec_financial_fact, sec_accounting_flag, sec_financial_derived.

thirteenf    Parse 13F INFORMATION TABLE XML attachments from bronze. Same Branch A
             dependency and sequencing as per-filing.
             Output: sec_thirteenf_holding.

company-identity Company master identity: global reference data
             (company_tickers/company_tickers_exchange) plus per-CIK
             submissions.json metadata. No Branch A dependency, and no
             ownership/ADV artifact fetch or parse -- calls
             _run_submissions_bronze_then_silver with its default
             artifact_policy/parser_policy ("none"/"none"), so only the
             form-agnostic silver staging that already happens for every
             submission (sec_company, sec_company_filing,
             sec_company_address, sec_company_former_name) runs; no
             ownership/ADV accessions are touched.
             Output: sec_company, sec_company_ticker, sec_company_filing,
             sec_company_address, sec_company_former_name.

Silver database
---------------
Writes to the canonical SEC silver database under ``silver/sec/silver.duckdb``.
Branch B tables share the same DuckDB file as Branch A tables so application code
can enforce cross-table consistency through ordinary reads before writing.

Invariants preserved
--------------------
- ``bootstrap-batch`` is NOT in ``SOURCE_EXPORT_COMMANDS`` — unchanged.
- ``bootstrap-fundamentals`` is NOT in ``SOURCE_EXPORT_COMMANDS`` — same design.
- Gold is built once by ``gold-refresh`` after all batches complete.
- SNOWFLAKE_RUN_MANIFEST_TASK remains STARTED — not altered here.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


_DEFAULT_LOCAL_SILVER_ROOT = "/tmp/edgar-warehouse-silver"


def execute(args: Any) -> int:
    """Entry point for the bootstrap-fundamentals CLI command."""
    raw_cik_list: list[int] = getattr(args, "cik_list", None) or []
    mode: str = str(getattr(args, "mode", "per-filing") or "per-filing")
    run_id: str = str(getattr(args, "run_id", None) or str(uuid.uuid4()))
    identity_refresh_run_id = str(getattr(args, "identity_refresh_run_id", None) or "")
    silver_root_override: str = getattr(args, "silver_root", None) or ""
    release_mode = bool(getattr(args, "release_mode", False))
    candidate_manifest = getattr(args, "candidate_manifest", None)
    if release_mode and not candidate_manifest:
        _err("bootstrap-fundamentals --release-mode requires --candidate-manifest")
        return 2
    if release_mode and mode in ("entity-facts", "company-identity"):
        _err("bootstrap-fundamentals --release-mode is only valid for per-filing or thirteenf")
        return 2
    if identity_refresh_run_id and (mode != "company-identity" or not raw_cik_list):
        _err("--identity-refresh-run-id requires company-identity mode with an explicit --cik-list")
        return 2
    if identity_refresh_run_id and identity_refresh_run_id != run_id:
        _err("--identity-refresh-run-id must match --run-id")
        return 2

    candidate_manifest_rows: list[Any] | None = None
    if candidate_manifest:
        try:
            from edgar_warehouse.infrastructure.object_storage import read_bytes
            manifest_payload = json.loads(read_bytes(str(candidate_manifest)).decode("utf-8"))
            candidate_manifest_rows = (
                manifest_payload.get("candidates", [])
                if isinstance(manifest_payload, dict) else manifest_payload
            )
            if not candidate_manifest_rows:
                raise ValueError("candidate manifest is empty")
        except Exception as exc:
            _err(f"could not read candidate manifest: {exc}")
            return 2

    cik_offset = int(getattr(args, "cik_offset", 0) or 0)
    _cik_limit_raw = getattr(args, "cik_limit", None)
    cik_limit = int(_cik_limit_raw) if _cik_limit_raw is not None else None

    from edgar_warehouse.infrastructure.warehouse_settings import resolve_edgar_identity
    try:
        identity = resolve_edgar_identity()
    except Exception as exc:
        _err(f"bootstrap-fundamentals: {exc}")
        return 2

    started_at = datetime.now(UTC)
    context = _build_silver_context(identity=identity, silver_root_override=silver_root_override)

    from edgar_warehouse.silver_support.session import open_silver_database
    try:
        # DuckDB Retirement Cutover Ticket 10: hydration removed entirely.
        # _resolve_fundamentals_ciks (both the --cik-list and windowed cases)
        # already reads bookkeeping.get_tracked_ciks() -- Postgres, not this
        # local `db` -- since Ticket 14 repointed it; canonical silver.duckdb
        # is no longer written by any command (see
        # _publish_silver_database_if_remote's docstring), so there is
        # nothing left to hydrate from.
        db = open_silver_database(context.silver_root)
    except Exception as exc:
        _err(f"Failed to open silver database: {exc}")
        return 2

    # DuckDB Retirement Cutover Ticket 14: sec_company_sync_state (read by
    # _resolve_fundamentals_ciks below) and the tables _sync_reference_data/
    # _run_submissions_bronze_then_silver touch now live in the Postgres-backed
    # BookkeepingStore, not this local DuckDB `db` connection.
    bookkeeping = _bookkeeping_store()

    # Resolve the CIK batch. When no explicit --cik-list is given (the Step
    # Functions Map case), pull the ordered silver tracking universe — the SAME
    # source and ordering Branch A's bootstrap-next uses — and apply
    # offset-then-limit windowing. This guarantees Branch A and Branch B process
    # identical CIK windows for the same {window_offset, window_limit} Map item.
    try:
        cik_list = _resolve_fundamentals_ciks(
            bookkeeping=bookkeeping,
            raw_cik_list=raw_cik_list,
            cik_offset=cik_offset,
            cik_limit=cik_limit,
        )
    except Exception as exc:
        _err(f"bootstrap-fundamentals could not resolve CIKs: {exc}")
        return 2

    if not cik_list:
        _err(
            "bootstrap-fundamentals requires --cik-list, or silver tracking state "
            "resolvable via --cik-offset/--cik-limit"
        )
        return 2

    candidate_accessions: set[str] | None = None
    if candidate_manifest_rows is not None:
        allowed_ciks = set(cik_list)
        per_filing_forms = {"8-K", "8-K/A", "DEF 14A", "DEF 14A/A", "DEFA14A", "PRE 14A"}
        thirteenf_forms = {"13F-HR", "13F-HR/A"}
        allowed_forms = per_filing_forms if mode == "per-filing" else thirteenf_forms
        candidate_accessions = set()
        for row in candidate_manifest_rows:
            if isinstance(row, dict):
                row_cik = int(row.get("cik") or 0)
                row_form = str(row.get("form") or "").strip().upper()
                if row_cik not in allowed_ciks or row_form not in allowed_forms:
                    continue
                accession = row.get("accession_number")
            else:
                accession = row
            if accession:
                candidate_accessions.add(str(accession))

    metrics: dict[str, Any] = {"mode": mode, "cik_count": len(cik_list)}
    _log("bootstrap_fundamentals_started", run_id=run_id, mode=mode,
         cik_count=len(cik_list), cik_offset=cik_offset,
         cik_limit=(cik_limit if cik_limit is not None else -1),
         resolved_from=("cik_list" if raw_cik_list else "silver_tracking_state"),
         silver_root=context.silver_root.root)

    # duckdb-retirement-cutover Ticket 17: per-filing/thirteenf/entity-facts
    # all need to READ real Branch A filing/attachment/raw-object metadata
    # and prior fundamentals output -- `db` (local DuckDB) is never
    # hydrated in production (Ticket 10 removed hydration entirely), so it
    # can never answer those reads. `source` is a read-only Snowflake
    # reader against the same live data; `db` stays the write target for
    # all three modes, unchanged.
    #
    # Hard-fail (not silently degrade) when this connection can't be
    # established, matching this function's own convention for every other
    # real dependency (resolve_edgar_identity, open_silver_database) above.
    # A pre-code /gof-refactor-reviewer consult flagged that falling back to
    # `db` here would reproduce this exact ticket's bug -- unbounded
    # re-fetch/re-scan -- conditionally on Snowflake being unreachable,
    # instead of fixing it: strictly worse than a loud failure, since it
    # would be an intermittent regression instead of an always-on one.
    source = None
    if mode in ("per-filing", "thirteenf", "entity-facts"):
        source = _open_fundamentals_silver_source()
        if source is None:
            db.close()
            _err("bootstrap-fundamentals: fundamentals silver source (Snowflake) unavailable")
            return 2

    try:
        if mode == "per-filing":
            from edgar_warehouse.application.workflows.fundamentals_ingest import (
                run_bootstrap_fundamentals_per_filing,
            )
            run_metrics = run_bootstrap_fundamentals_per_filing(
                cik_list=cik_list,
                source=source,
                db=db,
                sync_run_id=run_id,
                release_mode=release_mode,
                candidate_accessions=candidate_accessions,
            )
            metrics.update(run_metrics)

        elif mode == "entity-facts":
            from edgar_warehouse.application.workflows.fundamentals_ingest import (
                run_bootstrap_entity_facts,
            )
            run_metrics = run_bootstrap_entity_facts(
                cik_list=cik_list,
                db=db,
                identity=identity,
                sync_run_id=run_id,
                force=bool(getattr(args, "force", False)),
                source=source,
            )
            metrics.update(run_metrics)

            # After entity-facts, back-fill cross-period forensic scores
            from edgar_warehouse.parsers.accounting_flags import backfill_accounting_flags
            flags_updated = 0
            for cik in cik_list:
                try:
                    flags_updated += backfill_accounting_flags(cik=cik, silver=db)
                except Exception as exc:
                    _log("accounting_flags_backfill_error", cik=cik, error=str(exc))
            metrics["accounting_flags_updated"] = flags_updated

        elif mode == "thirteenf":
            from edgar_warehouse.application.workflows.fundamentals_ingest import (
                run_bootstrap_thirteenf,
            )
            run_metrics = run_bootstrap_thirteenf(
                cik_list=cik_list,
                source=source,
                db=db,
                sync_run_id=run_id,
                release_mode=release_mode,
                candidate_accessions=candidate_accessions,
            )
            metrics.update(run_metrics)

        elif mode == "company-identity":
            from edgar_warehouse.application.warehouse_orchestrator import (
                _merge_capture_network_metrics,
                _run_submissions_bronze_then_silver,
                _sync_reference_data,
            )
            fetch_date = started_at.date()
            if not identity_refresh_run_id:
                reference_metrics = _sync_reference_data(
                    context=context,
                    db=db,
                    bookkeeping=bookkeeping,
                    sync_run_id=run_id,
                    fetch_date=fetch_date,
                )
                metrics["reference_rows_written"] = reference_metrics["rows_written"]
                metrics["reference_rows_skipped"] = reference_metrics["rows_skipped"]
            # artifact_policy/parser_policy default to "none": bronze submissions
            # capture + form-agnostic silver staging (sec_company,
            # sec_company_filing, sec_company_address, sec_company_former_name)
            # only -- no ownership/ADV artifact fetch or parse.
            run_metrics = _run_submissions_bronze_then_silver(
                context=context,
                db=db,
                bookkeeping=bookkeeping,
                sync_run_id=run_id,
                ciks=cik_list,
                include_pagination=True,
                fetch_date=fetch_date,
                force=bool(getattr(args, "force", False)),
                load_mode="company_identity",
            )
            metrics["rows_inserted"] = run_metrics["rows_written"]
            metrics["rows_skipped"] = run_metrics["rows_skipped"]
            _merge_capture_network_metrics(metrics, run_metrics)

        else:
            db.close()
            _err(
                "Unknown mode '{mode}'. Expected: per-filing | entity-facts | "
                "thirteenf | company-identity".format(mode=mode)
            )
            return 2

    except Exception as exc:
        try:
            db.close()
        except Exception:
            pass
        if source is not None:
            try:
                source.close()
            except Exception:
                pass
        _err(f"bootstrap-fundamentals failed: {exc}")
        return 2

    db.close()
    if source is not None:
        try:
            source.close()
        except Exception:
            pass

    # A run-scoped Daily Identity Refresh persists only its immutable CIK delta.
    # The dedicated reducer is the sole canonical publisher for that run.
    if identity_refresh_run_id:
        from pathlib import Path

        from edgar_warehouse.application.identity_refresh_publication import persist_batch_outcome

        image_identity = os.environ.get("WAREHOUSE_IMAGE_REF", "").strip()
        if not image_identity:
            _err("identity refresh batch requires WAREHOUSE_IMAGE_REF")
            return 2
        try:
            outcome = persist_batch_outcome(
                context.storage_root,
                run_id=identity_refresh_run_id,
                image_identity=image_identity,
                ciks=cik_list,
                delta_file=Path(context.silver_root.join("silver", "sec", "silver.duckdb")),
            )
            metrics["identity_refresh_delta"] = {
                "batch_id": outcome["batch_id"],
                "path": outcome["delta_path"],
                "sha256": outcome["sha256"],
            }
        except Exception as exc:
            _err(f"Failed to persist identity refresh batch delta: {exc}")
            return 1

    # Upload the unified silver database to remote storage so later tasks can
    # consume the Branch A and Branch B tables from one consistent file.
    if context.storage_root.root and not identity_refresh_run_id:
        from edgar_warehouse.application.warehouse_orchestrator import (
            _publish_silver_database_if_remote,
        )
        try:
            upload_result = _publish_silver_database_if_remote(context)
            if upload_result and upload_result.get("skipped"):
                _log(
                    "silver_database_publish_skipped_noop",
                    relative_path=upload_result["relative_path"],
                    run_id=run_id,
                )
                metrics["silver_database_uploaded"] = False
            elif upload_result:
                _log(
                    "silver_database_uploaded",
                    destination=upload_result["path"],
                    size_bytes=upload_result["size_bytes"],
                    run_id=run_id,
                )
                metrics["silver_database_uploaded"] = True
                metrics["silver_database_size_bytes"] = upload_result["size_bytes"]
        except Exception as exc:
            _err(f"Failed to upload silver database to remote storage: {exc}")
            return 1

    duration = (datetime.now(UTC) - started_at).total_seconds()
    payload = {
        "command": "bootstrap-fundamentals",
        "run_id": run_id,
        "mode": mode,
        "cik_count": len(cik_list),
        "duration_seconds": round(duration, 2),
        "metrics": metrics,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "status": "ok",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    _log("bootstrap_fundamentals_completed", run_id=run_id, mode=mode,
         duration_seconds=payload["duration_seconds"], **{
             k: v for k, v in metrics.items() if isinstance(v, int)
         })
    return 0


def _open_fundamentals_silver_source() -> Any | None:
    """Read-only Snowflake reader for per-filing/thirteenf/entity-facts's
    skip-check and Branch A filing-metadata reads.

    duckdb-retirement-cutover Ticket 17: ``db`` (local DuckDB) is never
    hydrated in production, so it can never answer "does this filing/CIK
    already exist". Reuses ``SnowflakeSilverReader.connect()``'s default
    settings (``EDGARTOOLS_PROD_MDM_SILVER_READER``) -- despite its name,
    that role is the only one granted schema-wide read access to
    ``EDGARTOOLS_SILVER``, and ``SnowflakeSilverReader`` was already
    designed as a general ``.fetch()`` read seam, not an MDM-exclusive one
    (its own module docstring). Minting a second, identically-scoped
    read-only role would duplicate this one for no security benefit.

    Returns ``None`` on any connection failure. The caller hard-fails
    (``return 2``) rather than falling back to ``db`` -- ``db`` is empty in
    production, so a fallback would reproduce this exact ticket's bug
    (unbounded re-fetch/re-scan) conditionally on Snowflake being
    unreachable instead of fixing it, matching this command's existing
    convention for every other real dependency (``resolve_edgar_identity``,
    ``open_silver_database``).
    """
    from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader

    try:
        return SnowflakeSilverReader.connect()
    except Exception as exc:
        _err(f"fundamentals silver source unavailable: {exc}")
        return None


def _build_silver_context(
    *,
    identity: str,
    silver_root_override: str,
) -> WarehouseCommandContext:
    storage_root_uri = os.environ.get("WAREHOUSE_STORAGE_ROOT", "").strip()
    silver_root_uri = _resolve_silver_root_uri(
        storage_root_uri=storage_root_uri,
        silver_root_override=silver_root_override,
    )
    storage_root = StorageLocation(storage_root_uri or silver_root_uri)
    return WarehouseCommandContext(
        bronze_root=StorageLocation(
            os.environ.get("WAREHOUSE_BRONZE_ROOT", "").strip() or storage_root.root
        ),
        storage_root=storage_root,
        silver_root=StorageLocation(silver_root_uri),
        snowflake_export_root=None,
        environment_name=os.environ.get("WAREHOUSE_ENVIRONMENT", "dev"),
        identity=identity,
        runtime_mode=os.environ.get("WAREHOUSE_RUNTIME_MODE", "bronze_capture"),
    )


def _resolve_silver_root_uri(
    *,
    storage_root_uri: str,
    silver_root_override: str,
) -> str:
    if silver_root_override:
        return silver_root_override

    env_silver_root = os.environ.get("WAREHOUSE_SILVER_ROOT", "").strip()
    if env_silver_root:
        return env_silver_root

    if storage_root_uri:
        storage_root = StorageLocation(storage_root_uri)
        if not storage_root.is_remote:
            return storage_root_uri

    return _DEFAULT_LOCAL_SILVER_ROOT


def _resolve_fundamentals_ciks(
    *,
    bookkeeping: Any,
    raw_cik_list: list[int],
    cik_offset: int,
    cik_limit: int | None,
) -> list[int]:
    """Resolve the CIK batch for this Branch B run.

    Mirrors Branch A's ``_resolve_bootstrap_target_ciks`` semantics so the two
    parallel branches process identical windows for the same ``{window_offset,
    window_limit}`` Map item:

    - With an explicit ``--cik-list``: use it as-is, then window.
    - Without one: pull the silver tracked universe (ordered ASC by CIK, the same
      source/order/status-filter ``compute-windows``/``bootstrap-next`` use —
      LOAD_HISTORY_TRACKING_STATUS_FILTER, not 'active' alone; see that
      constant's docstring for why), then window.

    Windowing is offset-first, limit-second.
    """
    from edgar_warehouse.application.warehouse_orchestrator import (
        LOAD_HISTORY_TRACKING_STATUS_FILTER,
        _validate_window_args,
    )

    _validate_window_args(cik_limit, cik_offset)
    if raw_cik_list:
        ciks = list(raw_cik_list)
    else:
        ciks = bookkeeping.get_tracked_ciks(LOAD_HISTORY_TRACKING_STATUS_FILTER)
    ciks = ciks[cik_offset:]
    if cik_limit is not None:
        ciks = ciks[:cik_limit]
    return ciks


def _bookkeeping_store() -> Any:
    from edgar_warehouse.bookkeeping.database import get_engine, get_session
    from edgar_warehouse.bookkeeping.store import BookkeepingStore
    return BookkeepingStore(get_session(get_engine()))


def _log(event: str, **kwargs: Any) -> None:
    doc = {"event": event, "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"), **kwargs}
    print(json.dumps(doc, sort_keys=True), file=sys.stderr, flush=True)


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr, flush=True)
