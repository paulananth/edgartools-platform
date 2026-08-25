"""Ticket 24: assert durable external evidence (sec_adv_* rows), not
concrete classes -- same discipline as test_reference_catalog_silver_acceptance.py's
own header comment.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.adv_bulk_dataset_discovery import (
    AdvBulkDatasetCandidate,
    AdvBulkDatasetCandidateOutcome,
    AdvBulkDatasetDriveResult,
    AdvBulkDatasetManifest,
)
from edgar_warehouse.acquisition.adv_bulk_dataset_silver_acceptance import (
    UnsupportedRequiredProducers,
    drive_adv_bulk_dataset_silver_acceptance,
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


def _harness(tmp_path: Path):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
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


def _zip(files: dict[str, str]) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return payload.getvalue()


_BULK_ARCHIVE = _zip(
    {
        "IA_ADV_Base_A_20260601_20260630.csv": (
            '"FilingID","DateSubmitted","1A","1D","1E1","7B"\n'
            '2115188,"06/24/2026 10:37:17 AM","PNC WEALTH","801-66195",129052,"N"\n'
        ),
    }
)

_ROSTER_HEADER = (
    '"Organization CRD#","7B","Count of Private Funds - 7B(1)",'
    '"Any Hedge Funds","Total number of Hedge funds",'
    '"Any PE Funds","Total number of PE funds",'
    '"Total Gross Assets of Private Funds","Count of Private Funds - 7B(2)"\n'
)
_ROSTER_ARCHIVE = _zip(
    {
        "IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_1.CSV": (
            _ROSTER_HEADER
            + '1588,"Y","                   3","Y","3","N","",'
            '"           709,905,606.00","                   0"\n'
        ),
    }
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
    relative_path = f"adv_bulk_dataset/{raw_evidence_hash}"
    bronze_root.write_immutable_bytes(relative_path, payload)

    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id=candidate_id,
            source_family="adv_bulk_dataset",
            logical_source_key=logical_source_key,
            source_url="https://reports.adviserinfo.sec.gov/reports/foia/x.zip",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="adv-bulk-dataset-manifest-1",
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


def _outcome(
    *, source_kind: str, dataset_period: str, decision_id: str, variant: str | None = None
) -> AdvBulkDatasetCandidateOutcome:
    return AdvBulkDatasetCandidateOutcome(
        candidate=AdvBulkDatasetCandidate(
            source_kind=source_kind, dataset_period=dataset_period, variant=variant, source_url="x"
        ),
        decision_id=decision_id,
        fetch_disposition=FetchDisposition.FETCH_AUTHORIZED,
        fetch_state=FetchWorkState.CAPTURED,
        network_fetched=True,
        error=None,
    )


def test_adv_bulk_archive_settles_verified_and_writes_silver_rows(tmp_path: Path) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="adv-bulk-dataset-discovery/adv-bulk/2026-06",
        logical_source_key="adv-bulk-archive/2026-06",
        payload=_BULK_ARCHIVE,
    )
    outcome = _outcome(source_kind="adv_bulk", dataset_period="2026-06", decision_id=decision_id)

    result = drive_adv_bulk_dataset_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        AdvBulkDatasetDriveResult(
            manifest=AdvBulkDatasetManifest(universe_label="t", candidates=(), unpublished_periods=()),
            outcomes=(outcome,),
        ),
    )

    decision = result.outcomes[0].processing_decision
    assert decision.silver_outcome is SilverOutcome.PUBLISHED
    for producer in decision.expected_producers:
        assert producer.outcome.value == "VERIFIED"

    rows = silver.fetch("SELECT accession_number, crd_number FROM sec_adv_filing")
    assert rows == [{"accession_number": "iapd-adv:2115188", "crd_number": "129052"}]


def test_firm_roster_archive_settles_verified_and_writes_silver_row(tmp_path: Path) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision_id = _captured_decision(
        ledger, bronze_root,
        candidate_id="adv-bulk-dataset-discovery/firm-roster/registered/2026-07",
        logical_source_key="adv-firm-roster/registered/2026-07",
        payload=_ROSTER_ARCHIVE,
    )
    outcome = _outcome(
        source_kind="firm_roster", dataset_period="2026-07", variant="registered", decision_id=decision_id
    )

    result = drive_adv_bulk_dataset_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        AdvBulkDatasetDriveResult(
            manifest=AdvBulkDatasetManifest(universe_label="t", candidates=(), unpublished_periods=()),
            outcomes=(outcome,),
        ),
    )

    decision = result.outcomes[0].processing_decision
    assert decision.silver_outcome is SilverOutcome.PUBLISHED
    assert decision.expected_producers[0].outcome.value == "VERIFIED"

    rows = silver.fetch("SELECT adviser_crd_number, dataset_period FROM sec_adv_firm_roster")
    assert rows == [{"adviser_crd_number": "1588", "dataset_period": "2026-07"}]


def test_second_identical_capture_is_no_impact_and_publishes_with_no_producers(tmp_path: Path) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision_id_1 = _captured_decision(
        ledger, bronze_root,
        candidate_id="adv-bulk-dataset-discovery/adv-bulk/2026-06",
        logical_source_key="adv-bulk-archive/2026-06",
        payload=_BULK_ARCHIVE,
    )
    outcome_1 = _outcome(source_kind="adv_bulk", dataset_period="2026-06", decision_id=decision_id_1)
    first = drive_adv_bulk_dataset_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        AdvBulkDatasetDriveResult(
            manifest=AdvBulkDatasetManifest(universe_label="t", candidates=(), unpublished_periods=()),
            outcomes=(outcome_1,),
        ),
    )
    assert first.outcomes[0].processing_decision.silver_outcome is SilverOutcome.PUBLISHED

    decision_id_2 = _captured_decision(
        ledger, bronze_root,
        candidate_id="adv-bulk-dataset-discovery/adv-bulk/2026-06-replay",
        logical_source_key="adv-bulk-archive/2026-06",
        payload=_BULK_ARCHIVE,
    )
    outcome_2 = _outcome(source_kind="adv_bulk", dataset_period="2026-06", decision_id=decision_id_2)
    second = drive_adv_bulk_dataset_silver_acceptance(
        ledger, bronze_root, revisions, processing, finalizer, silver,
        AdvBulkDatasetDriveResult(
            manifest=AdvBulkDatasetManifest(universe_label="t", candidates=(), unpublished_periods=()),
            outcomes=(outcome_2,),
        ),
    )
    decision_2 = second.outcomes[0].processing_decision
    assert decision_2.silver_outcome is SilverOutcome.PUBLISHED
    assert decision_2.expected_producers == ()


def test_fails_closed_on_an_unsupported_required_producers_set(tmp_path: Path) -> None:
    ledger, bronze_root, revisions, processing, finalizer, silver = _harness(tmp_path)
    try:
        drive_adv_bulk_dataset_silver_acceptance(
            ledger, bronze_root, revisions, processing, finalizer, silver,
            AdvBulkDatasetDriveResult(
                manifest=AdvBulkDatasetManifest(universe_label="t", candidates=(), unpublished_periods=()),
                outcomes=(),
            ),
            required_producers=("sec_adv_filing",),
        )
        raised = False
    except UnsupportedRequiredProducers:
        raised = True
    assert raised is True
