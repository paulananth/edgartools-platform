"""bootstrap-fundamentals command — Branch B silver ingestion (fundamentals namespace).

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
             SEC directly via the shared SEC client — so in ``load_history`` this
             mode still runs concurrently with Branch A.
             Output: sec_financial_fact, sec_accounting_flag, sec_financial_derived.

thirteenf    Parse 13F INFORMATION TABLE XML attachments from bronze. Same Branch A
             dependency and sequencing as per-filing.
             Output: sec_thirteenf_holding.

Source reader (per-filing, thirteenf)
--------------------------------------
``sec_company_filing``/``sec_filing_attachment``/``sec_raw_object`` are produced by
Branch A, not by this command — the fundamentals shard ``db`` opens below never
contains them. ``execute()`` hydrates a read-only reader over Branch A's published
ownership silver.duckdb (see ``_hydrate_ownership_silver_readonly``) and passes it
as ``source`` to the per-filing/thirteenf workflow functions; ``db`` remains the
write-only target for fundamentals output tables.

Silver namespace
----------------
Writes to ``silver/fundamentals/`` (separate from Branch A's ``silver/ownership/``).
This is required by DuckDB's single-writer constraint (AD-05).  Both namespaces
are mounted as UNION ALL views by ShardedSilverReader during MDM derivation.

Invariants preserved
--------------------
- ``bootstrap-batch`` is NOT in ``GOLD_AFFECTING_COMMANDS`` — unchanged.
- ``bootstrap-fundamentals`` is NOT in ``GOLD_AFFECTING_COMMANDS`` — same design.
- Gold is built once by ``gold-refresh`` after all batches complete.
- SNOWFLAKE_RUN_MANIFEST_TASK remains STARTED — not altered here.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def execute(args: Any) -> int:
    """Entry point for the bootstrap-fundamentals CLI command."""
    raw_cik_list: list[int] = getattr(args, "cik_list", None) or []
    mode: str = str(getattr(args, "mode", "per-filing") or "per-filing")
    run_id: str = str(getattr(args, "run_id", None) or str(uuid.uuid4()))
    fundamentals_silver_path: str = getattr(args, "fundamentals_silver_path", None) or ""

    cik_offset = int(getattr(args, "cik_offset", 0) or 0)
    _cik_limit_raw = getattr(args, "cik_limit", None)
    cik_limit = int(_cik_limit_raw) if _cik_limit_raw is not None else None

    # Resolve the CIK batch.  When no explicit --cik-list is given (the Step
    # Functions Map case), pull the ordered MDM active universe — the SAME source
    # and ordering Branch A's bootstrap-next uses — and apply offset-then-limit
    # windowing.  This guarantees Branch A and Branch B process identical CIK
    # windows for the same {window_offset, window_limit} Map item.
    try:
        cik_list = _resolve_fundamentals_ciks(
            raw_cik_list=raw_cik_list, cik_offset=cik_offset, cik_limit=cik_limit
        )
    except Exception as exc:
        _err(f"bootstrap-fundamentals could not resolve CIKs: {exc}")
        return 2

    if not cik_list:
        _err(
            "bootstrap-fundamentals requires --cik-list, or an MDM-tracked active "
            "universe resolvable via --cik-offset/--cik-limit"
        )
        return 2

    if not fundamentals_silver_path:
        # Fall back to env var (set by ECS task definition)
        fundamentals_silver_path = os.environ.get(
            "FUNDAMENTALS_SILVER_PATH", "/tmp/silver/fundamentals/shard-0.duckdb"
        )

    from edgar_warehouse.infrastructure.warehouse_settings import resolve_edgar_identity
    try:
        identity = resolve_edgar_identity()
    except Exception as exc:
        _err(f"bootstrap-fundamentals: {exc}")
        return 2

    started_at = datetime.now(UTC)

    _log("bootstrap_fundamentals_started", run_id=run_id, mode=mode,
         cik_count=len(cik_list), cik_offset=cik_offset,
         cik_limit=(cik_limit if cik_limit is not None else -1),
         resolved_from=("cik_list" if raw_cik_list else "mdm_active_universe"),
         fundamentals_silver_path=fundamentals_silver_path)

    # Open fundamentals silver shard (creates tables if first run)
    from edgar_warehouse.silver_support.session import open_silver_shard
    try:
        db = open_silver_shard(fundamentals_silver_path)
    except Exception as exc:
        _err(f"Failed to open fundamentals silver database: {exc}")
        return 2

    metrics: dict[str, Any] = {"mode": mode, "cik_count": len(cik_list)}

    # per-filing and thirteenf read filing/attachment/raw-object metadata from
    # Branch A's ownership silver (bootstrap-next/bootstrap-batch output) — that
    # data was never in the fundamentals-only shard `db` opens. Hydrate a
    # read-only reader over it here; entity-facts needs no source read (it calls
    # the SEC companyfacts API directly).
    source = None
    if mode in ("per-filing", "thirteenf"):
        source_path = _hydrate_ownership_silver_readonly(
            storage_root_uri=os.environ.get("WAREHOUSE_STORAGE_ROOT", "").strip(),
            local_cache_dir=str(Path(fundamentals_silver_path).resolve().parent.parent),
        )
        if source_path is not None:
            from edgar_warehouse.silver_support.sharded_reader import ShardedSilverReader
            source = ShardedSilverReader([source_path])
        else:
            _log("bootstrap_fundamentals_source_unavailable", run_id=run_id, mode=mode)

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
            )
            metrics.update(run_metrics)

        else:
            db.close()
            _err(f"Unknown mode '{mode}'. Expected: per-filing | entity-facts | thirteenf")
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
        source.close()

    # Upload shard to remote storage so gold-refresh can consume it.
    # ECS container filesystems are ephemeral — without this the shard is lost on exit.
    storage_root_uri = os.environ.get("WAREHOUSE_STORAGE_ROOT", "")
    if storage_root_uri:
        from edgar_warehouse.application.warehouse_orchestrator import (
            _publish_fundamentals_shard_if_remote,
        )
        try:
            upload_result = _publish_fundamentals_shard_if_remote(
                local_shard_path=fundamentals_silver_path,
                storage_root_uri=storage_root_uri,
            )
            if upload_result:
                _log(
                    "fundamentals_shard_uploaded",
                    destination=upload_result["path"],
                    size_bytes=upload_result["size_bytes"],
                    run_id=run_id,
                )
                metrics["fundamentals_shard_uploaded"] = True
                metrics["fundamentals_shard_size_bytes"] = upload_result["size_bytes"]
        except Exception as exc:
            _err(f"Failed to upload fundamentals shard to remote storage: {exc}")
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


def _resolve_fundamentals_ciks(
    *,
    raw_cik_list: list[int],
    cik_offset: int,
    cik_limit: int | None,
) -> list[int]:
    """Resolve the CIK batch for this Branch B run.

    Mirrors Branch A's ``_resolve_bootstrap_target_ciks`` semantics so the two
    parallel branches process identical windows for the same ``{window_offset,
    window_limit}`` Map item:

    - With an explicit ``--cik-list``: use it as-is, then window.
    - Without one: pull the MDM tracked universe (ordered ASC by CIK, the same
      source/order/status-filter ``compute-windows``/``bootstrap-next`` use —
      LOAD_HISTORY_TRACKING_STATUS_FILTER, not 'active' alone; see that
      constant's docstring for why), then window.

    Windowing is offset-first, limit-second.
    """
    from edgar_warehouse.application.warehouse_orchestrator import (
        LOAD_HISTORY_TRACKING_STATUS_FILTER,
        _get_mdm_tracked_ciks,
        _validate_window_args,
    )

    _validate_window_args(cik_limit, cik_offset)
    if raw_cik_list:
        ciks = list(raw_cik_list)
    else:
        ciks = _get_mdm_tracked_ciks(LOAD_HISTORY_TRACKING_STATUS_FILTER)
    ciks = ciks[cik_offset:]
    if cik_limit is not None:
        ciks = ciks[:cik_limit]
    return ciks


def _hydrate_ownership_silver_readonly(
    *, storage_root_uri: str, local_cache_dir: str
) -> str | None:
    """Download Branch A's ownership silver.duckdb for read-only Branch B access.

    Mirrors the remote/local branching in
    ``warehouse_orchestrator._hydrate_silver_database_from_storage``, but takes
    plain strings instead of a full ``WarehouseCommandContext`` — bootstrap-fundamentals
    has never required ``WAREHOUSE_BRONZE_ROOT`` and shouldn't start requiring it
    just to read Branch A's silver.

    Returns the local path, or None when unavailable: storage is local and no
    monolith exists yet, or Branch A hasn't published one to remote storage yet.
    Callers treat None as "zero filings available" (AD-13), not an error.
    """
    from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes

    local_path = Path(local_cache_dir) / "sec" / "silver.duckdb"

    if not storage_root_uri:
        return str(local_path) if local_path.exists() else None

    storage = StorageLocation(root=storage_root_uri)
    if not storage.is_remote:
        return str(local_path) if local_path.exists() else None

    remote_path = storage.join("silver", "sec", "silver.duckdb")
    try:
        payload = read_bytes(remote_path)
    except (FileNotFoundError, OSError):
        return None

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(payload)
    return str(local_path)


def _log(event: str, **kwargs: Any) -> None:
    doc = {"event": event, "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"), **kwargs}
    print(json.dumps(doc, sort_keys=True), file=sys.stderr, flush=True)


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr, flush=True)
