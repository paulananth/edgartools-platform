"""Workflow entrypoint for ``drive-filing-discovery-for-date`` (Ticket 16/19/29).

Turns an already-sealed SEC daily form index observation
(``load-daily-form-index-for-date``'s own output: ``stg_daily_index_filing``
rows checkpointed ``status='succeeded'``) into a Discovery Manifest, drives
each in-scope candidate through the Ticket 15 ledger-gated capture Facade,
then (Ticket 29's wiring of Ticket 18/19's work into the live path) carries
every CAPTURED candidate the rest of the way -- Logical Source Revision,
sealed expected Silver producers, and a verified Silver publication or
explicit no-impact outcome -- via
``silver_acceptance.drive_filing_artifact_silver_acceptance``, then
publishes the local Silver candidate back to canonical storage the same way
every other silver-writing command does.

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
from datetime import UTC, date, datetime
from typing import Any

from edgar_warehouse.acquisition.discovery import (
    DiscoveryDriveResult,
    build_discovery_manifest,
    drive_discovery_manifest,
)
from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchDisposition, FetchWorkState
from edgar_warehouse.acquisition.processing import ProcessingLedger, SilverFinalizer
from edgar_warehouse.acquisition.registry_ledger import (
    SourceRegistryLedger,
    active_in_scope_forms,
    build_active_source_family_registry,
)
from edgar_warehouse.acquisition.revisions import SourceRevisionLedger
from edgar_warehouse.acquisition.silver_acceptance import (
    FilingArtifactSilverAcceptanceResult,
    drive_filing_artifact_silver_acceptance,
)
from edgar_warehouse.acquisition.source_family_registry import FILING_ARTIFACT_SOURCE_FAMILY
from edgar_warehouse.application.acquisition_command_registry import (
    acquisition_command_registration,
)
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application.warehouse_orchestrator import (
    _build_warehouse_context,
    _hydrate_silver_database_from_storage,
    _publish_silver_database_with_retry,
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

    # The Silver connection stays open across discovery + capture + revision
    # + processing + Silver finalization (Ticket 29): finalize_filing_
    # artifact_candidate needs to write and read back sec_raw_object on the
    # same local candidate this process eventually publishes. Only closed
    # once every candidate has settled, then published as one unit -- not
    # per-candidate, matching every other silver-writing command's
    # hydrate-once/publish-once shape.
    engine = get_engine()
    # Ticket 20: which forms are in scope now comes from the active Source
    # Family Registry version, not discovery.py's own hardcoded default --
    # a covered-but-not-yet-activated family, or one 'remove'd, must not
    # silently fall back to acquiring everything DISCOVERY_IN_SCOPE_FORMS
    # would have covered before the registry existed.
    in_scope_forms = active_in_scope_forms(engine, FILING_ARTIFACT_SOURCE_FAMILY)

    _hydrate_silver_database_from_storage(context)
    db = open_silver_database(context.silver_root)
    try:
        rows = _load_sealed_discovery_rows(db, business_date)
        manifest = build_discovery_manifest(
            rows, business_date=business_date, in_scope_forms=in_scope_forms
        )

        ledger = AcquisitionLedger(engine)
        revisions = SourceRevisionLedger(engine)
        processing = ProcessingLedger(engine)
        finalizer = SilverFinalizer(engine)
        registry = build_active_source_family_registry(engine, identity=context.identity)
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
        silver_result = drive_filing_artifact_silver_acceptance(
            ledger, revisions, processing, finalizer, db, result
        )
    finally:
        db.close()

    if result.interval_complete and silver_result.interval_complete:
        # Ticket 20's catch-up obligation, advanced by the exact same
        # completeness signal Ticket 29 already proved live end-to-end --
        # no separate cross-database prover, this run's own success *is*
        # the proof for this one business date.
        SourceRegistryLedger(engine).record_catchup_progress(
            FILING_ARTIFACT_SOURCE_FAMILY, date.fromisoformat(business_date)
        )

    _publish_silver_database_with_retry(context)

    write_consolidated_run_manifest(
        command_name=COMMAND_NAME,
        context=context,
        run_id=run_id,
        arguments=arguments,
        scope=scope,
        now=now,
        manifest_writes=manifest_writes,
        row_counts=_interval_row_counts(result, silver_result),
    )

    payload = _result_payload(
        result, silver_result, run_id=run_id, business_date=business_date
    )
    print(json.dumps(payload, sort_keys=True))
    return 0 if (result.interval_complete and silver_result.interval_complete) else 1


def _load_sealed_discovery_rows(db: Any, business_date: str) -> list[dict[str, Any]]:
    """Read the already-captured, already-checkpointed discovery observation.

    Fails closed if the daily index for this business date has not yet been
    fetched and sealed by ``load-daily-form-index-for-date`` -- this command
    never triggers that fetch itself (out of scope; see module docstring).
    Takes an already-open ``SilverDatabase`` (Ticket 29) rather than opening
    and closing its own, since the caller keeps the connection open across
    the whole workflow now.
    """

    checkpoint = db.get_daily_index_checkpoint(business_date)
    status = checkpoint.get("status") if checkpoint else "missing"
    if status != "succeeded":
        raise WarehouseRuntimeError(
            f"No sealed discovery observation for business_date={business_date} "
            f"(checkpoint status={status!r}); run load-daily-form-index-for-date "
            "for this date first"
        )
    return db.get_daily_index_filings(business_date)


def _interval_row_counts(
    result: DiscoveryDriveResult, silver_result: FilingArtifactSilverAcceptanceResult
) -> dict[str, Any]:
    """Seal the interval's completion in the durable manifest, not just the exit code."""

    captured = sum(
        1 for outcome in result.outcomes if outcome.fetch_state is FetchWorkState.CAPTURED
    )
    excluded = sum(
        1
        for outcome in result.outcomes
        if outcome.fetch_disposition is FetchDisposition.OUT_OF_SCOPE
    )
    silver_published = sum(
        1
        for outcome in silver_result.outcomes
        if outcome.error is None and outcome.settled
    )
    return {
        "candidates": result.manifest.candidate_count,
        "captured": captured,
        "excluded": excluded,
        "unsettled": len(result.unsettled_candidate_ids),
        "interval_complete": result.interval_complete,
        "silver_carried_forward": len(silver_result.outcomes),
        "silver_settled": silver_published,
        "silver_unsettled": len(silver_result.unsettled_candidate_ids),
        "silver_interval_complete": silver_result.interval_complete,
    }


