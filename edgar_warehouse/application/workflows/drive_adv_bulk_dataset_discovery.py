"""Workflow entrypoint for ``drive-adv-bulk-dataset-discovery`` (Ticket 24).

Mirrors ``drive_reference_catalog_discovery.py``'s shape: resolve a manifest,
drive it through the Ticket 15 ledger-gated capture Facade, carry every
CAPTURED candidate to Silver via
``adv_bulk_dataset_silver_acceptance.drive_adv_bulk_dataset_silver_acceptance``,
then publish the local Silver candidate back to canonical storage the same
way every other silver-writing command does.

Genuinely new, drives the Ticket 14 ledger and Ticket 15 Facade directly
rather than delegating into ``warehouse_orchestrator.py``'s
``ingest-relationship-sources``/``adv_bulk_fetch.fetch_adv_bulk_sources`` /
``firm_roster_fetch.fetch_firm_roster_sources`` legacy path (the bypass
Ticket 27 removes later, once every source family proves the authoritative
path -- this module does not touch it).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from edgar_warehouse.acquisition.adv_bulk_dataset_discovery import (
    ADV_BULK_DATASET_DISCOVERY_SOURCE_FAMILY,
    AdvBulkDatasetDriveResult,
    build_adv_bulk_dataset_manifest,
    drive_adv_bulk_dataset_manifest,
)
from edgar_warehouse.acquisition.adv_bulk_dataset_silver_acceptance import (
    ADV_BULK_PRODUCER_NAMES,
    FIRM_ROSTER_PRODUCER_NAME,
    AdvBulkDatasetSilverAcceptanceResult,
    drive_adv_bulk_dataset_silver_acceptance,
)
from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchWorkState
from edgar_warehouse.acquisition.processing import ProcessingLedger, SilverFinalizer
from edgar_warehouse.acquisition.registry_ledger import (
    SourceRegistryLedger,
    active_family_coverage,
    build_active_source_family_registry,
)
from edgar_warehouse.acquisition.revisions import SourceRevisionLedger
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
DEFAULT_REGISTRY_VERSION = "adv-bulk-dataset-v1"
DEFAULT_WINDOW_MONTHS = 13
COMMAND_NAME = "drive-adv-bulk-dataset-discovery"

ROLLING_WINDOW_BULK_DATASET_DISCOVERY_POLICY = "rolling_window_bulk_dataset"
_REQUIRED_PRODUCERS_DEFAULT = ADV_BULK_PRODUCER_NAMES + (FIRM_ROSTER_PRODUCER_NAME,)


class UnsupportedDiscoveryPolicy(WarehouseRuntimeError):
    """A covered family declares a discovery_policy this driver does not implement."""


def run_drive_adv_bulk_dataset_discovery(args: Any) -> int:
    context = _build_warehouse_context(COMMAND_NAME)
    now = datetime.now(UTC)
    run_id = getattr(args, "run_id", None) or uuid.uuid4().hex
    window_months = getattr(args, "window_months", None) or DEFAULT_WINDOW_MONTHS
    arguments = {"window_months": window_months}

    registration = acquisition_command_registration(COMMAND_NAME)
    assert registration is not None, f"{COMMAND_NAME} is not registered"
    scope = registration.resolve_scope(arguments=arguments, now=now, silver_root=None)
    manifest_writes = write_declared_layer_manifests(
        command_name=COMMAND_NAME, context=context, run_id=run_id, arguments=arguments, scope=scope, now=now
    )

    engine = get_engine()
    coverage = active_family_coverage(engine, ADV_BULK_DATASET_DISCOVERY_SOURCE_FAMILY)
    if coverage is not None and coverage.discovery_policy != ROLLING_WINDOW_BULK_DATASET_DISCOVERY_POLICY:
        raise UnsupportedDiscoveryPolicy(
            f"source_family={ADV_BULK_DATASET_DISCOVERY_SOURCE_FAMILY!r} declares "
            f"discovery_policy={coverage.discovery_policy!r}, but this driver "
            f"only implements {ROLLING_WINDOW_BULK_DATASET_DISCOVERY_POLICY!r}"
        )

    required_producers = coverage.required_producers if coverage is not None else _REQUIRED_PRODUCERS_DEFAULT

    from edgar_warehouse.application.adv_bulk_fetch import fetch_reports_metadata_bytes
    from edgar_warehouse.application.firm_roster_fetch import fetch_listing_bytes

    _hydrate_silver_database_from_storage(context)
    db = open_silver_database(context.silver_root)
    try:
        manifest = build_adv_bulk_dataset_manifest(
            universe_label=f"adv-bulk-dataset:{run_id}",
            as_of=now.date(),
            fetch_reports_metadata_bytes=lambda: fetch_reports_metadata_bytes(context.identity),
            fetch_listing_bytes=lambda: fetch_listing_bytes(context.identity),
            window_months=window_months,
        )

        ledger = AcquisitionLedger(engine)
        revisions = SourceRevisionLedger(engine)
        processing = ProcessingLedger(engine)
        finalizer = SilverFinalizer(engine)
        registry = build_active_source_family_registry(engine, identity=context.identity)
        worker_id = getattr(args, "worker_id", None) or f"drive-adv-bulk-dataset-discovery-{os.getpid()}"
        lease_seconds = getattr(args, "lease_seconds", None) or DEFAULT_LEASE_SECONDS
        registry_version = getattr(args, "registry_version", None) or DEFAULT_REGISTRY_VERSION

        result = drive_adv_bulk_dataset_manifest(
            ledger,
            context.bronze_root,
            registry,
            manifest,
            worker_id=worker_id,
            registry_version=registry_version,
            lease_seconds=lease_seconds,
        )
        silver_result = drive_adv_bulk_dataset_silver_acceptance(
            ledger,
            context.bronze_root,
            revisions,
            processing,
            finalizer,
            db,
            result,
            required_producers=required_producers,
        )
    finally:
        db.close()

    if result.interval_complete and silver_result.interval_complete:
        SourceRegistryLedger(engine).record_catchup_progress(
            ADV_BULK_DATASET_DISCOVERY_SOURCE_FAMILY, now.date()
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

    payload = _result_payload(result, silver_result, run_id=run_id)
    print(json.dumps(payload, sort_keys=True))
    return 0 if (result.interval_complete and silver_result.interval_complete) else 1


def _interval_row_counts(
    result: AdvBulkDatasetDriveResult, silver_result: AdvBulkDatasetSilverAcceptanceResult
) -> dict[str, Any]:
    captured = sum(1 for outcome in result.outcomes if outcome.fetch_state is FetchWorkState.CAPTURED)
    silver_settled = sum(1 for o in silver_result.outcomes if o.error is None and o.settled)
    return {
        "candidate_count": result.manifest.candidate_count,
        "unpublished_period_count": len(result.manifest.unpublished_periods),
        "captured": captured,
        "interval_complete": result.interval_complete,
        "silver_settled": silver_settled,
        "silver_interval_complete": silver_result.interval_complete,
    }


def _result_payload(
    result: AdvBulkDatasetDriveResult,
    silver_result: AdvBulkDatasetSilverAcceptanceResult,
    *,
    run_id: str,
) -> dict[str, Any]:
    silver_by_key = {
        (o.source_kind, o.dataset_period, o.variant): o for o in silver_result.outcomes
    }
    return {
        "candidate_count": result.manifest.candidate_count,
        "unpublished_periods": list(result.manifest.unpublished_periods),
        "discovery_manifest_digest": result.manifest.digest,
        "interval_complete": result.interval_complete,
        "silver_interval_complete": silver_result.interval_complete,
        "run_id": run_id,
        "outcomes": [
            {
                "source_kind": outcome.candidate.source_kind,
                "dataset_period": outcome.candidate.dataset_period,
                "variant": outcome.candidate.variant,
                "decision_id": outcome.decision_id,
                "fetch_disposition": (
                    outcome.fetch_disposition.value if outcome.fetch_disposition is not None else None
                ),
                "fetch_state": outcome.fetch_state.value if outcome.fetch_state is not None else None,
                "network_fetched": outcome.network_fetched,
                "error": outcome.error,
                **_silver_fields(
                    silver_by_key.get(
                        (outcome.candidate.source_kind, outcome.candidate.dataset_period, outcome.candidate.variant)
                    )
                ),
            }
            for outcome in result.outcomes
        ],
    }


def _silver_fields(outcome: Any) -> dict[str, Any]:
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
