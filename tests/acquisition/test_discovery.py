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


def test_discovery_candidate_id_is_deterministic_per_interval_and_accession() -> None:
    first = discovery_candidate_id("2026-08-24", "0001-26-000001")
    second = discovery_candidate_id("2026-08-24", "0001-26-000001")
    different_date = discovery_candidate_id("2026-08-25", "0001-26-000001")
    assert first == second
    assert first != different_date


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
