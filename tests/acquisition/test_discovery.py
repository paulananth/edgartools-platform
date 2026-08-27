from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.discovery import (
    DISCOVERY_IN_SCOPE_FORMS,
    DiscoveryCandidate,
    build_discovery_manifest,
    discovery_candidate_id,
    drive_discovery_manifest,
)
from edgar_warehouse.acquisition.facade import DEFAULT_FINALIZE_CAPTURE_ATTEMPTS
from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchDisposition, FetchWorkState
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _ledger() -> AcquisitionLedger:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AcquisitionBase.metadata.create_all(engine)
    return AcquisitionLedger(engine)


def _row(*, accession: str, cik: int, form: str, file_name: str | None = None) -> dict[str, object]:
    file_name = file_name or f"edgar/data/{cik}/{accession}.txt"
    return {
        "accession_number": accession,
        "cik": cik,
        "form": form,
        "filing_txt_url": f"https://www.sec.gov/Archives/{file_name}",
    }


class _SpyPolicy:
    def __init__(self, payload: bytes, *, complete: bool = True) -> None:
        self.payload = payload
        self.complete = complete
        self.fetch_calls: list[str] = []

    def fetch(self, source_url: str) -> bytes:
        self.fetch_calls.append(source_url)
        return self.payload

    def is_complete(self, payload: bytes) -> bool:
        return self.complete


# ---------------------------------------------------------------------------
# build_discovery_manifest
# ---------------------------------------------------------------------------


def test_manifest_orders_candidates_deterministically_by_accession() -> None:
    rows = [
        _row(accession="0001-26-000002", cik=2, form="4"),
        _row(accession="0001-26-000001", cik=1, form="4"),
    ]
    manifest = build_discovery_manifest(rows, business_date="2026-08-24")
    assert [c.accession_number for c in manifest.candidates] == [
        "0001-26-000001",
        "0001-26-000002",
    ]
    assert manifest.candidate_count == 2


def test_manifest_dedupes_repeated_accession_rows() -> None:
    rows = [
        _row(accession="0001-26-000001", cik=1, form="4"),
        _row(accession="0001-26-000001", cik=1, form="4"),
    ]
    manifest = build_discovery_manifest(rows, business_date="2026-08-24")
    assert manifest.candidate_count == 1


def test_manifest_digest_is_stable_regardless_of_input_row_order() -> None:
    a = _row(accession="0001-26-000001", cik=1, form="4")
    b = _row(accession="0001-26-000002", cik=2, form="10-K")
    manifest_1 = build_discovery_manifest([a, b], business_date="2026-08-24")
    manifest_2 = build_discovery_manifest([b, a], business_date="2026-08-24")
    assert manifest_1.digest == manifest_2.digest


def test_manifest_digest_changes_when_candidate_set_changes() -> None:
    manifest_1 = build_discovery_manifest(
        [_row(accession="0001-26-000001", cik=1, form="4")], business_date="2026-08-24"
    )
    manifest_2 = build_discovery_manifest(
        [_row(accession="0001-26-000002", cik=1, form="4")], business_date="2026-08-24"
    )
    assert manifest_1.digest != manifest_2.digest


def test_manifest_marks_ownership_forms_in_scope_and_others_excluded() -> None:
    rows = [
        _row(accession="0001-26-000001", cik=1, form="4"),
        _row(accession="0001-26-000002", cik=1, form="10-K"),
    ]
    manifest = build_discovery_manifest(rows, business_date="2026-08-24")
    by_accession = {c.accession_number: c for c in manifest.candidates}
    assert by_accession["0001-26-000001"].in_scope is True
    assert by_accession["0001-26-000002"].in_scope is False
    assert DISCOVERY_IN_SCOPE_FORMS == frozenset({"3", "3/A", "4", "4/A", "5", "5/A"})


def test_discovery_in_scope_forms_matches_warehouse_orchestrator_ownership_forms() -> None:
    # Deliberately duplicated by value, not import (see discovery.py's own
    # comment) -- this regression test is what keeps the two from silently
    # diverging on a future edit to either constant.
    from edgar_warehouse.application.warehouse_orchestrator import OWNERSHIP_FORMS

    assert DISCOVERY_IN_SCOPE_FORMS == OWNERSHIP_FORMS


# ---------------------------------------------------------------------------
# drive_discovery_manifest
# ---------------------------------------------------------------------------


