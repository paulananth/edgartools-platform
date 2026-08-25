from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchWorkState
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.submissions_discovery import (
    SubmissionsCandidate,
    build_submissions_manifest,
    drive_submissions_manifest,
    submissions_main_candidate_id,
    submissions_pagination_candidate_id,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _ledger() -> AcquisitionLedger:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AcquisitionBase.metadata.create_all(engine)
    return AcquisitionLedger(engine)


def _main_payload(*, files: list[str] | None = None) -> dict[str, object]:
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {"accessionNumber": []},
            "files": [{"name": name} for name in (files or [])],
        },
    }


class _SpyPolicy:
    """Drives distinct payloads per URL so a test can control main vs.
    pagination fetch content/completeness independently -- unlike
    discovery.py's tests, this module's Facade calls two different URL
    shapes per candidate, so a single fixed payload isn't enough.
    """

    def __init__(self) -> None:
        self.payloads: dict[str, bytes] = {}
        self.complete_urls: set[str] = set()
        self.fetch_calls: list[str] = []

    def set_response(self, url: str, payload: bytes, *, complete: bool = True) -> None:
        self.payloads[url] = payload
        if complete:
            self.complete_urls.add(url)

    def fetch(self, source_url: str) -> bytes:
        self.fetch_calls.append(source_url)
        return self.payloads[source_url]

    def is_complete(self, payload: bytes) -> bool:
        # is_complete only receives the payload, not the URL -- match by
        # payload identity via a reverse lookup, mirroring how a real
        # SubmissionsPolicy would just check payload shape regardless of URL.
        for url, stored in self.payloads.items():
            if stored == payload:
                return url in self.complete_urls
        return False


# ---------------------------------------------------------------------------
# build_submissions_manifest
# ---------------------------------------------------------------------------


def test_manifest_orders_candidates_deterministically_by_cik() -> None:
    manifest = build_submissions_manifest([320193, 1], universe_label="test")
    assert [c.cik for c in manifest.candidates] == [1, 320193]
    assert manifest.candidate_count == 2


def test_manifest_dedupes_repeated_ciks() -> None:
    manifest = build_submissions_manifest([320193, 320193], universe_label="test")
    assert manifest.candidate_count == 1


def test_manifest_digest_is_stable_regardless_of_input_order() -> None:
    a = build_submissions_manifest([1, 2], universe_label="test")
    b = build_submissions_manifest([2, 1], universe_label="test")
    assert a.digest == b.digest


# ---------------------------------------------------------------------------
# drive_submissions_manifest
# ---------------------------------------------------------------------------


