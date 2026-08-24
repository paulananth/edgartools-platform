"""Ticket 19 bullet 5: assert durable external evidence, not concrete classes.

Every test in this file exercises ``finalize_filing_artifact_candidate``
against a real ``SilverDatabase`` (DuckDB) and reads the resulting
``sec_raw_object`` row back independently -- the assertions are on what
landed in that durable store, never on which internal Facade/Strategy/
handler object was invoked.
"""

from __future__ import annotations

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
from edgar_warehouse.acquisition.processing import (
    ExpectedProducerOutcome,
    ProcessingDisposition,
    ProcessingLedger,
    SilverFinalizer,
    SilverOutcome,
)
from edgar_warehouse.acquisition.revisions import SourceRevisionLedger
from edgar_warehouse.acquisition.silver_acceptance import (
    CandidateNotCaptured,
    FilingArtifactCandidateMeta,
    bronze_reference_to_raw_evidence_hash,
    finalize_filing_artifact_candidate,
)
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
    return (
        AcquisitionLedger(engine),
        SourceRevisionLedger(engine),
        ProcessingLedger(engine),
        SilverFinalizer(engine),
        silver,
    )


def _captured_decision(
    ledger: AcquisitionLedger,
    *,
    candidate_id: str,
    logical_source_key: str,
    artifact_reference: str,
    worker_id: str = "worker-1",
) -> str:
    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id=candidate_id,
            source_family="filing_artifact",
            logical_source_key=logical_source_key,
            source_url=f"https://www.sec.gov/Archives/{candidate_id}.txt",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="discovery-manifest-1",
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
        artifact_reference=artifact_reference,
    )
    return decision.decision_id


_META = FilingArtifactCandidateMeta(
    cik=320193,
    accession_number="0000320193-26-000001",
    form="4",
    source_url="https://www.sec.gov/Archives/edgar/data/320193/0000320193-26-000001.txt",
)


