"""Workflow entrypoint for ``drive-filing-discovery-for-date`` (Ticket 16/19/29)
and ``drive-adv-filing-discovery-for-date`` (Ticket 24 bullet 4).

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

Ticket 24 bullet 4: ``adv_filing`` reuses ``FilingArtifactPolicy`` verbatim
under its own source family/coverage row (own ``in_scope_forms`` -- the 9 ADV
form variants), declared in the Source Family Registry but, until now, never
actually driven -- ADV filings still went through the pre-Ticket-14 legacy
``_run_parse_adv_bronze`` path. The mechanism this module implements
(sealed-daily-index -> manifest -> ledger-gated capture -> Silver
acceptance) is already fully generic in ``discovery.py``/``silver_acceptance.py``
(both already take ``source_family``/``required_producers`` as parameters,
not hardcoded constants) -- the only thing hardcoded to ``filing_artifact``
was this workflow function itself. ``_run_daily_index_driven_discovery``
below is that shared body, parameterized by family/command name; both public
entry points are thin wrappers over it -- Strategy reuse across families,
same discipline ``source_family_registry.py``'s own reuse note already
established for the Policy layer, not a new Template Method superclass.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
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
    active_family_coverage,
    active_in_scope_forms,
    build_active_source_family_registry,
)
from edgar_warehouse.acquisition.revisions import SourceRevisionLedger
from edgar_warehouse.acquisition.silver_acceptance import (
    FILING_ARTIFACT_PRODUCER_NAME,
    FilingArtifactSilverAcceptanceResult,
    drive_filing_artifact_silver_acceptance,
)
from edgar_warehouse.acquisition.source_family_registry import (
    ADV_FILING_SOURCE_FAMILY,
    FILING_ARTIFACT_SOURCE_FAMILY,
)
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
ADV_FILING_DEFAULT_REGISTRY_VERSION = "adv_filing-v1"
ADV_FILING_COMMAND_NAME = "drive-adv-filing-discovery-for-date"

# Ticket 32 bullet 1: the only discovery mechanism this module implements --
# a covered family's registry coverage declaring anything else is a real
# configuration error, not inert metadata to read and ignore.
DAILY_INDEX_DRIVEN_DISCOVERY_POLICY = "daily_index_driven"


class UnsupportedDiscoveryPolicy(WarehouseRuntimeError):
    """A covered family declares a discovery_policy this driver does not implement."""


def run_drive_filing_discovery_for_date(args: Any) -> int:
    return _run_daily_index_driven_discovery(
        args,
        source_family=FILING_ARTIFACT_SOURCE_FAMILY,
        command_name=COMMAND_NAME,
        default_registry_version=DEFAULT_REGISTRY_VERSION,
        default_required_producer=FILING_ARTIFACT_PRODUCER_NAME,
    )


def run_drive_adv_filing_discovery_for_date(args: Any) -> int:
    return _run_daily_index_driven_discovery(
        args,
        source_family=ADV_FILING_SOURCE_FAMILY,
        command_name=ADV_FILING_COMMAND_NAME,
        default_registry_version=ADV_FILING_DEFAULT_REGISTRY_VERSION,
        default_required_producer=FILING_ARTIFACT_PRODUCER_NAME,
    )


@dataclass
class GatedDiscoveryOutcome:
    """Ticket 46: the shared core's result, extracted so a second caller
    (daily-incremental's own in-process gated capture) can inspect
    completeness without going through this module's stdout/exit-code
    contract, which is specific to running as a standalone CLI command.
    """

    interval_complete: bool
    result: DiscoveryDriveResult
    silver_result: FilingArtifactSilverAcceptanceResult


def run_gated_discovery_for_business_date(
    *,
    context: Any,
    db: Any,
    engine: Any,
    business_date: str,
    business_date_value: date,
    source_family: str,
    default_registry_version: str,
    default_required_producer: str,
    worker_id: str,
    lease_seconds: int,
    registry_version: str,
) -> GatedDiscoveryOutcome:
    """Ticket 16/19/29's ledger-gated discovery/capture/Silver-acceptance
    body for one already-sealed business date, extracted (Ticket 46) so both
    this module's own CLI entrypoints (which additionally hydrate, publish,
    and write run manifests around this) and daily-incremental's in-process
    gated capture (which reuses its own already-open Silver connection and
    does its own manifest/publish bookkeeping) can share one implementation.
    Caller owns hydrate/publish/db lifecycle -- this function assumes `db`
    is already open and does not close or publish it.
    """
    # Ticket 20: which forms are in scope now comes from the active Source
    # Family Registry version, not discovery.py's own hardcoded default --
    # a covered-but-not-yet-activated family, or one 'remove'd, must not
    # silently fall back to acquiring everything DISCOVERY_IN_SCOPE_FORMS
    # would have covered before the registry existed.
    in_scope_forms = active_in_scope_forms(
        engine, source_family, as_of_date=business_date_value
    )
    # Ticket 32 bullet 1: the registry's discovery_policy and
    # required_producers become real gates here, not inert audit fields.
    coverage = active_family_coverage(
        engine, source_family, as_of_date=business_date_value
    )
    if coverage is not None and coverage.discovery_policy != DAILY_INDEX_DRIVEN_DISCOVERY_POLICY:
        raise UnsupportedDiscoveryPolicy(
            f"source_family={source_family!r} declares "
            f"discovery_policy={coverage.discovery_policy!r}, but this driver "
            f"only implements {DAILY_INDEX_DRIVEN_DISCOVERY_POLICY!r}"
        )
    required_producers = (
        coverage.required_producers
        if coverage is not None
        else (default_required_producer,)
    )

    rows = _load_sealed_discovery_rows(db, business_date)
    manifest = build_discovery_manifest(
        rows, business_date=business_date, source_family=source_family, in_scope_forms=in_scope_forms
    )

    ledger = AcquisitionLedger(engine)
    revisions = SourceRevisionLedger(engine)
    processing = ProcessingLedger(engine)
    finalizer = SilverFinalizer(engine)
    registry = build_active_source_family_registry(
        engine, identity=context.identity, as_of_date=business_date_value
    )

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
        ledger,
        revisions,
        processing,
        finalizer,
        db,
        result,
        required_producers=required_producers,
    )

    if result.interval_complete and silver_result.interval_complete:
        # Ticket 20's catch-up obligation, advanced by the exact same
        # completeness signal Ticket 29 already proved live end-to-end.
        SourceRegistryLedger(engine).record_catchup_progress(
            source_family, business_date_value
        )

    return GatedDiscoveryOutcome(
        interval_complete=result.interval_complete and silver_result.interval_complete,
        result=result,
        silver_result=silver_result,
    )


def run_filing_artifact_gated_capture_for_business_date(
    *,
    context: Any,
    db: Any,
    business_date: str,
    run_id: str,
) -> GatedDiscoveryOutcome:
    """Ticket 46: filing_artifact's gated discovery/capture, run in-process
    against daily-incremental's own already-open Silver connection.

    Deliberately in-process rather than a separate Step Functions state --
    see Ticket 46's Answer for the full rationale, but the load-bearing
    reason is the shared ``sec_fetch_active`` lease: this call makes real SEC
    network fetches (via ``drive_discovery_manifest``), and daily-incremental's
    ASL already holds that cross-command lease around the whole ECS task this
    runs inside. A separate Step Functions state would either fetch SEC data
    outside the lease window entirely, or require inserting a new state into
    daily-incremental's lease-acquire/release/Catch region -- the exact
    fragility this ticket was split out to avoid touching.

    Raises on any failure (including ``UnsupportedDiscoveryPolicy``) --
    unlike this module's own CLI entrypoints, this function does not decide
    failure isolation. Ticket 46's caller (daily-incremental's own per-date
    loop) wraps this call and folds any exception into its own metrics
    instead of failing the whole command, so it can never trip the state
    machine's ``MaxAttempts: 3`` retry on its own account. That isolation is
    about failure only -- a *successful* call is not passive observation:
    like the CLI path it shares this core with, it calls
    ``SourceRegistryLedger.record_catchup_progress`` on a completed
    interval, the same real catch-up-progress signal Ticket 27's
    removal-evidence bullets gate on. Turning this on for Ticket 10
    Decision 2's verification window deliberately advances that state, not
    just observes it (/code-review's Spec pass caught this docstring
    originally calling it "observation-only," which understated the effect).
    """
    engine = get_engine()
    business_date_value = date.fromisoformat(business_date)
    return run_gated_discovery_for_business_date(
        context=context,
        db=db,
        engine=engine,
        business_date=business_date,
        business_date_value=business_date_value,
        source_family=FILING_ARTIFACT_SOURCE_FAMILY,
        default_registry_version=DEFAULT_REGISTRY_VERSION,
        default_required_producer=FILING_ARTIFACT_PRODUCER_NAME,
        worker_id=f"daily-incremental-gated-capture-{run_id}",
        lease_seconds=DEFAULT_LEASE_SECONDS,
        registry_version=DEFAULT_REGISTRY_VERSION,
    )


def _run_daily_index_driven_discovery(
    args: Any,
    *,
    source_family: str,
    command_name: str,
    default_registry_version: str,
    default_required_producer: str,
) -> int:
    context = _build_warehouse_context(command_name)
    now = datetime.now(UTC)
    run_id = getattr(args, "run_id", None) or uuid.uuid4().hex
    business_date = str(args.business_date)
    business_date_value = date.fromisoformat(business_date)
    arguments = {"business_date": business_date}

    registration = acquisition_command_registration(command_name)
    assert registration is not None, f"{command_name} is not registered"
    scope = registration.resolve_scope(arguments=arguments, now=now, silver_root=None)
    manifest_writes = write_declared_layer_manifests(
        command_name=command_name, context=context, run_id=run_id, arguments=arguments, scope=scope, now=now
    )

    # The Silver connection stays open across discovery + capture + revision
    # + processing + Silver finalization (Ticket 29): finalize_filing_
    # artifact_candidate needs to write and read back sec_raw_object on the
    # same local candidate this process eventually publishes. Only closed
    # once every candidate has settled, then published as one unit -- not
    # per-candidate, matching every other silver-writing command's
    # hydrate-once/publish-once shape.
    engine = get_engine()
    worker_id = getattr(args, "worker_id", None) or f"{command_name}-{os.getpid()}"
    lease_seconds = getattr(args, "lease_seconds", None) or DEFAULT_LEASE_SECONDS
    registry_version = getattr(args, "registry_version", None) or default_registry_version

    _hydrate_silver_database_from_storage(context)
    db = open_silver_database(context.silver_root)
    try:
        # Ticket 46 extracted the discovery/capture/Silver-acceptance body
        # below into run_gated_discovery_for_business_date, shared with
        # daily-incremental's own in-process gated capture -- this call is
        # behavior-identical to the inline body it replaced.
        outcome = run_gated_discovery_for_business_date(
            context=context,
            db=db,
            engine=engine,
            business_date=business_date,
            business_date_value=business_date_value,
            source_family=source_family,
            default_registry_version=default_registry_version,
            default_required_producer=default_required_producer,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            registry_version=registry_version,
        )
    finally:
        db.close()

    result = outcome.result
    silver_result = outcome.silver_result

    _publish_silver_database_with_retry(context)

    write_consolidated_run_manifest(
        command_name=command_name,
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
