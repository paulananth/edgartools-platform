"""Workflow entrypoint for ``drive-filing-discovery-for-date`` (Ticket 16).

Turns an already-sealed SEC daily form index observation
(``load-daily-form-index-for-date``'s own output: ``stg_daily_index_filing``
rows checkpointed ``status='succeeded'``) into a Discovery Manifest and
drives each in-scope candidate through the Ticket 15 ledger-gated capture
Facade -- without a human supplying a ``--source-url`` by hand.

Like ``capture-filing-artifact``, this command is genuinely new and drives
the Ticket 14 ledger and Ticket 15 Facade directly rather than delegating
into the legacy ``execute_standard_command``/``_execute_warehouse`` engine.
It writes the same declared run-manifest layers Ticket 13's registration
seam promises (bronze/staging/artifacts + a consolidated run_manifest) via
the shared ``acquisition_run_writes`` helpers also used by
``capture-filing-artifact``, and folds the interval's own completion summary
into the consolidated manifest's ``row_counts`` so completion is legible
from the durable artifact, not only the process exit code.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from edgar_warehouse.acquisition.discovery import (
    DiscoveryDriveResult,
    build_discovery_manifest,
    drive_discovery_manifest,
)
from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchDisposition, FetchWorkState
from edgar_warehouse.acquisition.source_family_registry import build_source_family_registry
from edgar_warehouse.application.acquisition_command_registry import (
    acquisition_command_registration,
)
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application.warehouse_orchestrator import (
    _build_warehouse_context,
    _hydrate_silver_database_from_storage,
)
from edgar_warehouse.application.workflows.acquisition_run_writes import (
    write_consolidated_run_manifest,
    write_declared_layer_manifests,
)
from edgar_warehouse.mdm.database import get_engine
from edgar_warehouse.silver_support.session import open_silver_database

DEFAULT_LEASE_SECONDS = 300
DEFAULT_REGISTRY_VERSION = "filing_artifact-v1"
COMMAND_NAME = "drive-filing-discovery-for-date"


def run_drive_filing_discovery_for_date(args: Any) -> int:
    context = _build_warehouse_context(COMMAND_NAME)
    now = datetime.now(UTC)
    run_id = getattr(args, "run_id", None) or uuid.uuid4().hex
    business_date = str(args.business_date)
    arguments = {"business_date": business_date}

    registration = acquisition_command_registration(COMMAND_NAME)
    assert registration is not None, f"{COMMAND_NAME} is not registered"
    scope = registration.resolve_scope(arguments=arguments, now=now, silver_root=None)
    manifest_writes = write_declared_layer_manifests(
        command_name=COMMAND_NAME, context=context, run_id=run_id, arguments=arguments, scope=scope, now=now
    )

    rows = _load_sealed_discovery_rows(context, business_date)
    manifest = build_discovery_manifest(rows, business_date=business_date)

    engine = get_engine()
    ledger = AcquisitionLedger(engine)
    registry = build_source_family_registry(identity=context.identity)
    worker_id = getattr(args, "worker_id", None) or f"drive-filing-discovery-{os.getpid()}"
    lease_seconds = getattr(args, "lease_seconds", None) or DEFAULT_LEASE_SECONDS
    registry_version = getattr(args, "registry_version", None) or DEFAULT_REGISTRY_VERSION

    result = drive_discovery_manifest(
        ledger,
        context.bronze_root,
        registry,
        manifest,
        worker_id=worker_id,
        registry_version=registry_version,
        lease_seconds=lease_seconds,
    )

    write_consolidated_run_manifest(
        command_name=COMMAND_NAME,
        context=context,
        run_id=run_id,
        arguments=arguments,
        scope=scope,
        now=now,
        manifest_writes=manifest_writes,
        row_counts=_interval_row_counts(result),
    )

    payload = _result_payload(result, run_id=run_id, business_date=business_date)
    print(json.dumps(payload, sort_keys=True))
    return 0 if result.interval_complete else 1


def _load_sealed_discovery_rows(context: Any, business_date: str) -> list[dict[str, Any]]:
    """Read the already-captured, already-checkpointed discovery observation.

    Fails closed if the daily index for this business date has not yet been
    fetched and sealed by ``load-daily-form-index-for-date`` -- this command
    never triggers that fetch itself (out of scope; see module docstring).
    """

    _hydrate_silver_database_from_storage(context)
    db = open_silver_database(context.silver_root)
    try:
        checkpoint = db.get_daily_index_checkpoint(business_date)
        status = checkpoint.get("status") if checkpoint else "missing"
        if status != "succeeded":
            raise WarehouseRuntimeError(
                f"No sealed discovery observation for business_date={business_date} "
                f"(checkpoint status={status!r}); run load-daily-form-index-for-date "
                "for this date first"
            )
        return db.get_daily_index_filings(business_date)
    finally:
        db.close()


def _interval_row_counts(result: DiscoveryDriveResult) -> dict[str, Any]:
    """Seal the interval's completion in the durable manifest, not just the exit code."""

    captured = sum(
        1 for outcome in result.outcomes if outcome.fetch_state is FetchWorkState.CAPTURED
    )
    excluded = sum(
        1
        for outcome in result.outcomes
        if outcome.fetch_disposition is FetchDisposition.OUT_OF_SCOPE
    )
    return {
        "candidates": result.manifest.candidate_count,
        "captured": captured,
        "excluded": excluded,
        "unsettled": len(result.unsettled_candidate_ids),
        "interval_complete": result.interval_complete,
    }


def _result_payload(
    result: DiscoveryDriveResult, *, run_id: str, business_date: str
) -> dict[str, Any]:
    return {
        "business_date": business_date,
        "candidate_count": result.manifest.candidate_count,
        "discovery_manifest_digest": result.manifest.digest,
        "interval_complete": result.interval_complete,
        "run_id": run_id,
        "unsettled_candidate_ids": list(result.unsettled_candidate_ids),
        "outcomes": [
            {
                "accession_number": outcome.candidate.accession_number,
                "cik": outcome.candidate.cik,
                "form": outcome.candidate.form,
                "in_scope": outcome.candidate.in_scope,
                "decision_id": outcome.decision_id,
                "fetch_disposition": (
                    outcome.fetch_disposition.value
                    if outcome.fetch_disposition is not None
                    else None
                ),
                "fetch_state": (
                    outcome.fetch_state.value if outcome.fetch_state is not None else None
                ),
                "network_fetched": outcome.network_fetched,
                "error": outcome.error,
            }
            for outcome in result.outcomes
        ],
    }
