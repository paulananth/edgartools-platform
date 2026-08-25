"""Ticket 23: assert durable external evidence (sec_company_ticker rows), not
concrete classes -- same discipline as test_company_facts_silver_acceptance.py's
own header comment.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
)
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.processing import ProcessingLedger, SilverFinalizer, SilverOutcome
from edgar_warehouse.acquisition.reference_catalog_discovery import (
    ReferenceCatalogCandidate,
    ReferenceCatalogCandidateOutcome,
    ReferenceCatalogDriveResult,
    ReferenceCatalogManifest,
)
from edgar_warehouse.acquisition.reference_catalog_silver_acceptance import (
    UnsupportedRequiredProducers,
    drive_reference_catalog_silver_acceptance,
)
from edgar_warehouse.acquisition.revisions import SourceRevisionLedger
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _harness(tmp_path: Path):
    engine = _engine()
    AcquisitionBase.metadata.create_all(engine)
    silver = SilverDatabase(str(tmp_path / "silver.duckdb"))
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    return (
        AcquisitionLedger(engine),
        bronze_root,
        SourceRevisionLedger(engine),
        ProcessingLedger(engine),
        SilverFinalizer(engine),
        silver,
    )


def _captured_decision(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    *,
    candidate_id: str,
    logical_source_key: str,
    payload: bytes,
    worker_id: str = "worker-1",
) -> str:
    raw_evidence_hash = hashlib.sha256(payload).hexdigest()
    relative_path = f"reference_catalog/{raw_evidence_hash}"
    bronze_root.write_immutable_bytes(relative_path, payload)

    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id=candidate_id,
            source_family="reference_catalog",
            logical_source_key=logical_source_key,
            source_url="https://www.sec.gov/files/company_tickers.json",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="reference-catalog-manifest-1",
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
        )
    )
    lease = ledger.claim_fetch(decision.decision_id, worker_id=worker_id, lease_seconds=300)
    ledger.finalize_fetch(
        decision.decision_id,
        worker_id=worker_id,
        fencing_token=lease.fencing_token,
        final_state=FetchWorkState.CAPTURED,
        artifact_reference=relative_path,
    )
    return decision.decision_id


def _catalog_payload(*, entries: tuple[tuple[int, str], ...] = ((320193, "AAPL"),)) -> dict:
    return {
        str(i): {"cik_str": cik, "ticker": ticker, "title": f"Company {ticker}"}
        for i, (cik, ticker) in enumerate(entries)
    }


def _candidate_outcome(*, source_name: str, decision_id: str) -> ReferenceCatalogCandidateOutcome:
    return ReferenceCatalogCandidateOutcome(
        candidate=ReferenceCatalogCandidate(
            source_name=source_name,
            source_url=f"https://www.sec.gov/files/{source_name}.json",
        ),
        decision_id=decision_id,
        fetch_disposition=FetchDisposition.FETCH_AUTHORIZED,
        fetch_state=FetchWorkState.CAPTURED,
        network_fetched=True,
        error=None,
    )


def test_finalize_writes_and_verifies_sec_company_ticker(tmp_path: Path) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    payload = json.dumps(_catalog_payload()).encode("utf-8")
    decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="reference-catalog-discovery/company_tickers",
        logical_source_key="reference-catalog/company_tickers",
        payload=payload,
    )
    outcome = _candidate_outcome(source_name="company_tickers", decision_id=decision_id)

    result = drive_reference_catalog_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        ReferenceCatalogDriveResult(
            manifest=ReferenceCatalogManifest(universe_label="test", candidates=()),
            outcomes=(outcome,),
        ),
    )

    assert result.interval_complete is True
    assert len(result.outcomes) == 1
    decision = result.outcomes[0].processing_decision
    assert decision.silver_outcome is SilverOutcome.PUBLISHED
    producer_names = {p.producer_name for p in decision.expected_producers}
    assert producer_names == {"sec_company_ticker"}

    rows = silver.fetch(
        "SELECT cik, ticker FROM sec_company_ticker WHERE source_name = ?", ["company_tickers"]
    )
    assert rows == [{"cik": 320193, "ticker": "AAPL"}]


def test_finalize_settles_a_complete_empty_catalog_scope(tmp_path: Path) -> None:
    """Bullet 2: a valid zero-member catalog must settle VERIFIED with
    count=0, not be treated as incomplete or a failure.
    """

    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    payload = json.dumps({}).encode("utf-8")
    decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="reference-catalog-discovery/company_tickers",
        logical_source_key="reference-catalog/company_tickers",
        payload=payload,
    )
    outcome = _candidate_outcome(source_name="company_tickers", decision_id=decision_id)

    result = drive_reference_catalog_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        ReferenceCatalogDriveResult(
            manifest=ReferenceCatalogManifest(universe_label="test", candidates=()),
            outcomes=(outcome,),
        ),
    )

    assert result.interval_complete is True
    decision = result.outcomes[0].processing_decision
    assert decision.silver_outcome is SilverOutcome.PUBLISHED
    for producer in decision.expected_producers:
        assert producer.outcome.value == "VERIFIED"
        assert "count=0" in producer.scope_reference


def test_a_not_actually_captured_decision_is_recorded_as_a_per_candidate_error(
    tmp_path: Path,
) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id="reference-catalog-discovery/company_tickers",
            source_family="reference_catalog",
            logical_source_key="reference-catalog/company_tickers",
            source_url="https://www.sec.gov/files/company_tickers.json",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="reference-catalog-manifest-1",
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
        )
    )
    outcome = _candidate_outcome(source_name="company_tickers", decision_id=decision.decision_id)

    result = drive_reference_catalog_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        ReferenceCatalogDriveResult(
            manifest=ReferenceCatalogManifest(universe_label="test", candidates=()),
            outcomes=(outcome,),
        ),
    )

    assert result.interval_complete is False
    assert result.outcomes[0].error is not None
    assert result.outcomes[0].settled is False


def test_finalize_second_identical_capture_is_no_impact_and_publishes_with_no_producers(
    tmp_path: Path,
) -> None:
    """Bullet 4's 'unchanged' leg: a second CAPTURED decision for the same
    logical key carrying byte-identical content must seal with empty
    expected producers and touch nothing.
    """

    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    logical_key = "reference-catalog/company_tickers"
    payload = json.dumps(_catalog_payload()).encode("utf-8")

    first_decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="reference-catalog-discovery/company_tickers/first",
        logical_source_key=logical_key,
        payload=payload,
    )
    first_result = drive_reference_catalog_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        ReferenceCatalogDriveResult(
            manifest=ReferenceCatalogManifest(universe_label="test", candidates=()),
            outcomes=(_candidate_outcome(source_name="company_tickers", decision_id=first_decision_id),),
        ),
    )
    assert first_result.outcomes[0].processing_decision.silver_outcome is SilverOutcome.PUBLISHED

    second_decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="reference-catalog-discovery/company_tickers/second",
        logical_source_key=logical_key,
        payload=payload,
    )
    second_result = drive_reference_catalog_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        ReferenceCatalogDriveResult(
            manifest=ReferenceCatalogManifest(universe_label="test", candidates=()),
            outcomes=(_candidate_outcome(source_name="company_tickers", decision_id=second_decision_id),),
        ),
    )

    second_decision = second_result.outcomes[0].processing_decision
    assert second_decision.disposition.value == "NO_IMPACT"
    assert second_decision.silver_outcome is SilverOutcome.PUBLISHED
    assert second_decision.expected_producers == ()


def test_a_fresh_snapshot_replaces_the_prior_scope_for_the_local_candidate(tmp_path: Path) -> None:
    """Bullet 3's negative gate is only meaningful if a *good* fresh snapshot
    genuinely replaces the prior scope locally -- confirms
    ``replace_company_tickers``'s per-source_name delete-then-insert is
    correctly reached and does retire a dropped ticker from this candidate's
    own local Silver database (see this module's docstring for the separate,
    known gap in propagating that retirement to canonical).
    """

    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)

    first_payload = json.dumps(_catalog_payload(entries=((320193, "AAPL"), (789019, "MSFT")))).encode(
        "utf-8"
    )
    first_decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="reference-catalog-discovery/company_tickers/first",
        logical_source_key="reference-catalog/company_tickers",
        payload=first_payload,
    )
    drive_reference_catalog_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        ReferenceCatalogDriveResult(
            manifest=ReferenceCatalogManifest(universe_label="test", candidates=()),
            outcomes=(_candidate_outcome(source_name="company_tickers", decision_id=first_decision_id),),
        ),
    )
    assert {
        r["ticker"]
        for r in silver.fetch(
            "SELECT ticker FROM sec_company_ticker WHERE source_name = ?", ["company_tickers"]
        )
    } == {"AAPL", "MSFT"}

    # A fresh, content-different snapshot drops MSFT.
    second_payload = json.dumps(_catalog_payload(entries=((320193, "AAPL"),))).encode("utf-8")
    second_decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="reference-catalog-discovery/company_tickers/second",
        logical_source_key="reference-catalog/company_tickers",
        payload=second_payload,
    )
    second_result = drive_reference_catalog_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        ReferenceCatalogDriveResult(
            manifest=ReferenceCatalogManifest(universe_label="test", candidates=()),
            outcomes=(_candidate_outcome(source_name="company_tickers", decision_id=second_decision_id),),
        ),
    )

    assert second_result.outcomes[0].processing_decision.silver_outcome is SilverOutcome.PUBLISHED
    assert {
        r["ticker"]
        for r in silver.fetch(
            "SELECT ticker FROM sec_company_ticker WHERE source_name = ?", ["company_tickers"]
        )
    } == {"AAPL"}


def test_finalize_settles_verified_when_a_numbered_dict_entry_has_a_blank_ticker(
    tmp_path: Path,
) -> None:
    """Standards-review-caught edge case: ``_parse_company_ticker_rows``'s
    numbered-dict branch (``company_tickers.json`` shape) only guards a
    missing ``cik_str``, not an empty ``ticker`` -- but
    ``replace_company_tickers`` silently skips any row with a falsy ticker.
    Without filtering ``rows`` the same way before building the expected
    member set, this settles a false FAILED for a real SEC catalog entry
    that happens to carry a blank ticker.
    """

    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    payload = json.dumps(
        {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 1, "ticker": "", "title": "No-Ticker Co."},
        }
    ).encode("utf-8")
    decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="reference-catalog-discovery/company_tickers",
        logical_source_key="reference-catalog/company_tickers",
        payload=payload,
    )
    outcome = _candidate_outcome(source_name="company_tickers", decision_id=decision_id)

    result = drive_reference_catalog_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        ReferenceCatalogDriveResult(
            manifest=ReferenceCatalogManifest(universe_label="test", candidates=()),
            outcomes=(outcome,),
        ),
    )

    decision = result.outcomes[0].processing_decision
    assert decision.silver_outcome is SilverOutcome.PUBLISHED
    for producer in decision.expected_producers:
        assert producer.outcome.value == "VERIFIED"
        assert "count=1" in producer.scope_reference

    rows = silver.fetch(
        "SELECT cik, ticker FROM sec_company_ticker WHERE source_name = ?", ["company_tickers"]
    )
    assert rows == [{"cik": 320193, "ticker": "AAPL"}]


def test_drive_rejects_a_required_producers_set_it_cannot_serve(tmp_path: Path) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)

    with pytest.raises(UnsupportedRequiredProducers):
        drive_reference_catalog_silver_acceptance(
            ledger, bronze_root, revisions, processing, finalizer, silver,
            ReferenceCatalogDriveResult(
                manifest=ReferenceCatalogManifest(universe_label="test", candidates=()),
                outcomes=(),
            ),
            required_producers=("some_other_table",),
        )