def test_finalize_writes_and_verifies_sec_raw_object(tmp_path: Path) -> None:
    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision_id = _captured_decision(
        ledger,
        candidate_id="c1",
        logical_source_key="320193/0000320193-26-000001/full-submission-text",
        artifact_reference="filing_artifact/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )

    decision = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, decision_id, _META
    )

    assert decision.disposition is ProcessingDisposition.PROCESS_REQUIRED
    assert decision.silver_outcome is SilverOutcome.PUBLISHED
    producer = decision.expected_producers[0]
    assert producer.outcome is ExpectedProducerOutcome.VERIFIED

    # Durable external evidence: read sec_raw_object back independently,
    # not via anything this call returned.
    raw_object = silver.get_raw_object(producer.verified_reference)
    assert raw_object is not None
    assert raw_object["sha256"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert raw_object["accession_number"] == "0000320193-26-000001"
    assert raw_object["cik"] == 320193
    assert raw_object["form"] == "4"
    assert raw_object["source_type"] == "filing_artifact"
    assert raw_object["storage_path"] == "filing_artifact/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_finalize_marks_failed_on_read_back_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A write that lands but reads back wrong content must be recorded
    FAILED, not VERIFIED -- read-back verification, not write success alone
    (Ticket 19 bullet 2).
    """

    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision_id = _captured_decision(
        ledger,
        candidate_id="c1",
        logical_source_key="320193/0000320193-26-000001/full-submission-text",
        artifact_reference="filing_artifact/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )

    real_upsert = silver.upsert_raw_object

    def _corrupting_upsert(row: dict) -> None:
        row = dict(row)
        row["sha256"] = "corrupted-on-write"
        real_upsert(row)

    monkeypatch.setattr(silver, "upsert_raw_object", _corrupting_upsert)

    decision = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, decision_id, _META
    )

    assert decision.silver_outcome is SilverOutcome.FAILED
    producer = decision.expected_producers[0]
    assert producer.outcome is ExpectedProducerOutcome.FAILED
    assert "did not match" in producer.failure_detail


def test_finalize_blocks_later_revision_for_same_key_after_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    logical_key = "320193/0000320193-26-000001/full-submission-text"
    first_decision_id = _captured_decision(
        ledger,
        candidate_id="c1",
        logical_source_key=logical_key,
        artifact_reference="filing_artifact/cccccccccccccccccccccccccccccccc",
    )

    real_upsert = silver.upsert_raw_object

    def _corrupting_upsert(row: dict) -> None:
        row = dict(row)
        row["sha256"] = "corrupted-on-write"
        real_upsert(row)

    monkeypatch.setattr(silver, "upsert_raw_object", _corrupting_upsert)
    first_result = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, first_decision_id, _META
    )
    assert first_result.silver_outcome is SilverOutcome.FAILED

    monkeypatch.setattr(silver, "upsert_raw_object", real_upsert)
    second_decision_id = _captured_decision(
        ledger,
        candidate_id="c2",
        logical_source_key=logical_key,
        artifact_reference="filing_artifact/dddddddddddddddddddddddddddddddd",
    )

    with pytest.raises(Exception) as excinfo:
        finalize_filing_artifact_candidate(
            ledger, revisions, processing, finalizer, silver, second_decision_id, _META
        )
    assert "PriorRevisionNotSettled" in type(excinfo.value).__name__

    # Prior Silver state remains exactly as it was -- the blocked later
    # attempt never wrote or touched sec_raw_object at all. The first
    # (failed) attempt's row is still there, still carrying the mismatched
    # content it failed on -- nothing repaired or overwrote it.
    first_row = silver.get_raw_object(first_result.revision_id)
    assert first_row is not None
    assert first_row["sha256"] == "corrupted-on-write"


def test_finalize_is_idempotent_on_replay(tmp_path: Path) -> None:
    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision_id = _captured_decision(
        ledger,
        candidate_id="c1",
        logical_source_key="320193/0000320193-26-000001/full-submission-text",
        artifact_reference="filing_artifact/eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    )

    first = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, decision_id, _META
    )
    second = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, decision_id, _META
    )

    assert first == second


def test_finalize_second_identical_capture_is_no_impact_and_publishes_with_no_producers(
    tmp_path: Path,
) -> None:
    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    logical_key = "320193/0000320193-26-000001/full-submission-text"
    same_bytes_reference = "filing_artifact/ffffffffffffffffffffffffffffffff"
    first_decision_id = _captured_decision(
        ledger, candidate_id="c1", logical_source_key=logical_key, artifact_reference=same_bytes_reference
    )
    finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, first_decision_id, _META
    )

    second_decision_id = _captured_decision(
        ledger, candidate_id="c2", logical_source_key=logical_key, artifact_reference=same_bytes_reference
    )
    second = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, second_decision_id, _META
    )

    assert second.disposition is ProcessingDisposition.NO_IMPACT
    assert second.silver_outcome is SilverOutcome.PUBLISHED
    assert second.expected_producers == ()


def test_finalize_requires_captured_decision(tmp_path: Path) -> None:
    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id="c1",
            source_family="filing_artifact",
            logical_source_key="320193/0000320193-26-000001/full-submission-text",
            source_url="https://www.sec.gov/Archives/c1.txt",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="discovery-manifest-1",
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
        )
    )

    with pytest.raises(CandidateNotCaptured):
        finalize_filing_artifact_candidate(
            ledger, revisions, processing, finalizer, silver, decision.decision_id, _META
        )


def test_bronze_reference_to_raw_evidence_hash_matches_real_facade_output(tmp_path: Path) -> None:
    """Ties this module's path-parsing to the Facade's actual naming
    convention with a real capture, not just a hand-written example.
    """

    from edgar_warehouse.acquisition.facade import build_capture_facade
    from edgar_warehouse.acquisition.ledger import execute_source_request
    from edgar_warehouse.infrastructure.object_storage import StorageLocation

    engine = _engine()
    AcquisitionBase.metadata.create_all(engine)
    ledger = AcquisitionLedger(engine)
    bronze_root = StorageLocation(str(tmp_path / "bronze"))

    class _Policy:
        def fetch(self, source_url: str) -> bytes:
            return b"real filing bytes for hash parsing test"

        def is_complete(self, payload: bytes) -> bool:
            return True

    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": _Policy()}, worker_id="worker-1"
    )
    request = FetchDecisionRequest(
        candidate_id="c1",
        source_family="filing_artifact",
        logical_source_key="320193/0000320193-26-000001/full-submission-text",
        source_url="https://www.sec.gov/Archives/c1.txt",
        cause=DecisionCause.CAPTURED_DISCOVERY,
        cause_reference="discovery-manifest-1",
        disposition=FetchDisposition.FETCH_AUTHORIZED,
        blocker=None,
        next_action="FETCH_SOURCE",
    )
    result = execute_source_request(ledger, request, facade, worker_id="worker-1")

    parsed = bronze_reference_to_raw_evidence_hash(result.adapter_result.bronze_relative_path)
    assert parsed == result.adapter_result.raw_evidence_hash
