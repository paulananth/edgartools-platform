from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.conflict import (
    ConflictAlreadyResolved,
    ConflictLedger,
    ConflictNotFound,
    InvalidResolutionEvidence,
)
from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
)
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.revisions import RevisionRelationship, SourceRevisionLedger


def _engine():
    return create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


def _harness():
    engine = _engine()
    AcquisitionBase.metadata.create_all(engine)
    return AcquisitionLedger(engine), SourceRevisionLedger(engine), ConflictLedger(engine)


def _captured_decision(ledger: AcquisitionLedger, *, candidate_id: str, logical_source_key: str) -> str:
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
    lease = ledger.claim_fetch(decision.decision_id, worker_id="worker-1", lease_seconds=300)
    ledger.finalize_fetch(
        decision.decision_id,
        worker_id="worker-1",
        fencing_token=lease.fencing_token,
        final_state=FetchWorkState.CAPTURED,
        artifact_reference="filing_artifact/original-hash",
    )
    return decision.decision_id


def _parent_revision(ledger: AcquisitionLedger, revisions: SourceRevisionLedger, *, key: str) -> str:
    decision_id = _captured_decision(ledger, candidate_id=f"candidate-{key}", logical_source_key=key)
    revision = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash="original-hash",
        canonical_source_hash="original-hash",
        domain_content_hash="original-hash",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )
    return revision.revision_id


def test_record_evidence_conflict_captures_both_hashes_and_the_quarantine_reference() -> None:
    _, _, conflicts = _harness()

    conflict = conflicts.record_evidence_conflict(
        relative_path="filings/sec/accession/primary.xml",
        existing_content_hash="original-hash",
        new_content_hash="conflicting-hash",
        quarantine_bronze_reference="filings/sec/accession/primary.xml.conflict/conflicting-hash",
        source_family="filing_artifact",
        logical_source_key="0000320193/acc-1",
    )

    assert conflict.status == "PENDING"
    assert conflict.existing_content_hash == "original-hash"
    assert conflict.new_content_hash == "conflicting-hash"
    assert conflict.repair_revision_id is None


def test_record_evidence_conflict_is_idempotent_per_quarantine_reference() -> None:
    _, _, conflicts = _harness()

    first = conflicts.record_evidence_conflict(
        relative_path="filings/sec/accession/primary.xml",
        existing_content_hash="original-hash",
        new_content_hash="conflicting-hash",
        quarantine_bronze_reference="filings/sec/accession/primary.xml.conflict/conflicting-hash",
    )
    second = conflicts.record_evidence_conflict(
        relative_path="filings/sec/accession/primary.xml",
        existing_content_hash="original-hash",
        new_content_hash="conflicting-hash",
        quarantine_bronze_reference="filings/sec/accession/primary.xml.conflict/conflicting-hash",
    )

    assert first.conflict_id == second.conflict_id


def test_list_pending_conflicts_excludes_repaired_ones() -> None:
    ledger, revisions, conflicts = _harness()
    parent_id = _parent_revision(ledger, revisions, key="key-pending")
    conflict = conflicts.record_evidence_conflict(
        relative_path="filings/sec/accession/primary.xml",
        existing_content_hash="original-hash",
        new_content_hash="conflicting-hash",
        quarantine_bronze_reference="q-1",
    )

    assert [c.conflict_id for c in conflicts.list_pending_conflicts()] == [conflict.conflict_id]

    conflicts.resolve_conflict(
        conflict.conflict_id,
        parent_revision_id=parent_id,
        accept="existing",
        operator_authorization_reference="jira/OPS-1",
        reason="confirmed a benign SEC-side re-serve, original bytes correct",
    )

    assert conflicts.list_pending_conflicts() == ()


def test_resolve_conflict_accepting_existing_leaves_source_revision_untouched() -> None:
    """Bullet 2: keeping the existing evidence closes the conflict "without
    rewriting history" -- provable structurally as zero new source_revision
    rows.
    """

    ledger, revisions, conflicts = _harness()
    parent_id = _parent_revision(ledger, revisions, key="key-keep-existing")
    conflict = conflicts.record_evidence_conflict(
        relative_path="filings/sec/accession/primary.xml",
        existing_content_hash="original-hash",
        new_content_hash="conflicting-hash",
        quarantine_bronze_reference="q-keep",
    )

    resolved, revision = conflicts.resolve_conflict(
        conflict.conflict_id,
        parent_revision_id=parent_id,
        accept="existing",
        operator_authorization_reference="jira/OPS-2",
        reason="original filing confirmed correct against SEC's own re-served copy",
    )

    assert resolved.status == "REPAIRED"
    assert resolved.repair_revision_id == parent_id
    assert resolved.operator_authorization_reference == "jira/OPS-2"
    assert resolved.resolution_reason.startswith("original filing confirmed")
    assert revision is None


