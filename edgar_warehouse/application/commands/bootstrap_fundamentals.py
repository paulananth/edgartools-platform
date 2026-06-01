"""bootstrap-fundamentals command — Branch B silver ingestion (fundamentals namespace).

This command is the Branch B counterpart of ``bootstrap-batch``.  It runs in
parallel with ``bootstrap-batch`` (Branch A) as a Step Functions ``Parallel``
state node.  Each Distributed Map iteration calls this command with a specific
CIK batch and mode.

Modes
-----
per-filing   Process 8-K earnings releases + DEF 14A proxy filings from bronze.
             Output: sec_earnings_release, sec_executive_record.

entity-facts Fetch SEC companyfacts API for each CIK.
             Output: sec_financial_fact, sec_accounting_flag, sec_financial_derived.

thirteenf    Parse 13F INFORMATION TABLE XML attachments from bronze.
             Output: sec_thirteenf_holding.

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

    identity = os.environ.get("SEC_EDGAR_IDENTITY", "edgar-warehouse/1.0 admin@example.com")
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

    try:
        if mode == "per-filing":
            from edgar_warehouse.application.workflows.fundamentals_ingest import (
                run_bootstrap_fundamentals_per_filing,
            )
            # bronze_root is not needed — artifacts are read via silver raw_object paths
            run_metrics = run_bootstrap_fundamentals_per_filing(
                cik_list=cik_list,
                db=db,
                bronze_root=None,
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
        _err(f"bootstrap-fundamentals failed: {exc}")
        return 2

    db.close()

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
    - Without one: pull the MDM tracked active universe (ordered ASC by CIK,
      the same source/order ``bootstrap-next`` uses), then window.

    Windowing is offset-first, limit-second.
    """
    from edgar_warehouse.application.warehouse_orchestrator import (
        _get_mdm_tracked_ciks,
        _validate_window_args,
    )

    _validate_window_args(cik_limit, cik_offset)
    if raw_cik_list:
        ciks = list(raw_cik_list)
    else:
        ciks = _get_mdm_tracked_ciks("active")
    ciks = ciks[cik_offset:]
    if cik_limit is not None:
        ciks = ciks[:cik_limit]
    return ciks


def _log(event: str, **kwargs: Any) -> None:
    doc = {"event": event, "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"), **kwargs}
    print(json.dumps(doc, sort_keys=True), file=sys.stderr, flush=True)


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr, flush=True)