def test_drive_captures_in_scope_candidate_to_bronze(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    payload = b"<ownershipDocument>real filing bytes</ownershipDocument>"
    policy = _SpyPolicy(payload)
    manifest = build_discovery_manifest(
        [_row(accession="0001-26-000001", cik=320193, form="4")], business_date="2026-08-24"
    )

    result = drive_discovery_manifest(
        ledger,
        bronze_root,
        {"filing_artifact": policy},
        manifest,
        worker_id="worker-1",
        registry_version="filing_artifact-v1",
    )

    assert result.interval_complete is True
    assert result.unsettled_candidate_ids == ()
    outcome = result.outcomes[0]
    assert outcome.network_fetched is True
    assert outcome.fetch_state is FetchWorkState.CAPTURED
    expected_hash = hashlib.sha256(payload).hexdigest()
    stored = (tmp_path / "bronze" / "filing_artifact" / expected_hash).read_bytes()
    assert stored == payload
    assert policy.fetch_calls == [
        "https://www.sec.gov/Archives/edgar/data/320193/0001-26-000001.txt"
    ]


def test_drive_excludes_out_of_scope_form_with_no_download(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    policy = _SpyPolicy(b"should never be fetched")
    manifest = build_discovery_manifest(
        [_row(accession="0001-26-000009", cik=1, form="10-K")], business_date="2026-08-24"
    )

    result = drive_discovery_manifest(
        ledger,
        bronze_root,
        {"filing_artifact": policy},
        manifest,
        worker_id="worker-1",
        registry_version="filing_artifact-v1",
    )

    assert result.interval_complete is True
    outcome = result.outcomes[0]
    assert outcome.network_fetched is False
    assert outcome.fetch_disposition is FetchDisposition.OUT_OF_SCOPE
    assert policy.fetch_calls == []
    assert not (tmp_path / "bronze").exists()


def test_replaying_the_same_manifest_performs_no_duplicate_decision_or_network_work(
    tmp_path,
) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    policy = _SpyPolicy(b"payload")
    manifest = build_discovery_manifest(
        [
            _row(accession="0001-26-000001", cik=1, form="4"),
            _row(accession="0001-26-000002", cik=1, form="10-K"),
        ],
        business_date="2026-08-24",
    )

    first = drive_discovery_manifest(
        ledger,
        bronze_root,
        {"filing_artifact": policy},
        manifest,
        worker_id="worker-1",
        registry_version="filing_artifact-v1",
    )
    assert len(policy.fetch_calls) == 1
    first_decision_ids = {o.decision_id for o in first.outcomes}

    second = drive_discovery_manifest(
        ledger,
        bronze_root,
        {"filing_artifact": policy},
        manifest,
        worker_id="worker-2",
        registry_version="filing_artifact-v1",
    )

    # No new network fetch and no new decisions -- same decision_ids reused.
    assert len(policy.fetch_calls) == 1
    assert {o.decision_id for o in second.outcomes} == first_decision_ids
    assert all(not o.network_fetched for o in second.outcomes)
    assert second.interval_complete is True


def test_one_candidates_capture_failure_does_not_abort_the_rest_of_the_interval(
    tmp_path,
) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    good_policy = _SpyPolicy(b"good payload")
    manifest = build_discovery_manifest(
        [
            _row(accession="0001-26-000001", cik=1, form="4"),
            _row(accession="0001-26-000002", cik=2, form="4"),
        ],
        business_date="2026-08-24",
    )

    class _RoutingPolicy:
        def fetch(self, source_url: str) -> bytes:
            if "0001-26-000002" in source_url:
                raise RuntimeError("SEC request failed")
            return good_policy.fetch(source_url)

        def is_complete(self, payload: bytes) -> bool:
            return True

    result = drive_discovery_manifest(
        ledger,
        bronze_root,
        {"filing_artifact": _RoutingPolicy()},
        manifest,
        worker_id="worker-1",
        registry_version="filing_artifact-v1",
    )

    assert result.interval_complete is False
    outcomes_by_accession = {o.candidate.accession_number: o for o in result.outcomes}
    assert outcomes_by_accession["0001-26-000001"].fetch_state is FetchWorkState.CAPTURED
    failed = outcomes_by_accession["0001-26-000002"]
    assert failed.fetch_state is FetchWorkState.FAILED
    assert failed.error is not None
    assert result.unsettled_candidate_ids == ("0001-26-000002",)


def test_retrying_a_failed_candidate_on_a_later_drive_call_preserves_decision_identity(
    tmp_path,
) -> None:
    """Ticket 17 bullet 1: a retry (a second, later drive_discovery_manifest
    call for the SAME interval) must reuse the original decision, cause, and
    observation position while claiming a new attempt with a higher fence --
    not invent a second decision for the same candidate.
    """
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    manifest = build_discovery_manifest(
        [_row(accession="0001-26-000001", cik=1, form="4")], business_date="2026-08-24"
    )

    class _FailOnceThenSucceedPolicy:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload
            self.calls = 0

        def fetch(self, source_url: str) -> bytes:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("SEC request failed")
            return self.payload

        def is_complete(self, payload: bytes) -> bool:
            return True

    policy = _FailOnceThenSucceedPolicy(b"real filing bytes")

    first = drive_discovery_manifest(
        ledger,
        bronze_root,
        {"filing_artifact": policy},
        manifest,
        worker_id="worker-1",
        registry_version="filing_artifact-v1",
    )
    assert first.interval_complete is False
    failed_outcome = first.outcomes[0]
    assert failed_outcome.fetch_state is FetchWorkState.FAILED
    original_decision_id = failed_outcome.decision_id

    retried = drive_discovery_manifest(
        ledger,
        bronze_root,
        {"filing_artifact": policy},
        manifest,
        worker_id="worker-2",
        registry_version="filing_artifact-v1",
    )

    assert retried.interval_complete is True
    retried_outcome = retried.outcomes[0]
    # Same decision, cause, and observation position -- not a second decision
    # for the same candidate.
    assert retried_outcome.decision_id == original_decision_id
    assert retried_outcome.fetch_state is FetchWorkState.CAPTURED
    assert policy.calls == 2

    original_status = ledger.source_change_status(original_decision_id)
    assert original_status.observation_position == 1
    assert original_status.cause.value == "CAPTURED_DISCOVERY"

    stored = (
        tmp_path
        / "bronze"
        / "filing_artifact"
        / hashlib.sha256(policy.payload).hexdigest()
    ).read_bytes()
    assert stored == policy.payload


class _FlakyOnFirstCaptureLedger:
    """Wraps a real AcquisitionLedger; every CAPTURED finalize call for the
    FIRST candidate's decision (all of its bounded retry attempts) raises,
    standing in for sustained ledger unavailability right after that one
    candidate's Bronze write -- the orphan-quarantine scenario (Ticket 17
    bullet 4). A later candidate's CAPTURED finalize succeeds normally,
    proving the outage is isolated to the one decision, not global.
    """

    def __init__(self, real_ledger: AcquisitionLedger, *, fail_calls: int) -> None:
        self._real = real_ledger
        self._fail_calls = fail_calls
        self._capture_call_count = 0

    def __getattr__(self, name):
        return getattr(self._real, name)

    def finalize_fetch(self, *args, **kwargs):
        if kwargs.get("final_state") is FetchWorkState.CAPTURED:
            self._capture_call_count += 1
            if self._capture_call_count <= self._fail_calls:
                raise RuntimeError("sustained ledger unavailability")
        return self._real.finalize_fetch(*args, **kwargs)


def test_an_orphaned_bronze_capture_stays_unsettled_without_touching_sibling_candidates(
    tmp_path,
) -> None:
    real_ledger = _ledger()
    flaky_ledger = _FlakyOnFirstCaptureLedger(
        real_ledger, fail_calls=DEFAULT_FINALIZE_CAPTURE_ATTEMPTS
    )
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    policy = _SpyPolicy(b"real filing bytes that never finalize")
    manifest = build_discovery_manifest(
        [
            _row(accession="0001-26-000001", cik=1, form="4"),
            _row(accession="0001-26-000002", cik=2, form="4"),
        ],
        business_date="2026-08-24",
    )

    class _RoutingPolicy:
        def fetch(self, source_url: str) -> bytes:
            if "0001-26-000001" in source_url:
                return policy.fetch(source_url)
            return b"sibling candidate's own payload"

        def is_complete(self, payload: bytes) -> bool:
            return True

    result = drive_discovery_manifest(
        flaky_ledger,
        bronze_root,
        {"filing_artifact": _RoutingPolicy()},
        manifest,
        worker_id="worker-1",
        registry_version="filing_artifact-v1",
    )

    assert result.interval_complete is False
    outcomes_by_accession = {o.candidate.accession_number: o for o in result.outcomes}

    orphaned = outcomes_by_accession["0001-26-000001"]
    assert orphaned.error is not None
    assert "quarantined" in orphaned.error
    # Never downgraded to FAILED -- the ledger genuinely doesn't know CAPTURED
    # happened, so it must not lie about it either. Confirmed via the REAL
    # (unwrapped) ledger, since drive_discovery_manifest's own outcome record
    # is built from what the (possibly stale) status read returned.
    real_status = real_ledger.source_change_status(orphaned.decision_id)
    assert real_status.fetch_state is FetchWorkState.LEASED

    # The sibling candidate, sharing this same interval/call, is untouched.
    sibling = outcomes_by_accession["0001-26-000002"]
    assert sibling.fetch_state is FetchWorkState.CAPTURED
    assert sibling.error is None

    assert result.unsettled_candidate_ids == ("0001-26-000001",)


def test_discovery_candidate_id_is_deterministic_per_interval_and_accession() -> None:
    first = discovery_candidate_id("2026-08-24", "0001-26-000001")
    second = discovery_candidate_id("2026-08-24", "0001-26-000001")
    different_date = discovery_candidate_id("2026-08-25", "0001-26-000001")
    assert first == second
    assert first != different_date


def test_discovery_candidate_id_preserves_filing_artifacts_legacy_format() -> None:
    """Ticket 24 bullet 4: filing_artifact already has real prod ledger rows
    (Ticket 29's dry run) keyed on this exact format -- changing it would
    silently break replay recognition and cause a real SEC re-fetch on the
    next run for an already-processed date. Locks in the id string itself,
    not just its determinism, so a future refactor can't silently drift it.
    """

    assert discovery_candidate_id("2026-08-24", "0001-26-000001") == (
        "filing-discovery/2026-08-24/0001-26-000001"
    )
    assert discovery_candidate_id(
        "2026-08-24", "0001-26-000001", source_family="filing_artifact"
    ) == "filing-discovery/2026-08-24/0001-26-000001"


def test_discovery_candidate_id_scopes_other_families_to_avoid_collision() -> None:
    """The real bug this ticket found: the same business_date + accession is
    a genuine candidate in more than one family's manifest (one in-scope,
    one excluded) when two families' drivers read the same sealed daily
    index -- without source_family in the id, the second family's decision
    collides with the first's.
    """

    filing_id = discovery_candidate_id(
        "2026-08-24", "0001-26-000001", source_family="filing_artifact"
    )
    adv_id = discovery_candidate_id(
        "2026-08-24", "0001-26-000001", source_family="adv_filing"
    )
    assert filing_id != adv_id
    assert adv_id == "filing-discovery/adv_filing/2026-08-24/0001-26-000001"


def test_conflicting_replay_with_a_different_registry_version_does_not_abort_the_rest_of_the_interval(
    tmp_path,
) -> None:
    """A candidate_id is scoped to (business_date, accession), but the
    Fetch Decision's cause_reference embeds registry_version -- so reusing
    the same manifest with a different registry_version raises
    CandidateDecisionConflict for an already-decided candidate. That must
    stay a per-candidate unsettled outcome, not abort every other
    candidate in the same drive call.
    """

    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    policy = _SpyPolicy(b"payload")
    manifest = build_discovery_manifest(
        [_row(accession="0001-26-000001", cik=1, form="4")], business_date="2026-08-24"
    )

    first = drive_discovery_manifest(
        ledger,
        bronze_root,
        {"filing_artifact": policy},
        manifest,
        worker_id="worker-1",
        registry_version="filing_artifact-v1",
    )
    assert first.interval_complete is True
    assert len(policy.fetch_calls) == 1

    conflicting_manifest = build_discovery_manifest(
        [
            _row(accession="0001-26-000001", cik=1, form="4"),
            _row(accession="0001-26-000009", cik=9, form="4"),
        ],
        business_date="2026-08-24",
    )

    second = drive_discovery_manifest(
        ledger,
        bronze_root,
        {"filing_artifact": policy},
        conflicting_manifest,
        worker_id="worker-2",
        registry_version="filing_artifact-v2",
    )

    # The whole drive call did not raise -- the conflicting candidate is
    # simply unsettled, and the genuinely new sibling candidate still
    # reached verified Bronze in the same call.
    assert second.interval_complete is False
    assert second.unsettled_candidate_ids == ("0001-26-000001",)
    outcomes_by_accession = {o.candidate.accession_number: o for o in second.outcomes}
    conflicted = outcomes_by_accession["0001-26-000001"]
    assert conflicted.decision_id is None
    assert conflicted.fetch_disposition is None
    assert conflicted.error is not None
    sibling = outcomes_by_accession["0001-26-000009"]
    assert sibling.fetch_state is FetchWorkState.CAPTURED
    assert len(policy.fetch_calls) == 2