def test_resolve_conflict_accepting_conflicting_materializes_a_repair_revision() -> None:
    ledger, revisions, conflicts = _harness()
    parent_id = _parent_revision(ledger, revisions, key="key-accept-conflicting")
    conflict = conflicts.record_evidence_conflict(
        relative_path="filings/sec/accession/primary.xml",
        existing_content_hash="original-hash",
        new_content_hash="conflicting-hash",
        quarantine_bronze_reference="filings/sec/accession/primary.xml.conflict/conflicting-hash",
    )

    resolved, revision = conflicts.resolve_conflict(
        conflict.conflict_id,
        parent_revision_id=parent_id,
        accept="conflicting",
        operator_authorization_reference="jira/OPS-3",
        reason="SEC confirmed the original capture was truncated; corrected bytes are authoritative",
    )

    assert resolved.status == "REPAIRED"
    assert revision is not None
    assert resolved.repair_revision_id == revision.revision_id
    assert revision.parent_revision_id == parent_id
    assert revision.revision_relationship is RevisionRelationship.REPAIR
    assert revision.raw_evidence_hash == "conflicting-hash"
    assert revision.bronze_artifact_reference == (
        "filings/sec/accession/primary.xml.conflict/conflicting-hash"
    )


def test_resolve_conflict_is_idempotent_for_a_matching_replay() -> None:
    ledger, revisions, conflicts = _harness()
    parent_id = _parent_revision(ledger, revisions, key="key-idem")
    conflict = conflicts.record_evidence_conflict(
        relative_path="filings/sec/accession/primary.xml",
        existing_content_hash="original-hash",
        new_content_hash="conflicting-hash",
        quarantine_bronze_reference="q-idem",
    )

    first, first_revision = conflicts.resolve_conflict(
        conflict.conflict_id,
        parent_revision_id=parent_id,
        accept="conflicting",
        operator_authorization_reference="jira/OPS-4",
        reason="corrected bytes confirmed authoritative",
    )
    second, second_revision = conflicts.resolve_conflict(
        conflict.conflict_id,
        parent_revision_id=parent_id,
        accept="conflicting",
        operator_authorization_reference="jira/OPS-4",
        reason="corrected bytes confirmed authoritative",
    )

    assert first.repair_revision_id == second.repair_revision_id
    assert second_revision is None  # settled state re-read, not re-materialized


def test_resolve_conflict_rejects_a_replay_with_a_different_outcome() -> None:
    ledger, revisions, conflicts = _harness()
    parent_id = _parent_revision(ledger, revisions, key="key-mismatch")
    conflict = conflicts.record_evidence_conflict(
        relative_path="filings/sec/accession/primary.xml",
        existing_content_hash="original-hash",
        new_content_hash="conflicting-hash",
        quarantine_bronze_reference="q-mismatch",
    )
    conflicts.resolve_conflict(
        conflict.conflict_id,
        parent_revision_id=parent_id,
        accept="existing",
        operator_authorization_reference="jira/OPS-5",
        reason="original confirmed correct",
    )

    with pytest.raises(ConflictAlreadyResolved):
        conflicts.resolve_conflict(
            conflict.conflict_id,
            parent_revision_id=parent_id,
            accept="conflicting",
            operator_authorization_reference="jira/OPS-6",
            reason="changed my mind",
        )


def test_resolve_conflict_requires_a_real_operator_authorization_reference_and_reason() -> None:
    ledger, revisions, conflicts = _harness()
    parent_id = _parent_revision(ledger, revisions, key="key-blank")
    conflict = conflicts.record_evidence_conflict(
        relative_path="filings/sec/accession/primary.xml",
        existing_content_hash="original-hash",
        new_content_hash="conflicting-hash",
        quarantine_bronze_reference="q-blank",
    )

    with pytest.raises(InvalidResolutionEvidence):
        conflicts.resolve_conflict(
            conflict.conflict_id,
            parent_revision_id=parent_id,
            accept="existing",
            operator_authorization_reference="   ",
            reason="a real reason",
        )
    with pytest.raises(InvalidResolutionEvidence):
        conflicts.resolve_conflict(
            conflict.conflict_id,
            parent_revision_id=parent_id,
            accept="existing",
            operator_authorization_reference="jira/OPS-7",
            reason="",
        )


def test_resolve_conflict_against_a_nonexistent_conflict_raises() -> None:
    _, _, conflicts = _harness()

    with pytest.raises(ConflictNotFound):
        conflicts.resolve_conflict(
            "does-not-exist",
            parent_revision_id="also-does-not-exist",
            accept="existing",
            operator_authorization_reference="jira/OPS-8",
            reason="n/a",
        )
