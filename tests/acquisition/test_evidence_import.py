from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.evidence_import import (
    ChecksumVerificationFailed,
    EvidenceImportLedger,
    InvalidImportEvidence,
)
from edgar_warehouse.acquisition.ledger import (
    DecisionOwnerRole,
    UnauthorizedTransitionRole,
)
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _ledger(tmp_path) -> EvidenceImportLedger:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AcquisitionBase.metadata.create_all(engine)
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    return EvidenceImportLedger(engine, bronze_root)


def test_import_evidence_verifies_checksum_writes_bronze_and_records_lineage(
    tmp_path,
) -> None:
    ledger = _ledger(tmp_path)
    payload = b"<XML>imported filing body</XML>"
    checksum = hashlib.sha256(payload).hexdigest()

    imported = ledger.import_evidence(
        source_family="filing_artifact",
        logical_source_key="0000320193/0000320193-26-000001/primary-document",
        source_environment="dev",
        source_bronze_reference="filing_artifact/0000320193-26-000001",
        payload=payload,
        expected_checksum=checksum,
        operator_authorization_reference="import-ticket-1",
        reason="Recovering a dev-only backfill after prod ledger loss.",
    )

    assert imported.raw_evidence_hash == checksum
    assert imported.local_bronze_reference == f"filing_artifact/{checksum}"
    assert imported.source_environment == "dev"
    assert imported.source_bronze_reference == "filing_artifact/0000320193-26-000001"

    stored = (tmp_path / "bronze" / "filing_artifact" / checksum).read_bytes()
    assert stored == payload


def test_import_evidence_is_idempotent_per_source_environment_and_reference(
    tmp_path,
) -> None:
    ledger = _ledger(tmp_path)
    payload = b"<XML>replayed import</XML>"
    checksum = hashlib.sha256(payload).hexdigest()
    kwargs = dict(
        source_family="filing_artifact",
        logical_source_key="accession/document",
        source_environment="dev",
        source_bronze_reference="filing_artifact/replayed",
        payload=payload,
        expected_checksum=checksum,
        operator_authorization_reference="import-ticket-2",
        reason="First import.",
    )

    first = ledger.import_evidence(**kwargs)
    second = ledger.import_evidence(
        **{**kwargs, "reason": "Replayed import call with a different reason."}
    )

    assert second.import_id == first.import_id
    assert second.reason == "First import."  # the original row, not re-written


def test_import_evidence_rejects_a_mismatched_checksum_before_writing_bronze(
    tmp_path,
) -> None:
    ledger = _ledger(tmp_path)
    payload = b"<XML>tampered or corrupted in transit</XML>"

    with pytest.raises(ChecksumVerificationFailed):
        ledger.import_evidence(
            source_family="filing_artifact",
            logical_source_key="accession/document",
            source_environment="dev",
            source_bronze_reference="filing_artifact/mismatched",
            payload=payload,
            expected_checksum="0" * 64,
            operator_authorization_reference="import-ticket-3",
            reason="Attempted import with a bad checksum.",
        )

    assert not (tmp_path / "bronze").exists()


def test_import_evidence_requires_a_non_empty_operator_authorization_reference(
    tmp_path,
) -> None:
    ledger = _ledger(tmp_path)
    payload = b"<XML>unauthorized import attempt</XML>"
    checksum = hashlib.sha256(payload).hexdigest()

    with pytest.raises(InvalidImportEvidence, match="operator_authorization_reference"):
        ledger.import_evidence(
            source_family="filing_artifact",
            logical_source_key="accession/document",
            source_environment="dev",
            source_bronze_reference="filing_artifact/unauthorized",
            payload=payload,
            expected_checksum=checksum,
            operator_authorization_reference="   ",
            reason="Missing authorization.",
        )


def test_import_evidence_requires_a_non_empty_reason(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    payload = b"<XML>unreasoned import attempt</XML>"
    checksum = hashlib.sha256(payload).hexdigest()

    with pytest.raises(InvalidImportEvidence, match="reason"):
        ledger.import_evidence(
            source_family="filing_artifact",
            logical_source_key="accession/document",
            source_environment="dev",
            source_bronze_reference="filing_artifact/unreasoned",
            payload=payload,
            expected_checksum=checksum,
            operator_authorization_reference="import-ticket-4",
            reason="   ",
        )


def test_import_evidence_requires_the_operator_role(tmp_path) -> None:
    ledger = _ledger(tmp_path)
    payload = b"<XML>wrong-role import attempt</XML>"
    checksum = hashlib.sha256(payload).hexdigest()

    with pytest.raises(UnauthorizedTransitionRole):
        ledger.import_evidence(
            source_family="filing_artifact",
            logical_source_key="accession/document",
            source_environment="dev",
            source_bronze_reference="filing_artifact/wrong-role",
            payload=payload,
            expected_checksum=checksum,
            operator_authorization_reference="import-ticket-5",
            reason="Wrong role attempt.",
            actor_role=DecisionOwnerRole.ACQUISITION_COORDINATOR,
        )


def test_identical_bytes_from_two_different_sources_share_one_local_bronze_object(
    tmp_path,
) -> None:
    """Content-addressed by construction: two imports of byte-identical
    evidence from different source environments/references land at the same
    local Bronze key, each still getting its own distinct lineage row."""
    ledger = _ledger(tmp_path)
    payload = b"<XML>same bytes, two origins</XML>"
    checksum = hashlib.sha256(payload).hexdigest()

    first = ledger.import_evidence(
        source_family="filing_artifact",
        logical_source_key="accession/document",
        source_environment="dev",
        source_bronze_reference="filing_artifact/origin-a",
        payload=payload,
        expected_checksum=checksum,
        operator_authorization_reference="import-ticket-6",
        reason="First origin.",
    )
    second = ledger.import_evidence(
        source_family="filing_artifact",
        logical_source_key="accession/document",
        source_environment="staging",
        source_bronze_reference="filing_artifact/origin-b",
        payload=payload,
        expected_checksum=checksum,
        operator_authorization_reference="import-ticket-7",
        reason="Second origin.",
    )

    assert first.import_id != second.import_id
    assert first.local_bronze_reference == second.local_bronze_reference == (
        f"filing_artifact/{checksum}"
    )
