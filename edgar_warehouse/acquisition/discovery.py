"""Drive filing capture from a sealed SEC discovery observation (Ticket 16).

Turns an already-captured, already-checkpointed SEC daily form index -- the
existing ``load-daily-form-index-for-date`` command's own output
(``stg_daily_index_filing`` rows, sealed by a ``sec_daily_index_checkpoint``
row with ``status='succeeded'``) -- into a counted, ordered, digested
Discovery Manifest, and issues exactly one Ticket 14 Fetch Decision per
candidate before driving in-scope candidates through Ticket 15's ledger-gated
capture Facade.

This module deliberately does not re-fetch or re-stage the daily index
itself: that legacy discovery/bronze path is its own future migration
(spec.md's per-source-family vertical-slice sequencing), out of scope here.
Ticket 16 only adds the sealing/decision-issuing layer on top of discovery
evidence that already exists, mirroring how Ticket 15 added the capture
Facade on top of an already-approved source adapter without touching
discovery itself.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

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
from edgar_warehouse.infrastructure.object_storage import StorageLocation

FILING_DISCOVERY_SOURCE_FAMILY = "filing_artifact"

# Ticket 16's minimal real slice drives the ownership forms -- the same
# family already proven end-to-end through Ticket 15's manual smoke test.
# Mirrors warehouse_orchestrator.OWNERSHIP_FORMS deliberately by value, not
# import: this module stays independent of the ~292KB legacy orchestrator so
# the new vertical slice does not re-acquire that coupling. Widening the
# in-scope form set to other families is later migration-ticket work
# (spec.md's per-source-family vertical slices), not this ticket's job.
DISCOVERY_IN_SCOPE_FORMS = frozenset({"3", "3/A", "4", "4/A", "5", "5/A"})

DEFAULT_LEASE_SECONDS = 300


@dataclass(frozen=True)
class DiscoveryCandidate:
    """One row of a sealed discovery observation, resolved to a capture target."""

    accession_number: str
    cik: int
    form: str
    source_url: str
    in_scope: bool

    @property
    def logical_source_key(self) -> str:
        return f"{self.cik}/{self.accession_number}/full-submission-text"


@dataclass(frozen=True)
class DiscoveryManifest:
    """A counted, ordered, digested Discovery Manifest for one bounded interval."""

    business_date: str
    source_family: str
    candidates: tuple[DiscoveryCandidate, ...]

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def digest(self) -> str:
        canonical = "\n".join(
            f"{c.accession_number}|{c.cik}|{c.form}|{c.source_url}|{c.in_scope}"
            for c in self.candidates
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_discovery_manifest(
    rows: Sequence[Mapping[str, Any]],
    *,
    business_date: str,
    source_family: str = FILING_DISCOVERY_SOURCE_FAMILY,
    in_scope_forms: frozenset[str] = DISCOVERY_IN_SCOPE_FORMS,
) -> DiscoveryManifest:
    """Seal ``stg_daily_index_filing``-shaped rows into an ordered manifest.

    Deduplicates by accession number (a discovery observation's business
    key) and orders deterministically so the digest -- and therefore the
    candidate identities derived from it downstream -- is stable across
    replays regardless of the input rows' original order.
    """

    by_accession: dict[str, DiscoveryCandidate] = {}
    for row in rows:
        accession_number = str(row["accession_number"])
        if accession_number in by_accession:
            continue
        form = str(row["form"])
        by_accession[accession_number] = DiscoveryCandidate(
            accession_number=accession_number,
            cik=int(row["cik"]),
            form=form,
            source_url=str(row["filing_txt_url"]),
            in_scope=form in in_scope_forms,
        )
    ordered = tuple(by_accession[key] for key in sorted(by_accession))
    return DiscoveryManifest(
        business_date=business_date, source_family=source_family, candidates=ordered
    )


@dataclass(frozen=True)
class DiscoveryCandidateOutcome:
    candidate: DiscoveryCandidate
    # decision_id/fetch_disposition are None only when the ledger itself
    # rejected the Fetch Decision (e.g. a conflicting replay) -- no decision
    # exists at all for this candidate in that case, not just an unfetched one.
    decision_id: str | None
    fetch_disposition: FetchDisposition | None
    fetch_state: FetchWorkState | None
    network_fetched: bool
    error: str | None

    @property
    def settled(self) -> bool:
        # Reuse the ledger's own terminal-disposition set rather than
        # re-listing it here, so the two stay in lockstep instead of
        # silently diverging if a disposition is ever added there.
        return (
            self.fetch_state is FetchWorkState.CAPTURED
            or self.fetch_disposition in TERMINAL_NO_DOWNLOAD_DISPOSITIONS
        )


@dataclass(frozen=True)
class DiscoveryDriveResult:
    manifest: DiscoveryManifest
    outcomes: tuple[DiscoveryCandidateOutcome, ...]

    @property
    def interval_complete(self) -> bool:
        return all(outcome.settled for outcome in self.outcomes)

    @property
    def unsettled_candidate_ids(self) -> tuple[str, ...]:
        return tuple(
            outcome.candidate.accession_number
            for outcome in self.outcomes
            if not outcome.settled
        )


def discovery_candidate_id(
    business_date: str, accession_number: str, *, source_family: str = FILING_DISCOVERY_SOURCE_FAMILY
) -> str:
    """Deterministic candidate identity: same interval + accession + family -> same id.

    This is what makes replaying the same discovery evidence idempotent at
    the ledger layer (``AcquisitionLedger.create_fetch_decision`` is keyed
    globally by ``candidate_id``, not scoped by ``source_family``) without
    this module needing its own dedupe state.

    Ticket 24 bullet 4 found a real, previously-unexercised bug here: this
    module was written when only ``filing_artifact`` ever drove daily-index
    discovery, so a candidate_id keyed on interval+accession alone was
    accidentally already globally unique. That stopped being true once
    ``adv_filing`` reused the same sealed daily-index observation: the same
    business_date + accession pair is a real candidate in *both* families'
    manifests (one in-scope, one excluded), so without source_family in the
    id, the second family's driver collided with the first's already-
    registered decision for that accession -- reproduced live while wiring
    the new ``drive-adv-filing-discovery-for-date`` driver, not a
    hypothetical.

    The fix deliberately does NOT change ``filing_artifact``'s own id format
    (still ``filing-discovery/{business_date}/{accession_number}``, no
    family segment): Ticket 29 already ran a real prod dry run that wrote
    live ledger rows under that exact format, and this id is exactly what
    makes a re-run recognize an already-CAPTURED candidate without a real
    SEC fetch (this file's own "SEC data idempotency" policy, CLAUDE.md).
    Changing the format for an already-covered family would silently break
    that recognition on the very next replay -- a new candidate_id means no
    ``existing`` row is found, a fresh Fetch Decision is created, and the
    facade re-fetches from SEC over the network. Every other family's id
    does include the family segment, since no other family has any live
    ledger history whose format this would need to preserve.
    """

    if source_family == FILING_DISCOVERY_SOURCE_FAMILY:
        return f"filing-discovery/{business_date}/{accession_number}"
    return f"filing-discovery/{source_family}/{business_date}/{accession_number}"


def drive_discovery_manifest(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    registry: Mapping[str, SourceFamilyPolicy],
    manifest: DiscoveryManifest,
    *,
    worker_id: str,
    registry_version: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    on_progress: Callable[[int, int], None] | None = None,
) -> DiscoveryDriveResult:
    """Issue one Fetch Decision per candidate and drive in-scope ones through capture.

    Replay-safe: an already-``CAPTURED`` candidate is detected via a cheap,
    network-free ``create_fetch_decision`` status check before any fetch is
    attempted, so replaying the same manifest performs no duplicate decision,
    network request, or logical source work (Ticket 16's bullet 4). A single
    candidate's decision rejection (e.g. a conflicting replay) or capture
    failure is caught and recorded per-candidate so it cannot abort the rest
    of the interval (Ticket 16's bullet 3: the interval itself simply stays
    incomplete until every candidate reaches a settled outcome).

    ``on_progress``, when provided, is called after every candidate settles
    with ``(processed, candidate_count)``. Callers own cadence and logging
    (Ticket 48); this loop does not emit events itself.
    """

    facade = build_capture_facade(ledger, bronze_root, registry, worker_id=worker_id)
    cause_reference = f"discovery-manifest:{manifest.digest}:registry:{registry_version}"
    outcomes: list[DiscoveryCandidateOutcome] = []
    candidate_count = manifest.candidate_count
    for candidate in manifest.candidates:
        try:
            request = _build_fetch_decision_request(candidate, cause_reference, manifest)
            try:
                status = ledger.create_fetch_decision(request)
            except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
                # A conflicting replay (e.g. a different registry_version reused
                # for an already-decided candidate) or another ledger-level
                # rejection leaves no decision at all for this candidate -- it
                # stays unsettled, blocking interval completion, rather than
                # aborting every other candidate in this same drive call.
                outcomes.append(
                    DiscoveryCandidateOutcome(
                        candidate=candidate,
                        decision_id=None,
                        fetch_disposition=None,
                        fetch_state=None,
                        network_fetched=False,
                        error=str(error),
                    )
                )
                continue
            if not candidate.in_scope or status.fetch_state is FetchWorkState.CAPTURED:
                outcomes.append(
                    DiscoveryCandidateOutcome(
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
                    ledger,
                    request,
                    facade,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                )
                # execute_source_request's own status snapshot is taken at LEASED
                # time, before the facade runs (see tests/acquisition/test_facade.py's
                # identical re-query) -- read the ledger back to get the true
                # post-finalize fetch_state instead of trusting a stale value.
                final_status = ledger.source_change_status(result.status.decision_id)
                outcomes.append(
                    DiscoveryCandidateOutcome(
                        candidate=candidate,
                        decision_id=final_status.decision_id,
                        fetch_disposition=final_status.fetch_disposition,
                        fetch_state=final_status.fetch_state,
                        network_fetched=True,
                        error=None,
                    )
                )
            except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
                failed_status = ledger.source_change_status(status.decision_id)
                outcomes.append(
                    DiscoveryCandidateOutcome(
                        candidate=candidate,
                        decision_id=failed_status.decision_id,
                        fetch_disposition=failed_status.fetch_disposition,
                        fetch_state=failed_status.fetch_state,
                        network_fetched=True,
                        error=str(error),
                    )
                )
        finally:
            if on_progress is not None:
                on_progress(len(outcomes), candidate_count)
    return DiscoveryDriveResult(manifest=manifest, outcomes=tuple(outcomes))


def _build_fetch_decision_request(
    candidate: DiscoveryCandidate, cause_reference: str, manifest: DiscoveryManifest
) -> FetchDecisionRequest:
    candidate_id = discovery_candidate_id(
        manifest.business_date, candidate.accession_number, source_family=manifest.source_family
    )
    if not candidate.in_scope:
        return FetchDecisionRequest(
            candidate_id=candidate_id,
            source_family=manifest.source_family,
            logical_source_key=candidate.logical_source_key,
            source_url=candidate.source_url,
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference=cause_reference,
            disposition=FetchDisposition.OUT_OF_SCOPE,
            blocker=None,
            next_action="NONE",
            owner_role=DecisionOwnerRole.ACQUISITION_COORDINATOR,
            scope_proof_reference=(
                f"discovery-manifest:{manifest.digest}:excluded-form:{candidate.form}"
            ),
        )
    return FetchDecisionRequest(
        candidate_id=candidate_id,
        source_family=manifest.source_family,
        logical_source_key=candidate.logical_source_key,
        source_url=candidate.source_url,
        cause=DecisionCause.CAPTURED_DISCOVERY,
        cause_reference=cause_reference,
        disposition=FetchDisposition.FETCH_AUTHORIZED,
        blocker=None,
        next_action="FETCH_SOURCE",
        owner_role=DecisionOwnerRole.ACQUISITION_COORDINATOR,
    )
