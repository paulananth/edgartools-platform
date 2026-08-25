"""Workflow entrypoint for ``drive-reference-catalog-discovery`` (Ticket 23).

Mirrors ``drive_company_facts_discovery.py``'s shape exactly, minus the CIK
universe resolution: the candidate set here is a fixed, small set of source
names (``reference_catalog_discovery.SUPPORTED_SOURCE_NAMES``), not a
per-command-invocation universe query -- seal it into a manifest, drive it
through the Ticket 15 ledger-gated capture Facade, then carry every CAPTURED
candidate the rest of the way -- Logical Source Revision, sealed expected
Silver producers, and a verified Silver publication -- via
``reference_catalog_silver_acceptance.drive_reference_catalog_silver_acceptance``,
then publish the local Silver candidate back to canonical storage the same
way every other silver-writing command does.

Genuinely new, drives the Ticket 14 ledger and Ticket 15 Facade directly
rather than delegating into ``warehouse_orchestrator.py``'s
``_sync_reference_data`` (the legacy bypass path Ticket 27 removes later,
once every source family proves the authoritative path -- this module does
not touch it).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from edgar_warehouse.acquisition.reference_catalog_discovery import (
    REFERENCE_CATALOG_DISCOVERY_SOURCE_FAMILY,
    ReferenceCatalogDriveResult,
    build_reference_catalog_manifest,
    drive_reference_catalog_manifest,
)
from edgar_warehouse.acquisition.reference_catalog_silver_acceptance import (
    REFERENCE_CATALOG_PRODUCER_NAME,
    ReferenceCatalogSilverAcceptanceResult,
    drive_reference_catalog_silver_acceptance,
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
DEFAULT_REGISTRY_VERSION = "reference-catalog-v1"
COMMAND_NAME = "drive-reference-catalog-discovery"

FIXED_SOURCE_NAME_SET_DISCOVERY_POLICY = "fixed_source_name_set"


class UnsupportedDiscoveryPolicy(WarehouseRuntimeError):
    """A covered family declares a discovery_policy this driver does not implement."""


def run_drive_reference_catalog_discovery(args: Any) -> int:
    context = _build_warehouse_context(COMMAND_NAME)
    now = datetime.now(UTC)
    run_id = getattr(args, "run_id", None) or uuid.uuid4().hex
    source_names = getattr(args, "source_names", None)
    arguments = {"source_names": source_names}

    registration = acquisition_command_registration(COMMAND_NAME)
    assert registration is not None, f"{COMMAND_NAME} is not registered"
    scope = registration.resolve_scope(arguments=arguments, now=now, silver_root=None)
    manifest_writes = write_declared_layer_manifests(
        command_name=COMMAND_NAME, context=context, run_id=run_id, arguments=arguments, scope=scope, now=now
    )

    engine = get_engine()
    coverage = active_family_coverage(engine, REFERENCE_CATALOG_DISCOVERY_SOURCE_FAMILY)
    if coverage is not None and coverage.discovery_policy != FIXED_SOURCE_NAME_SET_DISCOVERY_POLICY:
        raise UnsupportedDiscoveryPolicy(
            f"source_family={REFERENCE_CATALOG_DISCOVERY_SOURCE_FAMILY!r} declares "
            f"discovery_policy={coverage.discovery_policy!r}, but this driver "
            f"only implements {FIXED_SOURCE_NAME_SET_DISCOVERY_POLICY!r}"
        )

    required_producers = (
        coverage.required_producers if coverage is not None else (REFERENCE_CATALOG_PRODUCER_NAME,)
    )

    _hydrate_silver_database_from_storage(context)
    db = open_silver_database(context.silver_root)
    try:
        manifest = build_reference_catalog_manifest(
            source_names, universe_label=f"reference-catalog:{run_id}"
        )

        ledger = AcquisitionLedger(engine)
        revisions = SourceRevisionLedger(engine)
        processing = ProcessingLedger(engine)
        finalizer = SilverFinalizer(engine)
        registry = build_active_source_family_registry(engine, identity=context.identity)
        worker_id = getattr(args, "worker_id", None) or f"drive-reference-catalog-discovery-{os.getpid()}"
        lease_seconds = getattr(args, "lease_seconds", None) or DEFAULT_LEASE_SECONDS
        registry_version = getattr(args, "registry_version", None) or DEFAULT_REGISTRY_VERSION

        result = drive_reference_catalog_manifest(
            ledger,
            context.bronze_root,
            registry,
            manifest,
            worker_id=worker_id,
            registry_version=registry_version,
            lease_seconds=lease_seconds,
        )
        silver_result = drive_reference_catalog_silver_acceptance(
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
            REFERENCE_CATALOG_DISCOVERY_SOURCE_FAMILY, now.date()
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
    result: ReferenceCatalogDriveResult, silver_result: ReferenceCatalogSilverAcceptanceResult
) -> dict[str, Any]:
    captured = sum(1 for outcome in result.outcomes if outcome.fetch_state is FetchWorkState.CAPTURED)
    silver_settled = sum(1 for o in silver_result.outcomes if o.error is None and o.settled)
    return {
        "source_name_count": result.manifest.candidate_count,
        "captured": captured,
        "unsettled_source_names": len(result.unsettled_source_names),
        "interval_complete": result.interval_complete,
        "silver_settled": silver_settled,
        "silver_interval_complete": silver_result.interval_complete,
    }


def _result_payload(
    result: ReferenceCatalogDriveResult,
    silver_result: ReferenceCatalogSilverAcceptanceResult,
    *,
    run_id: str,
) -> dict[str, Any]:
    silver_by_source_name = {o.source_name: o for o in silver_result.outcomes}
    return {
        "source_name_count": result.manifest.candidate_count,
        "discovery_manifest_digest": result.manifest.digest,
        "interval_complete": result.interval_complete,
        "silver_interval_complete": silver_result.interval_complete,
        "run_id": run_id,
        "unsettled_source_names": list(result.unsettled_source_names),
        "outcomes": [
            {
                "source_name": outcome.candidate.source_name,
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
                **_silver_fields(silver_by_source_name.get(outcome.candidate.source_name)),
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
