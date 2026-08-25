from __future__ import annotations

import json

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.company_facts_discovery import (
    CompanyFactsCandidate,
    build_company_facts_manifest,
    company_facts_candidate_id,
    drive_company_facts_manifest,
)
from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchWorkState
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
# build_company_facts_manifest
# ---------------------------------------------------------------------------


def test_manifest_orders_candidates_deterministically_by_cik() -> None:
    manifest = build_company_facts_manifest([320193, 1], universe_label="test")
    assert [c.cik for c in manifest.candidates] == [1, 320193]
    assert manifest.candidate_count == 2


def test_manifest_dedupes_repeated_ciks() -> None:
    manifest = build_company_facts_manifest([320193, 320193], universe_label="test")
    assert manifest.candidate_count == 1


def test_manifest_digest_is_stable_regardless_of_input_order() -> None:
    a = build_company_facts_manifest([1, 2], universe_label="test")
    b = build_company_facts_manifest([2, 1], universe_label="test")
    assert a.digest == b.digest


def test_zero_cik_universe_is_a_valid_complete_empty_manifest() -> None:
    """Ticket 22 bullet 2: a valid complete-empty scope, not an error."""

    manifest = build_company_facts_manifest([], universe_label="test")
    assert manifest.candidate_count == 0
    assert manifest.digest == build_company_facts_manifest([], universe_label="other").digest


# ---------------------------------------------------------------------------
# drive_company_facts_manifest
# ---------------------------------------------------------------------------


def test_drive_captures_a_company_facts_snapshot(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    candidate = CompanyFactsCandidate(
        cik=320193, source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )
    manifest = build_company_facts_manifest([320193], universe_label="test")
    payload = json.dumps({"cik": 320193, "entityName": "Apple Inc.", "facts": {}}).encode("utf-8")
    policy = _SpyPolicy(payload)

    result = drive_company_facts_manifest(
        ledger,
        bronze_root,
        {"company_facts": policy},
        manifest,
        worker_id="worker-1",
        registry_version="company-facts-v1",
    )

    assert result.interval_complete is True
    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.candidate == candidate
    assert outcome.fetch_state is FetchWorkState.CAPTURED
    assert outcome.network_fetched is True
    assert policy.fetch_calls == [candidate.source_url]


def test_drive_replay_performs_no_second_network_fetch(tmp_path) -> None:
    """The bug caught during Ticket 21's TDD, guarded against here from the
    start: candidate ids must not be keyed by anything run-derived, or a
    replay silently re-fetches every CIK from SEC on every invocation.
    """

    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    manifest = build_company_facts_manifest([320193], universe_label="test")
    payload = json.dumps({"cik": 320193, "entityName": "Apple Inc.", "facts": {}}).encode("utf-8")
    policy = _SpyPolicy(payload)

    first = drive_company_facts_manifest(
        ledger, bronze_root, {"company_facts": policy}, manifest,
        worker_id="worker-1", registry_version="company-facts-v1",
    )
    assert first.interval_complete is True
    assert len(policy.fetch_calls) == 1

    second = drive_company_facts_manifest(
        ledger, bronze_root, {"company_facts": policy}, manifest,
        worker_id="worker-2", registry_version="company-facts-v1",
    )
    assert second.interval_complete is True
    assert len(policy.fetch_calls) == 1
    assert second.outcomes[0].network_fetched is False


def test_drive_stays_incomplete_when_capture_fails(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    manifest = build_company_facts_manifest([320193], universe_label="test")
    policy = _SpyPolicy(b"not valid json", complete=False)

    result = drive_company_facts_manifest(
        ledger, bronze_root, {"company_facts": policy}, manifest,
        worker_id="worker-1", registry_version="company-facts-v1",
    )

    assert result.interval_complete is False
    assert list(result.unsettled_ciks) == [320193]


def test_candidate_ids_are_deterministic_per_cik_only() -> None:
    """Deliberately NOT keyed by any per-run/per-universe label -- see
    ``company_facts_candidate_id``'s own docstring: a CIK's company-facts
    snapshot is a standing object, not scoped to an interval.
    """

    assert company_facts_candidate_id(320193) == company_facts_candidate_id(320193)
    assert company_facts_candidate_id(320193) != company_facts_candidate_id(1)
