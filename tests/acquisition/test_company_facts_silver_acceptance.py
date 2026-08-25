"""Ticket 22: assert durable external evidence (sec_financial_fact/
sec_accounting_flag rows), not concrete classes -- same discipline as
test_submissions_silver_acceptance.py's own header comment.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.company_facts_discovery import (
    CompanyFactsCandidate,
    CompanyFactsCandidateOutcome,
    CompanyFactsDriveResult,
    CompanyFactsManifest,
)
from edgar_warehouse.acquisition.company_facts_silver_acceptance import (
    UnsupportedRequiredProducers,
    drive_company_facts_silver_acceptance,
)
from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
)
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.processing import ProcessingLedger, SilverFinalizer, SilverOutcome
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
    relative_path = f"company_facts/{raw_evidence_hash}"
    bronze_root.write_immutable_bytes(relative_path, payload)

    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id=candidate_id,
            source_family="company_facts",
            logical_source_key=logical_source_key,
            source_url=f"https://data.sec.gov/api/xbrl/companyfacts/{candidate_id}.json",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="company-facts-manifest-1",
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


def _facts_payload(*, accession: str = "0000320193-23-000106", with_facts: bool = True) -> dict:
    if not with_facts:
        return {"cik": 320193, "entityName": "Apple Inc.", "facts": {}}
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "end": "2023-09-30", "val": 1000,
                                "accn": accession, "fy": 2023, "fp": "FY", "form": "10-K",
                            }
                        ]
                    }
                }
            }
        },
    }


def _candidate_outcome(*, cik: int, decision_id: str) -> CompanyFactsCandidateOutcome:
    return CompanyFactsCandidateOutcome(
        candidate=CompanyFactsCandidate(
            cik=cik,
            source_url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
        ),
        decision_id=decision_id,
        fetch_disposition=FetchDisposition.FETCH_AUTHORIZED,
        fetch_state=FetchWorkState.CAPTURED,
        network_fetched=True,
        error=None,
    )


def test_finalize_writes_and_verifies_sec_financial_fact_and_sec_accounting_flag(
    tmp_path: Path,
) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    payload = json.dumps(_facts_payload()).encode("utf-8")
    decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="company-facts-discovery/320193",
        logical_source_key="320193/company-facts",
        payload=payload,
    )
    outcome = _candidate_outcome(cik=320193, decision_id=decision_id)

    result = drive_company_facts_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        CompanyFactsDriveResult(
            manifest=CompanyFactsManifest(universe_label="test", candidates=()),
            outcomes=(outcome,),
        ),
    )

    assert result.interval_complete is True
    assert len(result.outcomes) == 1
    decision = result.outcomes[0].processing_decision
    assert decision.silver_outcome is SilverOutcome.PUBLISHED
    producer_names = {p.producer_name for p in decision.expected_producers}
    assert producer_names == {"sec_financial_fact", "sec_accounting_flag"}

    rows = silver.fetch(
        "SELECT concept, value FROM sec_financial_fact WHERE cik = ?", [320193]
    )
    assert rows == [{"concept": "Assets", "value": 1000.0}]


def test_finalize_settles_a_complete_empty_facts_scope(tmp_path: Path) -> None:
    """Ticket 22 bullet 2 / advisor trap: a real CIK can have zero XBRL
    facts -- this must settle VERIFIED with count 0, not be treated as
    incomplete or a failure.
    """

    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    payload = json.dumps(_facts_payload(with_facts=False)).encode("utf-8")
    decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="company-facts-discovery/320193",
        logical_source_key="320193/company-facts",
        payload=payload,
    )
    outcome = _candidate_outcome(cik=320193, decision_id=decision_id)

    result = drive_company_facts_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        CompanyFactsDriveResult(
            manifest=CompanyFactsManifest(universe_label="test", candidates=()),
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
            candidate_id="company-facts-discovery/320193",
            source_family="company_facts",
            logical_source_key="320193/company-facts",
            source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="company-facts-manifest-1",
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
        )
    )
    outcome = _candidate_outcome(cik=320193, decision_id=decision.decision_id)

    result = drive_company_facts_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        CompanyFactsDriveResult(
            manifest=CompanyFactsManifest(universe_label="test", candidates=()),
            outcomes=(outcome,),
        ),
    )

    assert result.interval_complete is False
    assert result.outcomes[0].error is not None
    assert result.outcomes[0].settled is False


def test_finalize_second_identical_capture_is_no_impact_and_publishes_with_no_producers(
    tmp_path: Path,
) -> None:
    """Ticket 22 bullet 4's 'unchanged' leg: a second CAPTURED decision for
    the same logical key carrying byte-identical content must seal with
    empty expected producers and touch nothing, mirroring
    test_silver_acceptance.py's own filing_artifact equivalent.
    """

    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    logical_key = "320193/company-facts"
    payload = json.dumps(_facts_payload()).encode("utf-8")

    first_decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="company-facts-discovery/320193/first",
        logical_source_key=logical_key,
        payload=payload,
    )
    first_result = drive_company_facts_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        CompanyFactsDriveResult(
            manifest=CompanyFactsManifest(universe_label="test", candidates=()),
            outcomes=(_candidate_outcome(cik=320193, decision_id=first_decision_id),),
        ),
    )
    assert first_result.outcomes[0].processing_decision.silver_outcome is SilverOutcome.PUBLISHED

    second_decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="company-facts-discovery/320193/second",
        logical_source_key=logical_key,
        payload=payload,
    )
    second_result = drive_company_facts_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        CompanyFactsDriveResult(
            manifest=CompanyFactsManifest(universe_label="test", candidates=()),
            outcomes=(_candidate_outcome(cik=320193, decision_id=second_decision_id),),
        ),
    )

    second_decision = second_result.outcomes[0].processing_decision
    assert second_decision.disposition.value == "NO_IMPACT"
    assert second_decision.silver_outcome is SilverOutcome.PUBLISHED
    assert second_decision.expected_producers == ()


def test_drive_rejects_a_required_producers_set_it_cannot_serve(tmp_path: Path) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)

    with pytest.raises(UnsupportedRequiredProducers):
        drive_company_facts_silver_acceptance(
            ledger, bronze_root, revisions, processing, finalizer, silver,
            CompanyFactsDriveResult(
                manifest=CompanyFactsManifest(universe_label="test", candidates=()),
                outcomes=(),
            ),
            required_producers=("some_other_table",),
        )
