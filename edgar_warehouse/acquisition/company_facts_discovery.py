"""Drive company-facts snapshot capture from a CIK universe (Ticket 22).

Single-phase, unlike ``submissions_discovery.py``: one company-facts JSON
response per CIK is the whole candidate -- there is no pagination inventory
to derive after the fact, so this module issues and drives exactly one Fetch
Decision per CIK with no two-call duplication to extract a shared helper for
(contrast ``submissions_discovery._issue_and_drive_decision``, built because
that module has two call sites; this one has one).

Deliberately does not touch ``fundamentals_ingest.py``'s existing
``run_bootstrap_entity_facts`` -- that is the legacy bypass path Ticket 27
removes only once every source family (including this one) proves the
authoritative path; this module builds a parallel, ledger-gated path.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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

COMPANY_FACTS_DISCOVERY_SOURCE_FAMILY = "company_facts"

DEFAULT_LEASE_SECONDS = 300


@dataclass(frozen=True)
class CompanyFactsCandidate:
    """One CIK's company-facts snapshot."""

    cik: int
    source_url: str

    @property
    def logical_source_key(self) -> str:
        return f"{self.cik}/company-facts"


@dataclass(frozen=True)
class CompanyFactsManifest:
    """A counted, ordered, digested manifest of one bounded CIK universe."""

    universe_label: str
    candidates: tuple[CompanyFactsCandidate, ...]

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def digest(self) -> str:
        canonical = "\n".join(f"{c.cik}|{c.source_url}" for c in self.candidates)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_company_facts_manifest(
    ciks: Sequence[int], *, universe_label: str
) -> CompanyFactsManifest:
    """Seal a CIK universe into an ordered manifest.

    Deduplicates by CIK (a company-facts candidate's business key) and orders
    deterministically so the digest -- and therefore ``cause_reference``
    downstream -- is stable across replays regardless of input order. A
    zero-CIK universe is a valid, complete manifest (candidate_count=0,
    digest of the empty string), not an error -- mirrors Ticket 21's
    complete-empty-scope handling.
    """

    from edgar.urls import build_company_facts_url

    by_cik: dict[int, CompanyFactsCandidate] = {}
    for cik in ciks:
        cik_int = int(cik)
        if cik_int in by_cik:
            continue
        by_cik[cik_int] = CompanyFactsCandidate(
            cik=cik_int, source_url=build_company_facts_url(cik_int)
        )
    ordered = tuple(by_cik[key] for key in sorted(by_cik))
    return CompanyFactsManifest(universe_label=universe_label, candidates=ordered)


def company_facts_candidate_id(cik: int) -> str:
    """Deterministic candidate identity: same CIK -> same id, always.

    Deliberately NOT keyed by a per-run/per-universe label -- mirrors
    ``submissions_discovery.submissions_main_candidate_id``'s own reasoning
    exactly: a CIK's company-facts snapshot is a standing object, not scoped
    to a real interval, so keying by anything run-derived would silently
    break replay-safety (the ledger's per-key ordering needs to recognize a
    replay as the *same* logical key's next observation, not a fresh one).
    """

    return f"company-facts-discovery/{cik}"


@dataclass(frozen=True)
class CompanyFactsCandidateOutcome:
    candidate: CompanyFactsCandidate
    # decision_id/fetch_disposition are None only when the ledger itself
    # rejected the Fetch Decision (e.g. a conflicting replay) -- no decision
    # exists at all for this candidate in that case.
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
class CompanyFactsDriveResult:
    manifest: CompanyFactsManifest
    outcomes: tuple[CompanyFactsCandidateOutcome, ...]

    @property
    def interval_complete(self) -> bool:
        return all(outcome.settled for outcome in self.outcomes)

    @property
    def unsettled_ciks(self) -> tuple[int, ...]:
        return tuple(
            outcome.candidate.cik for outcome in self.outcomes if not outcome.settled
        )


def drive_company_facts_manifest(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    registry: Mapping[str, SourceFamilyPolicy],
    manifest: CompanyFactsManifest,
    *,
    worker_id: str,
    registry_version: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> CompanyFactsDriveResult:
    """Issue one Fetch Decision per CIK and drive it through capture.

    Replay-safe the same way ``discovery.drive_discovery_manifest`` and
    ``submissions_discovery.drive_submissions_manifest`` are: an already-
    ``CAPTURED`` candidate is detected via a cheap, network-free
    ``create_fetch_decision`` status check before any fetch is attempted.
    One candidate's failure is caught and recorded per-candidate so it
    cannot abort the rest of the interval.
    """

    facade = build_capture_facade(ledger, bronze_root, registry, worker_id=worker_id)
    cause_reference = f"company-facts-manifest:{manifest.digest}:registry:{registry_version}"
    outcomes: list[CompanyFactsCandidateOutcome] = []
    for candidate in manifest.candidates:
        request = FetchDecisionRequest(
            candidate_id=company_facts_candidate_id(candidate.cik),
            source_family=COMPANY_FACTS_DISCOVERY_SOURCE_FAMILY,
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
                CompanyFactsCandidateOutcome(
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
                CompanyFactsCandidateOutcome(
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
                CompanyFactsCandidateOutcome(
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
            CompanyFactsCandidateOutcome(
                candidate=candidate,
                decision_id=final_status.decision_id,
                fetch_disposition=final_status.fetch_disposition,
                fetch_state=final_status.fetch_state,
                network_fetched=True,
                error=None,
            )
        )

    return CompanyFactsDriveResult(manifest=manifest, outcomes=tuple(outcomes))
