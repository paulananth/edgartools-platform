from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchWorkState
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.reference_catalog_discovery import (
    ReferenceCatalogCandidate,
    UnsupportedReferenceSource,
    build_reference_catalog_manifest,
    drive_reference_catalog_manifest,
    reference_catalog_candidate_id,
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
# build_reference_catalog_manifest
# ---------------------------------------------------------------------------


def test_manifest_orders_candidates_deterministically_by_source_name() -> None:
    manifest = build_reference_catalog_manifest(
        ["company_tickers_exchange", "company_tickers"], universe_label="test"
    )
    assert [c.source_name for c in manifest.candidates] == [
        "company_tickers",
        "company_tickers_exchange",
    ]
    assert manifest.candidate_count == 2


def test_manifest_dedupes_repeated_source_names() -> None:
    manifest = build_reference_catalog_manifest(
        ["company_tickers", "company_tickers"], universe_label="test"
    )
    assert manifest.candidate_count == 1


def test_manifest_digest_is_stable_regardless_of_input_order() -> None:
    a = build_reference_catalog_manifest(
        ["company_tickers", "company_tickers_exchange"], universe_label="test"
    )
    b = build_reference_catalog_manifest(
        ["company_tickers_exchange", "company_tickers"], universe_label="test"
    )
    assert a.digest == b.digest


def test_zero_source_universe_is_a_valid_complete_empty_manifest() -> None:
    """Bullet 2: a valid complete-empty scope, not an error."""

    manifest = build_reference_catalog_manifest([], universe_label="test")
    assert manifest.candidate_count == 0
    assert manifest.digest == build_reference_catalog_manifest([], universe_label="other").digest


def test_default_manifest_covers_exactly_the_two_supported_ticker_catalogs() -> None:
    manifest = build_reference_catalog_manifest(universe_label="test")
    assert [c.source_name for c in manifest.candidates] == [
        "company_tickers",
        "company_tickers_exchange",
    ]


def test_manifest_rejects_an_unsupported_source_name() -> None:
    with pytest.raises(UnsupportedReferenceSource):
        build_reference_catalog_manifest(["pcaob_auditorsearch_bulk"], universe_label="test")


# ---------------------------------------------------------------------------
# drive_reference_catalog_manifest
# ---------------------------------------------------------------------------


def test_drive_captures_a_reference_catalog_snapshot(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    candidate = ReferenceCatalogCandidate(
        source_name="company_tickers", source_url="https://www.sec.gov/files/company_tickers.json"
    )
    manifest = build_reference_catalog_manifest(["company_tickers"], universe_label="test")
    payload = json.dumps({"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}).encode(
        "utf-8"
    )
    policy = _SpyPolicy(payload)

    result = drive_reference_catalog_manifest(
        ledger,
        bronze_root,
        {"reference_catalog": policy},
        manifest,
        worker_id="worker-1",
        registry_version="reference-catalog-v1",
    )

    assert result.interval_complete is True
    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.candidate == candidate
    assert outcome.fetch_state is FetchWorkState.CAPTURED
    assert outcome.network_fetched is True
    assert policy.fetch_calls == [candidate.source_url]


def test_drive_replay_performs_no_second_network_fetch(tmp_path) -> None:
    """Same replay-safety guard Tickets 21/22 already proved: candidate ids
    must not be keyed by anything run-derived.
    """

    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    manifest = build_reference_catalog_manifest(["company_tickers"], universe_label="test")
    payload = json.dumps({}).encode("utf-8")
    policy = _SpyPolicy(payload)

    first = drive_reference_catalog_manifest(
        ledger, bronze_root, {"reference_catalog": policy}, manifest,
        worker_id="worker-1", registry_version="reference-catalog-v1",
    )
    assert first.interval_complete is True
    assert len(policy.fetch_calls) == 1

    second = drive_reference_catalog_manifest(
        ledger, bronze_root, {"reference_catalog": policy}, manifest,
        worker_id="worker-2", registry_version="reference-catalog-v1",
    )
    assert second.interval_complete is True
    assert len(policy.fetch_calls) == 1
    assert second.outcomes[0].network_fetched is False


def test_drive_stays_incomplete_when_capture_fails(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    manifest = build_reference_catalog_manifest(["company_tickers"], universe_label="test")
    policy = _SpyPolicy(b"not valid json", complete=False)

    result = drive_reference_catalog_manifest(
        ledger, bronze_root, {"reference_catalog": policy}, manifest,
        worker_id="worker-1", registry_version="reference-catalog-v1",
    )

    assert result.interval_complete is False
    assert list(result.unsettled_source_names) == ["company_tickers"]


def test_candidate_ids_are_deterministic_per_source_name_only() -> None:
    assert reference_catalog_candidate_id("company_tickers") == reference_catalog_candidate_id(
        "company_tickers"
    )
    assert reference_catalog_candidate_id("company_tickers") != reference_catalog_candidate_id(
        "company_tickers_exchange"
    )