def test_drive_captures_main_and_all_declared_pagination_files(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    candidate = SubmissionsCandidate(cik=320193, source_url="https://data.sec.gov/submissions/CIK0000320193.json")
    manifest = build_submissions_manifest([320193], universe_label="test")

    main_payload = _main_payload(files=["CIK0000320193-submissions-001.json"])
    main_bytes = json.dumps(main_payload).encode("utf-8")
    pagination_bytes = json.dumps({"filings": {"accessionNumber": []}}).encode("utf-8")

    policy = _SpyPolicy()
    policy.set_response(candidate.source_url, main_bytes)
    from edgar_warehouse.infrastructure.sec_client import build_submission_pagination_url

    pagination_url = build_submission_pagination_url("CIK0000320193-submissions-001.json")
    policy.set_response(pagination_url, pagination_bytes)

    result = drive_submissions_manifest(
        ledger,
        bronze_root,
        {"submissions": policy},
        manifest,
        worker_id="worker-1",
        registry_version="submissions-v1",
    )

    assert result.interval_complete is True
    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.fetch_state is FetchWorkState.CAPTURED
    assert outcome.network_fetched is True
    assert len(outcome.pagination_outcomes) == 1
    pagination_outcome = outcome.pagination_outcomes[0]
    assert pagination_outcome.file_name == "CIK0000320193-submissions-001.json"
    assert pagination_outcome.fetch_state is FetchWorkState.CAPTURED
    assert pagination_outcome.network_fetched is True
    assert policy.fetch_calls == [candidate.source_url, pagination_url]


def test_drive_with_no_declared_pagination_files_settles_trivially(tmp_path) -> None:
    """Ticket 21: an empty scope (no pagination files at all) must still
    reach an explicit verified outcome, not a silent short-circuit.
    """

    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    candidate = SubmissionsCandidate(cik=320193, source_url="https://data.sec.gov/submissions/CIK0000320193.json")
    manifest = build_submissions_manifest([320193], universe_label="test")

    main_payload = _main_payload(files=[])
    main_bytes = json.dumps(main_payload).encode("utf-8")
    policy = _SpyPolicy()
    policy.set_response(candidate.source_url, main_bytes)

    result = drive_submissions_manifest(
        ledger,
        bronze_root,
        {"submissions": policy},
        manifest,
        worker_id="worker-1",
        registry_version="submissions-v1",
    )

    assert result.interval_complete is True
    outcome = result.outcomes[0]
    assert outcome.pagination_outcomes == ()
    assert outcome.pagination_complete is True


def test_drive_stays_incomplete_when_a_pagination_file_fails(tmp_path) -> None:
    """Ticket 21 bullet 2: a main snapshot cannot declare completeness while
    a referenced pagination file is missing/failed/unverified.
    """

    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    candidate = SubmissionsCandidate(cik=320193, source_url="https://data.sec.gov/submissions/CIK0000320193.json")
    manifest = build_submissions_manifest([320193], universe_label="test")

    main_payload = _main_payload(files=["CIK0000320193-submissions-001.json"])
    main_bytes = json.dumps(main_payload).encode("utf-8")
    policy = _SpyPolicy()
    policy.set_response(candidate.source_url, main_bytes)
    from edgar_warehouse.infrastructure.sec_client import build_submission_pagination_url

    pagination_url = build_submission_pagination_url("CIK0000320193-submissions-001.json")
    # Corrupt/incomplete pagination response -- policy.is_complete() will
    # return False for it (not registered as complete), causing the Facade
    # to raise SourceCaptureFailed and the fetch decision to end FAILED.
    policy.set_response(pagination_url, b"not valid json", complete=False)

    result = drive_submissions_manifest(
        ledger,
        bronze_root,
        {"submissions": policy},
        manifest,
        worker_id="worker-1",
        registry_version="submissions-v1",
    )

    assert result.interval_complete is False
    outcome = result.outcomes[0]
    # Main itself captured fine -- only the pagination file failed.
    assert outcome.fetch_state is FetchWorkState.CAPTURED
    assert outcome.settled is False
    assert outcome.pagination_complete is False
    assert list(result.unsettled_ciks) == [320193]


def test_drive_replay_performs_no_second_network_fetch(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    candidate = SubmissionsCandidate(cik=320193, source_url="https://data.sec.gov/submissions/CIK0000320193.json")
    manifest = build_submissions_manifest([320193], universe_label="test")

    main_payload = _main_payload(files=["CIK0000320193-submissions-001.json"])
    main_bytes = json.dumps(main_payload).encode("utf-8")
    pagination_bytes = json.dumps({"filings": {"accessionNumber": []}}).encode("utf-8")
    policy = _SpyPolicy()
    policy.set_response(candidate.source_url, main_bytes)
    from edgar_warehouse.infrastructure.sec_client import build_submission_pagination_url

    pagination_url = build_submission_pagination_url("CIK0000320193-submissions-001.json")
    policy.set_response(pagination_url, pagination_bytes)

    first = drive_submissions_manifest(
        ledger,
        bronze_root,
        {"submissions": policy},
        manifest,
        worker_id="worker-1",
        registry_version="submissions-v1",
    )
    assert first.interval_complete is True
    assert len(policy.fetch_calls) == 2

    second = drive_submissions_manifest(
        ledger,
        bronze_root,
        {"submissions": policy},
        manifest,
        worker_id="worker-2",
        registry_version="submissions-v1",
    )
    assert second.interval_complete is True
    # No additional network fetches on replay.
    assert len(policy.fetch_calls) == 2
    assert second.outcomes[0].network_fetched is False
    assert second.outcomes[0].pagination_outcomes[0].network_fetched is False


def test_candidate_ids_are_deterministic_per_cik_and_file() -> None:
    """Deliberately NOT keyed by any per-run/per-universe label -- see
    submissions_main_candidate_id's own docstring for why: a CIK's
    submissions candidate is a standing object, not scoped to an interval
    the way a daily filing candidate is, so replaying across different runs
    (different run_ids, different days) must resolve to the SAME candidate
    identity for the ledger's per-key ordering to recognize it correctly.
    """

    assert submissions_main_candidate_id(320193) == submissions_main_candidate_id(320193)
    assert submissions_main_candidate_id(320193) != submissions_main_candidate_id(1)
    assert submissions_pagination_candidate_id(
        320193, "a.json"
    ) != submissions_pagination_candidate_id(320193, "b.json")
    assert submissions_pagination_candidate_id(
        320193, "a.json"
    ) != submissions_pagination_candidate_id(1, "a.json")
