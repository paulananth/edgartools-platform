"""Drive submissions main-snapshot + pagination capture from a CIK universe
(Ticket 21).

Mirrors ``discovery.py``'s per-candidate fault isolation and
``execute_source_request``/Facade call shape (Ticket 16's proven pattern),
but cannot reuse that module directly: filing discovery is single-wave
(daily-index rows already name every candidate URL up front), while
submissions discovery is two-phase per CIK -- a company's pagination files
are not knowable until its main snapshot has actually been fetched and
parsed. See ``source_family_registry.py``'s own docstring for why one
Strategy (``SubmissionsPolicy``) still serves both logical-key kinds despite
this module's two-phase driving loop: the Facade's one-URL-per-call contract
is unchanged, only the caller now issues that call twice, sequentially, per
CIK.

Deliberately does not touch ``warehouse_orchestrator.py``'s existing
``_capture_submission_bronze_snapshots``/``_run_submissions_bronze_then_
silver`` -- that is the legacy bypass path Ticket 27 removes only once every
source family (including this one) proves the authoritative path; this
module builds a parallel, ledger-gated path, it does not modify or reuse the
legacy one's fetch logic.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

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

SUBMISSIONS_DISCOVERY_SOURCE_FAMILY = "submissions"

DEFAULT_LEASE_SECONDS = 300


@dataclass(frozen=True)
class SubmissionsCandidate:
    """One CIK's submissions main snapshot -- the only candidate kind this
    module's own manifest carries. Pagination candidates are not knowable
    until the main snapshot is actually fetched, so they are not manifest
    members; they are issued by ``drive_submissions_manifest`` itself,
    per-CIK, after that CIK's main fetch settles (see module docstring).
    """

    cik: int
    source_url: str

    @property
    def logical_source_key(self) -> str:
        return f"{self.cik}/main"


@dataclass(frozen=True)
class SubmissionsManifest:
    """A counted, ordered, digested manifest of one bounded CIK universe."""

    universe_label: str
    candidates: tuple[SubmissionsCandidate, ...]

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def digest(self) -> str:
        canonical = "\n".join(
            f"{c.cik}|{c.source_url}" for c in self.candidates
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_submissions_manifest(
    ciks: Sequence[int], *, universe_label: str
) -> SubmissionsManifest:
    """Seal a CIK universe into an ordered manifest.

    Deduplicates by CIK (a submissions candidate's business key) and orders
    deterministically so the digest -- and therefore ``cause_reference``
    downstream -- is stable across replays regardless of input order.
    """

    from edgar.urls import build_submissions_url

    by_cik: dict[int, SubmissionsCandidate] = {}
    for cik in ciks:
        cik_int = int(cik)
        if cik_int in by_cik:
            continue
        by_cik[cik_int] = SubmissionsCandidate(
            cik=cik_int, source_url=build_submissions_url(cik_int)
        )
    ordered = tuple(by_cik[key] for key in sorted(by_cik))
    return SubmissionsManifest(universe_label=universe_label, candidates=ordered)


@dataclass(frozen=True)
class PaginationOutcome:
    """One pagination file's fetch outcome, resolved during a main
    candidate's own drive step (its file names aren't known until the main
    payload is parsed, so they never appear in the manifest itself).
    """

    file_name: str
    decision_id: str | None
    fetch_state: FetchWorkState | None
    network_fetched: bool
    error: str | None

    @property
    def settled(self) -> bool:
        return self.fetch_state is FetchWorkState.CAPTURED


@dataclass(frozen=True)
class SubmissionsCandidateOutcome:
    candidate: SubmissionsCandidate
    # decision_id/fetch_disposition are None only when the ledger itself
    # rejected the main Fetch Decision (e.g. a conflicting replay) -- no
    # decision exists at all for this candidate in that case.
    decision_id: str | None
    fetch_disposition: FetchDisposition | None
    fetch_state: FetchWorkState | None
    network_fetched: bool
    error: str | None
    pagination_outcomes: tuple[PaginationOutcome, ...] = field(default_factory=tuple)

    @property
    def settled(self) -> bool:
        """The main decision reached a terminal state AND (when CAPTURED)
        every pagination file it declared also settled -- Ticket 21 bullet
        2: a main snapshot's own completeness is gated on its pagination
        files, not just on its own fetch reaching CAPTURED.
        """

        main_settled = (
            self.fetch_state is FetchWorkState.CAPTURED
            or self.fetch_disposition in TERMINAL_NO_DOWNLOAD_DISPOSITIONS
        )
        if not main_settled:
            return False
        if self.fetch_state is not FetchWorkState.CAPTURED:
            return True
        return all(p.settled for p in self.pagination_outcomes)

    @property
    def pagination_complete(self) -> bool:
        return all(p.settled for p in self.pagination_outcomes)


@dataclass(frozen=True)
class SubmissionsDriveResult:
    manifest: SubmissionsManifest
    outcomes: tuple[SubmissionsCandidateOutcome, ...]

    @property
    def interval_complete(self) -> bool:
        return all(outcome.settled for outcome in self.outcomes)

    @property
    def unsettled_ciks(self) -> tuple[int, ...]:
        return tuple(
            outcome.candidate.cik for outcome in self.outcomes if not outcome.settled
        )


def submissions_main_candidate_id(cik: int) -> str:
    """Deterministic candidate identity: same CIK -> same id, always.

    Deliberately NOT keyed by a per-run/per-universe label the way
    ``discovery.discovery_candidate_id`` is keyed by ``business_date`` --
    a daily filing candidate is scoped to a real interval (one calendar
    day's index), but a CIK's submissions main snapshot is a standing
    object with no such interval. Keying by anything run-derived (a
    manifest digest, a run_id-based ``universe_label``) would silently
    break replay-safety: two runs over the same CIK on different days
    would create two different Fetch Decisions for what the ledger's
    per-key ordering (``observation_position``, ``_require_prior_revision_
    published``) needs to recognize as the *same* logical key's next
    observation, not a fresh, independent one.
    """

    return f"submissions-discovery/{cik}/main"


def submissions_pagination_candidate_id(cik: int, file_name: str) -> str:
    return f"submissions-discovery/{cik}/pagination/{file_name}"


def _pagination_file_names(main_payload: dict[str, object]) -> list[str]:
    """Extract pagination file names from a parsed submissions main payload.

    Mirrors ``warehouse_orchestrator._pagination_file_names`` exactly (same
    ``filings.files[*].name`` shape) -- kept as a small local copy rather
    than an import from that ~292KB legacy module, matching this module's
    own docstring stance of staying independent of it.
    """

    filings = main_payload.get("filings", {})
    files = filings.get("files", []) if isinstance(filings, dict) else []
    if not isinstance(files, list):
        return []
    names: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        file_name = str(entry.get("name", "")).strip()
        if file_name:
            names.append(file_name)
    return names


def drive_submissions_manifest(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    registry: Mapping[str, SourceFamilyPolicy],
    manifest: SubmissionsManifest,
    *,
    worker_id: str,
    registry_version: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> SubmissionsDriveResult:
    """Issue one main Fetch Decision per CIK; for every CIK whose main fetch
    is newly CAPTURED this call, parse it, then issue one Fetch Decision per
    declared pagination file and drive those too.

    Replay-safe the same way ``discovery.drive_discovery_manifest`` is: an
    already-``CAPTURED`` main candidate is detected via a cheap,
    network-free ``create_fetch_decision`` status check before any fetch is
    attempted. On a replay where the main candidate was already captured
    (but this process instance doesn't have its parsed payload on hand),
    pagination candidates are re-derived by re-fetching the main snapshot's
    bytes from Bronze (cheap, no SEC network call -- ``build_capture_facade``
    /``SubmissionsPolicy.fetch`` is never invoked for an already-CAPTURED
    decision) so their file names can still be resolved and their own
    decisions checked/driven. One candidate's failure (main or any of its
    pagination files) is caught and recorded per-candidate so it cannot
    abort the rest of the interval -- the interval simply stays incomplete
    until every CIK's main snapshot AND every one of its declared pagination
    files reaches a settled outcome.
    """

    facade = build_capture_facade(ledger, bronze_root, registry, worker_id=worker_id)
    cause_reference = f"submissions-manifest:{manifest.digest}:registry:{registry_version}"
    outcomes: list[SubmissionsCandidateOutcome] = []
    for candidate in manifest.candidates:
        outcomes.append(
            _drive_one_candidate(
                ledger,
                bronze_root,
                registry,
                facade,
                candidate,
                cause_reference=cause_reference,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
        )
    return SubmissionsDriveResult(manifest=manifest, outcomes=tuple(outcomes))


@dataclass(frozen=True)
class _DecisionDriveOutcome:
    """One decision's outcome after issue-and-drive -- the shared shape
    both a main candidate and a pagination file need before they diverge
    into their own result types (``SubmissionsCandidateOutcome`` carries
    pagination_outcomes; ``PaginationOutcome`` doesn't).
    """

    decision_id: str | None
    fetch_disposition: FetchDisposition | None
    fetch_state: FetchWorkState | None
    captured_artifact_reference: str | None
    network_fetched: bool
    error: str | None


def _issue_and_drive_decision(
    ledger: AcquisitionLedger,
    facade,
    request: FetchDecisionRequest,
    *,
    worker_id: str,
    lease_seconds: int,
) -> _DecisionDriveOutcome:
    """Issue one Fetch Decision and drive it through capture if not already
    CAPTURED.

    Shared by ``_drive_one_candidate`` (main) and ``_drive_pagination_for_cik``
    (each pagination file) -- Standards review, this ticket: the
    create_fetch_decision try/except -> CAPTURED short-circuit ->
    execute_source_request try/except -> re-query-status shape was
    duplicated between the two.
    """

    try:
        status = ledger.create_fetch_decision(request)
    except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
        return _DecisionDriveOutcome(
            decision_id=None,
            fetch_disposition=None,
            fetch_state=None,
            captured_artifact_reference=None,
            network_fetched=False,
            error=str(error),
        )

    if status.fetch_state is FetchWorkState.CAPTURED:
        return _DecisionDriveOutcome(
            decision_id=status.decision_id,
            fetch_disposition=status.fetch_disposition,
            fetch_state=status.fetch_state,
            captured_artifact_reference=status.captured_artifact_reference,
            network_fetched=False,
            error=None,
        )

    try:
        result = execute_source_request(
            ledger, request, facade, worker_id=worker_id, lease_seconds=lease_seconds
        )
        final_status = ledger.source_change_status(result.status.decision_id)
    except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
        failed_status = ledger.source_change_status(status.decision_id)
        return _DecisionDriveOutcome(
            decision_id=failed_status.decision_id,
            fetch_disposition=failed_status.fetch_disposition,
            fetch_state=failed_status.fetch_state,
            captured_artifact_reference=failed_status.captured_artifact_reference,
            network_fetched=True,
            error=str(error),
        )

    return _DecisionDriveOutcome(
        decision_id=final_status.decision_id,
        fetch_disposition=final_status.fetch_disposition,
        fetch_state=final_status.fetch_state,
        captured_artifact_reference=final_status.captured_artifact_reference,
        network_fetched=True,
        error=None,
    )


def _drive_one_candidate(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    registry: Mapping[str, SourceFamilyPolicy],
    facade,
    candidate: SubmissionsCandidate,
    *,
    cause_reference: str,
    worker_id: str,
    lease_seconds: int,
) -> SubmissionsCandidateOutcome:
    main_request = FetchDecisionRequest(
        candidate_id=submissions_main_candidate_id(candidate.cik),
        source_family=SUBMISSIONS_DISCOVERY_SOURCE_FAMILY,
        logical_source_key=candidate.logical_source_key,
        source_url=candidate.source_url,
        cause=DecisionCause.CAPTURED_DISCOVERY,
        cause_reference=cause_reference,
        disposition=FetchDisposition.FETCH_AUTHORIZED,
        blocker=None,
        next_action="FETCH_SOURCE",
        owner_role=DecisionOwnerRole.ACQUISITION_COORDINATOR,
    )
    outcome = _issue_and_drive_decision(
        ledger, facade, main_request, worker_id=worker_id, lease_seconds=lease_seconds
    )

    if outcome.fetch_state is not FetchWorkState.CAPTURED:
        # Rejected outright, or fetched but not CAPTURED (e.g. incomplete
        # payload -> FAILED) -- nothing to derive pagination candidates from.
        return SubmissionsCandidateOutcome(
            candidate=candidate,
            decision_id=outcome.decision_id,
            fetch_disposition=outcome.fetch_disposition,
            fetch_state=outcome.fetch_state,
            network_fetched=outcome.network_fetched,
            error=outcome.error,
        )

    # CAPTURED (this call or an earlier one) -- derive pagination candidates
    # from the verified Bronze bytes; a cache hit above means no new SEC
    # network call happens for the main snapshot itself here.
    assert outcome.captured_artifact_reference is not None
    main_bytes = _read_bronze_bytes(bronze_root, outcome.captured_artifact_reference)
    pagination_outcomes = _drive_pagination_for_cik(
        ledger,
        registry,
        facade,
        candidate.cik,
        main_bytes,
        cause_reference=cause_reference,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    return SubmissionsCandidateOutcome(
        candidate=candidate,
        decision_id=outcome.decision_id,
        fetch_disposition=outcome.fetch_disposition,
        fetch_state=outcome.fetch_state,
        network_fetched=outcome.network_fetched,
        error=None,
        pagination_outcomes=pagination_outcomes,
    )


def _drive_pagination_for_cik(
    ledger: AcquisitionLedger,
    registry: Mapping[str, SourceFamilyPolicy],
    facade,
    cik: int,
    main_bytes: bytes,
    *,
    cause_reference: str,
    worker_id: str,
    lease_seconds: int,
) -> tuple[PaginationOutcome, ...]:
    from edgar_warehouse.infrastructure.sec_client import build_submission_pagination_url

    try:
        main_payload = json.loads(main_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        # A main payload that captured successfully (is_complete() already
        # proved it's a valid JSON object at fetch time) but somehow fails
        # to reparse here would indicate a Bronze read-back mismatch far
        # more serious than one pagination file -- treat as zero pagination
        # files rather than raising, since this candidate's own settled
        # state already reflects a successful main capture; nothing further
        # to drive.
        return ()
    file_names = _pagination_file_names(main_payload) if isinstance(main_payload, dict) else []

    outcomes: list[PaginationOutcome] = []
    for file_name in file_names:
        request = FetchDecisionRequest(
            candidate_id=submissions_pagination_candidate_id(cik, file_name),
            source_family=SUBMISSIONS_DISCOVERY_SOURCE_FAMILY,
            logical_source_key=f"{cik}/pagination/{file_name}",
            source_url=build_submission_pagination_url(file_name),
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference=cause_reference,
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
            owner_role=DecisionOwnerRole.ACQUISITION_COORDINATOR,
        )
        outcome = _issue_and_drive_decision(
            ledger, facade, request, worker_id=worker_id, lease_seconds=lease_seconds
        )
        outcomes.append(
            PaginationOutcome(
                file_name=file_name,
                decision_id=outcome.decision_id,
                fetch_state=outcome.fetch_state,
                network_fetched=outcome.network_fetched,
                error=outcome.error,
            )
        )
    return tuple(outcomes)


def _read_bronze_bytes(bronze_root: StorageLocation, relative_path: str) -> bytes:
    from edgar_warehouse.infrastructure.object_storage import read_bytes

    return read_bytes(bronze_root.join(relative_path))
