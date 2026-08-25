"""Ticket 21: assert durable external evidence (sec_company/sec_company_
filing rows), not concrete classes -- same discipline as
test_silver_acceptance.py's own header comment for filing_artifact.
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
from edgar_warehouse.acquisition.processing import (
    ExpectedProducerOutcome,
    ProcessingLedger,
    SilverFinalizer,
    SilverOutcome,
)
from edgar_warehouse.acquisition.revisions import SourceRevisionLedger
from edgar_warehouse.acquisition.submissions_discovery import (
    PaginationOutcome,
    SubmissionsCandidate,
    SubmissionsCandidateOutcome,
    SubmissionsDriveResult,
    SubmissionsManifest,
)
from edgar_warehouse.acquisition.submissions_silver_acceptance import (
    UnsupportedRequiredProducers,
    drive_submissions_silver_acceptance,
)
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
) -> tuple[str, str]:
    """Writes payload to bronze (mirroring facade._capture_bronze_evidence's
    naming convention) and finalizes a CAPTURED decision referencing it.
    Returns (decision_id, bronze_relative_path).
    """

    raw_evidence_hash = hashlib.sha256(payload).hexdigest()
    relative_path = f"submissions/{raw_evidence_hash}"
    bronze_root.write_immutable_bytes(relative_path, payload)

    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id=candidate_id,
            source_family="submissions",
            logical_source_key=logical_source_key,
            source_url=f"https://data.sec.gov/submissions/{candidate_id}.json",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="submissions-manifest-1",
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
    return decision.decision_id, relative_path


def _main_payload(*, files: list[str] | None = None) -> dict[str, object]:
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-26-000001"],
                "filingDate": ["2026-08-01"],
                "reportDate": [""],
                "acceptanceDateTime": ["2026-08-01T00:00:00.000Z"],
                "act": ["34"],
                "form": ["4"],
                "fileNumber": [""],
                "filmNumber": [""],
                "items": [""],
                "size": [1000],
                "isXBRL": [0],
                "isInlineXBRL": [0],
                "primaryDocument": ["doc.xml"],
                "primaryDocDescription": [""],
            },
            "files": [{"name": name} for name in (files or [])],
        },
    }


def _pagination_payload(*, accession: str) -> dict[str, object]:
    return {
        "filings": {
            "accessionNumber": [accession],
            "filingDate": ["2020-01-01"],
            "reportDate": [""],
            "acceptanceDateTime": ["2020-01-01T00:00:00.000Z"],
            "act": ["34"],
            "form": ["4"],
            "fileNumber": [""],
            "filmNumber": [""],
            "items": [""],
            "size": [500],
            "isXBRL": [0],
            "isInlineXBRL": [0],
            "primaryDocument": ["doc.xml"],
            "primaryDocDescription": [""],
        }
    }


def _candidate_outcome(
    *,
    cik: int,
    decision_id: str,
    fetch_state: FetchWorkState,
    pagination_outcomes: tuple[PaginationOutcome, ...] = (),
) -> SubmissionsCandidateOutcome:
    return SubmissionsCandidateOutcome(
        candidate=SubmissionsCandidate(
            cik=cik, source_url=f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
        ),
        decision_id=decision_id,
        fetch_disposition=FetchDisposition.FETCH_AUTHORIZED,
        fetch_state=fetch_state,
        network_fetched=True,
        error=None,
        pagination_outcomes=pagination_outcomes,
    )


def test_finalize_writes_and_verifies_sec_company_and_sec_company_filing(tmp_path: Path) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    payload = json.dumps(_main_payload(files=[])).encode("utf-8")
    decision_id, _ = _captured_decision(
        ledger,
        bronze_root,
        candidate_id="submissions-discovery/test/320193/main",
        logical_source_key="320193/main",
        payload=payload,
    )
    outcome = _candidate_outcome(
        cik=320193, decision_id=decision_id, fetch_state=FetchWorkState.CAPTURED
    )
    result = drive_submissions_silver_acceptance(
        ledger,
        bronze_root,
        revisions,
        processing,
        finalizer,
        silver,
        SubmissionsDriveResult(
            manifest=SubmissionsManifest(universe_label="test", candidates=()),
            outcomes=(outcome,),
        ),
    )

    assert result.interval_complete is True
    assert len(result.main_outcomes) == 1
    main_decision = result.main_outcomes[0].processing_decision
    assert main_decision.silver_outcome is SilverOutcome.PUBLISHED
    producer_names = {p.producer_name for p in main_decision.expected_producers}
    assert producer_names == {"sec_company", "sec_company_filing"}
    for producer in main_decision.expected_producers:
        assert producer.outcome is ExpectedProducerOutcome.VERIFIED

    # Durable external evidence.
    company = silver.get_company(320193)
    assert company is not None
    assert company["entity_name"] == "Apple Inc."
    filing = silver.get_filing("0000320193-26-000001")
    assert filing is not None
    assert filing["cik"] == 320193


def test_main_candidate_is_skipped_while_pagination_is_incomplete(tmp_path: Path) -> None:
    """Ticket 21 bullet 2: a main snapshot cannot declare completeness while
    a referenced pagination file is unverified -- this must not even attempt
    to seal Silver producers for main, leaving it unsettled for the next
    replay rather than sealing a decision this run.

    Note: a pagination file that never reached CAPTURED at the fetch layer
    (fetch_state=FAILED here) has no SilverAcceptanceResult entry at all --
    this module's own interval_complete is scoped to "of what reached
    CAPTURED, did Silver settle it," mirroring silver_acceptance.py's
    identical filing_artifact scoping. The un-captured pagination file is
    the *fetch* layer's problem, already reflected in
    SubmissionsDriveResult.interval_complete -- a command orchestrator
    checks both layers together (see drive_filing_discovery.py's own
    ``result.interval_complete and silver_result.interval_complete``), so
    the overall run correctly reports incomplete even though this module's
    own result is vacuously "complete" over zero attempted outcomes.
    """

    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    payload = json.dumps(_main_payload(files=["file1.json"])).encode("utf-8")
    decision_id, _ = _captured_decision(
        ledger,
        bronze_root,
        candidate_id="submissions-discovery/test/320193/main",
        logical_source_key="320193/main",
        payload=payload,
    )
    # Pagination file never captured (fetch_state=FAILED) -> pagination_complete=False.
    pagination_outcome = PaginationOutcome(
        file_name="file1.json",
        decision_id="submissions-discovery/test/320193/pagination/file1.json",
        fetch_state=FetchWorkState.FAILED,
        network_fetched=True,
        error="SourceCaptureFailed: incomplete payload",
    )
    outcome = _candidate_outcome(
        cik=320193,
        decision_id=decision_id,
        fetch_state=FetchWorkState.CAPTURED,
        pagination_outcomes=(pagination_outcome,),
    )
    drive_result = SubmissionsDriveResult(
        manifest=SubmissionsManifest(universe_label="test", candidates=()),
        outcomes=(outcome,),
    )
    # The fetch-layer result already reports this interval incomplete --
    # this is the real signal an orchestrator relies on.
    assert drive_result.interval_complete is False

    result = drive_submissions_silver_acceptance(
        ledger,
        bronze_root,
        revisions,
        processing,
        finalizer,
        silver,
        drive_result,
    )

    # Main candidate was entirely skipped -- not attempted-and-failed.
    assert result.main_outcomes == ()
    # The un-captured pagination file is never attempted at the Silver
    # layer either (this module only finalizes CAPTURED decisions).
    assert result.pagination_outcomes == ()
    # No revision was materialized for main, and no sec_company row exists.
    assert silver.get_company(320193) is None


def test_pagination_candidate_writes_and_verifies_sec_company_filing(tmp_path: Path) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    payload = json.dumps(_pagination_payload(accession="0000320193-19-000042")).encode("utf-8")
    decision_id, _ = _captured_decision(
        ledger,
        bronze_root,
        candidate_id="submissions-discovery/test/320193/pagination/file1.json",
        logical_source_key="320193/pagination/file1.json",
        payload=payload,
    )
    pagination_outcome = PaginationOutcome(
        file_name="file1.json",
        decision_id=decision_id,
        fetch_state=FetchWorkState.CAPTURED,
        network_fetched=True,
        error=None,
    )
    outcome = SubmissionsCandidateOutcome(
        candidate=SubmissionsCandidate(
            cik=320193, source_url="https://data.sec.gov/submissions/CIK0000320193.json"
        ),
        decision_id=None,
        fetch_disposition=None,
        fetch_state=None,
        network_fetched=False,
        error="main not captured this run",
        pagination_outcomes=(pagination_outcome,),
    )
    result = drive_submissions_silver_acceptance(
        ledger,
        bronze_root,
        revisions,
        processing,
        finalizer,
        silver,
        SubmissionsDriveResult(
            manifest=SubmissionsManifest(universe_label="test", candidates=()),
            outcomes=(outcome,),
        ),
    )

    assert len(result.pagination_outcomes) == 1
    pagination_decision = result.pagination_outcomes[0].processing_decision
    assert pagination_decision.silver_outcome is SilverOutcome.PUBLISHED
    filing = silver.get_filing("0000320193-19-000042")
    assert filing is not None
    assert filing["cik"] == 320193


def test_a_not_actually_captured_decision_is_recorded_as_a_per_candidate_error(
    tmp_path: Path,
) -> None:
    """Mirrors silver_acceptance.py's own fault isolation: one candidate's
    CandidateNotCaptured must not abort the whole drive call -- it's caught
    and recorded as this candidate's own error, leaving the rest of the
    interval (and the ability to retry this candidate on a later replay)
    intact.
    """

    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id="submissions-discovery/test/320193/main",
            source_family="submissions",
            logical_source_key="320193/main",
            source_url="https://data.sec.gov/submissions/CIK0000320193.json",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="submissions-manifest-1",
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
        )
    )
    outcome = _candidate_outcome(
        cik=320193, decision_id=decision.decision_id, fetch_state=FetchWorkState.CAPTURED
    )
    result = drive_submissions_silver_acceptance(
        ledger,
        bronze_root,
        revisions,
        processing,
        finalizer,
        silver,
        SubmissionsDriveResult(
            manifest=SubmissionsManifest(universe_label="test", candidates=()),
            outcomes=(outcome,),
        ),
    )

    assert result.interval_complete is False
    assert len(result.main_outcomes) == 1
    assert result.main_outcomes[0].error is not None
    assert "not CAPTURED" in result.main_outcomes[0].error
    assert result.main_outcomes[0].settled is False


def test_drive_rejects_a_required_producers_set_it_cannot_serve(tmp_path: Path) -> None:
    """Ticket 32 bullet 1's pattern, ported: required_producers is validated
    upfront, not read and ignored -- this Strategy's write bodies only know
    how to produce sec_company + sec_company_filing, so a registry
    declaring anything else must fail closed rather than silently doing
    nothing for the undeclared producer.
    """

    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)

    with pytest.raises(UnsupportedRequiredProducers):
        drive_submissions_silver_acceptance(
            ledger,
            bronze_root,
            revisions,
            processing,
            finalizer,
            silver,
            SubmissionsDriveResult(
                manifest=SubmissionsManifest(universe_label="test", candidates=()),
                outcomes=(),
            ),
            required_producers=("some_other_table",),
        )