def _result_payload(
    result: DiscoveryDriveResult,
    silver_result: FilingArtifactSilverAcceptanceResult,
    *,
    run_id: str,
    business_date: str,
) -> dict[str, Any]:
    silver_by_decision_id = {
        outcome.decision_id: outcome for outcome in silver_result.outcomes
    }
    return {
        "business_date": business_date,
        "candidate_count": result.manifest.candidate_count,
        "discovery_manifest_digest": result.manifest.digest,
        "interval_complete": result.interval_complete,
        "silver_interval_complete": silver_result.interval_complete,
        "run_id": run_id,
        "unsettled_candidate_ids": list(result.unsettled_candidate_ids),
        "silver_unsettled_candidate_ids": list(silver_result.unsettled_candidate_ids),
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
                **_silver_outcome_fields(silver_by_decision_id.get(outcome.decision_id)),
            }
            for outcome in result.outcomes
        ],
    }


def _silver_outcome_fields(outcome: Any) -> dict[str, Any]:
    if outcome is None:
        return {
            "revision_id": None,
            "processing_disposition": None,
            "silver_outcome": None,
            "silver_error": None,
        }
    decision = outcome.processing_decision
    return {
        "revision_id": decision.revision_id if decision is not None else None,
        "processing_disposition": decision.disposition.value if decision is not None else None,
        "silver_outcome": decision.silver_outcome.value if decision is not None else None,
        "silver_error": outcome.error,
    }
