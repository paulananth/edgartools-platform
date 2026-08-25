"""Drive ADV bulk-dataset capture (IAPD ADV bulk archives + Firm Roster
archives) through the Ticket 14/15 ledger (Ticket 24).

Both source kinds share one identity model -- complete-snapshot-per-
``dataset_period`` -- and therefore one Source Family
(``ADV_BULK_DATASET_SOURCE_FAMILY``), same shape as
``reference_catalog_discovery.py``'s fixed-source-name-set family. They
differ from that sibling in one way: knowing *which concrete archive URL* to
fetch for the newest period(s) itself requires a network read (SEC/IAPD's
``reports_metadata.json`` for ADV bulk, the Firm Roster listing page for
roster) -- there is no fixed URL list to build a manifest from directly.
That resolution step is treated the same way ``drive_filing_discovery.py``
treats the SEC daily index: a cheap, non-Bronze-worthy discovery read, not
itself a ledger-gated Fetch Decision. Only the real archive download that
follows is ledger-gated, via ``AdvBulkDatasetPolicy``.

Reuses ``adv_bulk_fetch.py``/``firm_roster_fetch.py``'s own period-selection
logic (``rolling_window_periods``/``periods_to_fetch``/``select_downloadable``,
``latest_available_period``/``period_to_fetch``/``select_downloadable_variants``)
unmodified rather than reimplementing it -- those functions already encode
the real-world lessons (13-month rolling window, roster's single-latest-
period-only contract, no-op-without-force independence) this module must not
regress. ``already_ingested`` is always passed as an empty set here: unlike
the legacy fetch-and-upload path, replay-safety here comes entirely from
``create_fetch_decision``'s idempotent CAPTURED short-circuit (same as every
other family in this package), not from a pre-filter -- so the manifest
always covers the full rolling window / latest period, and the ledger is
what makes a re-run of an already-captured period a no-op.

Firm Roster publishes two disjoint-by-CRD variants per period (registered
advisers, exempt reporting advisers) -- each variant is its own candidate,
its own Fetch Decision, its own archive download.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date

from edgar_warehouse.acquisition.facade import SourceFamilyPolicy, build_capture_facade
from edgar_warehouse.acquisition.ledger import (
    TERMINAL_NO_DOWNLOAD_DISPOSITIONS,
    AcquisitionLedger,
    DecisionCause,
    DecisionOwnerRole,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
    execute_source_request,
)
from edgar_warehouse.application.adv_bulk_fetch import (
    periods_to_fetch,
    rolling_window_periods,
    select_downloadable,
)
from edgar_warehouse.application.firm_roster_fetch import (
    period_to_fetch,
    select_downloadable_variants,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation

ADV_BULK_DATASET_DISCOVERY_SOURCE_FAMILY = "adv_bulk_dataset"

DEFAULT_LEASE_SECONDS = 300

_ADV_BULK_ARCHIVE_URL = "https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/{year}/{file_name}"
_FIRM_ROSTER_HOST = "https://www.sec.gov"


@dataclass(frozen=True)
class AdvBulkDatasetCandidate:
    """One resolved, concrete archive download -- an ADV bulk archive for a
    dataset_period, or one Firm Roster variant (registered/exempt) for a
    dataset_period.
    """

    source_kind: str  # "adv_bulk" | "firm_roster"
    dataset_period: str
    source_url: str
    variant: str | None = None  # only set for source_kind="firm_roster"

    @property
    def logical_source_key(self) -> str:
        if self.source_kind == "firm_roster":
            return f"adv-firm-roster/{self.variant}/{self.dataset_period}"
        return f"adv-bulk-archive/{self.dataset_period}"


@dataclass(frozen=True)
class AdvBulkDatasetManifest:
    universe_label: str
    candidates: tuple[AdvBulkDatasetCandidate, ...]
    unpublished_periods: tuple[str, ...]

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def digest(self) -> str:
        canonical = "\n".join(
            f"{c.source_kind}|{c.dataset_period}|{c.variant or ''}|{c.source_url}"
            for c in self.candidates
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_adv_bulk_dataset_manifest(
    *,
    universe_label: str,
    as_of: date,
    fetch_reports_metadata_bytes: Callable[[], bytes],
    fetch_listing_bytes: Callable[[], bytes],
    window_months: int = 13,
) -> AdvBulkDatasetManifest:
    """Resolve the full rolling window of ADV bulk periods plus the single
    latest Firm Roster period into concrete, fetchable candidates.

    Both metadata/listing reads are pure discovery inputs, not themselves
    captured as Bronze evidence -- see this module's own docstring. A period
    the metadata/listing doesn't (yet) publish is recorded in
    ``unpublished_periods``, not treated as an error (bullet 3's valid-empty
    contract): SEC/IAPD publishing the current month's archive a few days
    late is normal, expected behavior.
    """

    from edgar_warehouse.application.adv_bulk_fetch import parse_reports_metadata
    from edgar_warehouse.application.firm_roster_fetch import (
        latest_available_period,
        parse_firm_roster_listing,
    )

    window = rolling_window_periods(as_of, window_months=window_months)
    bulk_periods = periods_to_fetch(window, already_ingested=set())
    metadata = parse_reports_metadata(fetch_reports_metadata_bytes())
    bulk_targets, unpublished = select_downloadable(metadata, bulk_periods)

    listing = parse_firm_roster_listing(fetch_listing_bytes().decode("utf-8"))
    latest_period = latest_available_period(listing)
    roster_period = period_to_fetch(latest_period, already_ingested=set())

    candidates: list[AdvBulkDatasetCandidate] = [
        AdvBulkDatasetCandidate(
            source_kind="adv_bulk",
            dataset_period=target.dataset_period,
            source_url=_ADV_BULK_ARCHIVE_URL.format(year=target.year, file_name=target.file_name),
        )
        for target in bulk_targets
    ]
    if roster_period is not None:
        variants = select_downloadable_variants(listing, roster_period)
        for variant, href in sorted(variants.items()):
            candidates.append(
                AdvBulkDatasetCandidate(
                    source_kind="firm_roster",
                    dataset_period=roster_period,
                    variant=variant,
                    source_url=f"{_FIRM_ROSTER_HOST}{href}",
                )
            )

    return AdvBulkDatasetManifest(
        universe_label=universe_label,
        candidates=tuple(candidates),
        unpublished_periods=tuple(unpublished),
    )


def adv_bulk_dataset_candidate_id(candidate: AdvBulkDatasetCandidate) -> str:
    """Deterministic candidate identity, keyed only by stable source shape
    (kind/period/variant) -- never run-derived, same replay-safety
    discipline as every prior family in this package.
    """

    if candidate.source_kind == "firm_roster":
        return f"adv-bulk-dataset-discovery/firm-roster/{candidate.variant}/{candidate.dataset_period}"
    return f"adv-bulk-dataset-discovery/adv-bulk/{candidate.dataset_period}"


@dataclass(frozen=True)
class AdvBulkDatasetCandidateOutcome:
    candidate: AdvBulkDatasetCandidate
    decision_id: str | None
    fetch_disposition: FetchDisposition | None
    fetch_state: FetchWorkState | None
    network_fetched: bool
    error: str | None

    @property
    def settled(self) -> bool:
        return (
            self.fetch_state is FetchWorkState.CAPTURED
            or self.fetch_disposition in TERMINAL_NO_DOWNLOAD_DISPOSITIONS
        )


@dataclass(frozen=True)
class AdvBulkDatasetDriveResult:
    manifest: AdvBulkDatasetManifest
    outcomes: tuple[AdvBulkDatasetCandidateOutcome, ...]

    @property
    def interval_complete(self) -> bool:
        return all(outcome.settled for outcome in self.outcomes)


def drive_adv_bulk_dataset_manifest(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    registry: Mapping[str, SourceFamilyPolicy],
    manifest: AdvBulkDatasetManifest,
    *,
    worker_id: str,
    registry_version: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> AdvBulkDatasetDriveResult:
    """Issue one Fetch Decision per resolved archive and drive it through
    capture -- same replay-safe, per-candidate-fault-isolated shape as
    ``reference_catalog_discovery.drive_reference_catalog_manifest``.
    """

    facade = build_capture_facade(ledger, bronze_root, registry, worker_id=worker_id)
    cause_reference = f"adv-bulk-dataset-manifest:{manifest.digest}:registry:{registry_version}"
    outcomes: list[AdvBulkDatasetCandidateOutcome] = []
    for candidate in manifest.candidates:
        request = FetchDecisionRequest(
            candidate_id=adv_bulk_dataset_candidate_id(candidate),
            source_family=ADV_BULK_DATASET_DISCOVERY_SOURCE_FAMILY,
            logical_source_key=candidate.logical_source_key,
            source_url=candidate.source_url,
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference=cause_reference,
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
            owner_role=DecisionOwnerRole.ACQUISITION_COORDINATOR,
        )
        try:
            status = ledger.create_fetch_decision(request)
        except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
            outcomes.append(
                AdvBulkDatasetCandidateOutcome(
                    candidate=candidate,
                    decision_id=None,
                    fetch_disposition=None,
                    fetch_state=None,
                    network_fetched=False,
                    error=str(error),
                )
            )
            continue

        if status.fetch_state is FetchWorkState.CAPTURED:
            outcomes.append(
                AdvBulkDatasetCandidateOutcome(
                    candidate=candidate,
                    decision_id=status.decision_id,
                    fetch_disposition=status.fetch_disposition,
                    fetch_state=status.fetch_state,
                    network_fetched=False,
                    error=None,
                )
            )
            continue

        try:
            result = execute_source_request(
                ledger, request, facade, worker_id=worker_id, lease_seconds=lease_seconds
            )
            final_status = ledger.source_change_status(result.status.decision_id)
        except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
            failed_status = ledger.source_change_status(status.decision_id)
            outcomes.append(
                AdvBulkDatasetCandidateOutcome(
                    candidate=candidate,
                    decision_id=failed_status.decision_id,
                    fetch_disposition=failed_status.fetch_disposition,
                    fetch_state=failed_status.fetch_state,
                    network_fetched=True,
                    error=str(error),
                )
            )
            continue

        outcomes.append(
            AdvBulkDatasetCandidateOutcome(
                candidate=candidate,
                decision_id=final_status.decision_id,
                fetch_disposition=final_status.fetch_disposition,
                fetch_state=final_status.fetch_state,
                network_fetched=True,
                error=None,
            )
        )

    return AdvBulkDatasetDriveResult(manifest=manifest, outcomes=tuple(outcomes))
