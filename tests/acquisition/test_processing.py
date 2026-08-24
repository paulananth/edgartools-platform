from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as _session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
    ProcessingTransitionRole,
    UnauthorizedTransitionRole,
)
from edgar_warehouse.acquisition.models import AcquisitionBase, SourceProcessingDecisionRecord
from edgar_warehouse.acquisition.processing import (
    ExpectedProducerAlreadySettled,
    ExpectedProducerNotFound,
    ExpectedProducerOutcome,
    ExpectedProducerSpec,
    PriorRevisionNotSettled,
    ProcessingDisposition,
    ProcessingLedger,
    RevisionNotFound,
    SilverFinalizer,
    SilverOutcome,
    read_source_change_status_detail,
)
from edgar_warehouse.acquisition.revisions import SourceRevisionLedger


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _ledgers():
    engine = _engine()
    AcquisitionBase.metadata.create_all(engine)
    return (
        AcquisitionLedger(engine),
        SourceRevisionLedger(engine),
        ProcessingLedger(engine),
        SilverFinalizer(engine),
        engine,
    )


def _captured_decision(
    ledger: AcquisitionLedger,
    *,
    candidate_id: str,
    logical_source_key: str,
    source_family: str = "filing_artifact",
    artifact_reference: str = "filing_artifact/deadbeef",
    worker_id: str = "worker-1",
) -> str:
    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id=candidate_id,
            source_family=source_family,
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


def _changed_revision(
    ledger: AcquisitionLedger,
    revisions: SourceRevisionLedger,
    *,
    candidate_id: str,
    logical_source_key: str,
    domain_content_hash: str = "domain-1",
):
    decision_id = _captured_decision(
        ledger, candidate_id=candidate_id, logical_source_key=logical_source_key
    )
    return revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash=f"raw-{candidate_id}",
        canonical_source_hash=f"canonical-{candidate_id}",
        domain_content_hash=domain_content_hash,
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )


_ONE_PRODUCER = (
    ExpectedProducerSpec(
        producer_name="sec_raw_object",
        target_table="sec_raw_object",
        scope_reference="0000320193-26-000001",
    ),
)


def test_seal_expected_producers_records_full_processing_decision() -> None:
    ledger, revisions, processing, _finalizer, _engine = _ledgers()
    revision = _changed_revision(
        ledger, revisions, candidate_id="c1", logical_source_key="key-1"
    )

    decision = processing.seal_expected_producers(
        revision.revision_id, expected_producers=_ONE_PRODUCER
    )

    assert decision.revision_id == revision.revision_id
    assert decision.source_family == "filing_artifact"
    assert decision.logical_source_key == "key-1"
    assert decision.observation_position == revision.observation_position
    assert decision.disposition is ProcessingDisposition.PROCESS_REQUIRED
    assert decision.silver_outcome is SilverOutcome.PENDING
    assert len(decision.expected_producers) == 1
    producer = decision.expected_producers[0]
    assert producer.producer_name == "sec_raw_object"
    assert producer.target_table == "sec_raw_object"
    assert producer.scope_reference == "0000320193-26-000001"
    assert producer.outcome is ExpectedProducerOutcome.PENDING
    assert producer.verified_reference is None
    assert producer.failure_detail is None


def test_seal_expected_producers_no_impact_revision_seals_published_with_no_producers() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    first = _changed_revision(
        ledger, revisions, candidate_id="c1", logical_source_key="key-1", domain_content_hash="same"
    )
    first_decision = processing.seal_expected_producers(
        first.revision_id, expected_producers=_ONE_PRODUCER
    )
    finalizer.record_producer_outcome(
        first_decision.processing_decision_id,
        "sec_raw_object",
        outcome=ExpectedProducerOutcome.VERIFIED,
        verified_reference="ref-1",
    )

    second_decision_id = _captured_decision(
        ledger, candidate_id="c2", logical_source_key="key-1"
    )
    second = revisions.materialize_from_capture(
        second_decision_id,
        raw_evidence_hash="raw-c2",
        canonical_source_hash="canonical-c2",
        domain_content_hash="same",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )
    assert second.content_impact.value == "NO_IMPACT"

    decision = processing.seal_expected_producers(second.revision_id)

    assert decision.disposition is ProcessingDisposition.NO_IMPACT
    assert decision.silver_outcome is SilverOutcome.PUBLISHED
    assert decision.expected_producers == ()


def test_seal_expected_producers_changed_without_producers_raises() -> None:
    ledger, revisions, processing, _finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")

    with pytest.raises(ValueError, match="requires at least one expected producer"):
        processing.seal_expected_producers(revision.revision_id, expected_producers=())


def test_seal_expected_producers_no_impact_with_producers_raises() -> None:
    ledger, revisions, processing, _finalizer, _engine = _ledgers()
    _changed_revision(
        ledger, revisions, candidate_id="c1", logical_source_key="key-1", domain_content_hash="same"
    )
    second_decision_id = _captured_decision(ledger, candidate_id="c2", logical_source_key="key-1")
    second = revisions.materialize_from_capture(
        second_decision_id,
        raw_evidence_hash="raw-c2",
        canonical_source_hash="canonical-c2",
        domain_content_hash="same",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    with pytest.raises(ValueError, match="must not declare expected producers"):
        processing.seal_expected_producers(second.revision_id, expected_producers=_ONE_PRODUCER)


def test_seal_expected_producers_is_idempotent_per_revision() -> None:
    ledger, revisions, processing, _finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")

    first = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)
    second = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)

    assert first.processing_decision_id == second.processing_decision_id
    with _session(_engine) as session:
        rows = session.execute(
            select(SourceProcessingDecisionRecord).where(
                SourceProcessingDecisionRecord.revision_id == revision.revision_id
            )
        ).scalars().all()
    assert len(rows) == 1


def test_seal_expected_producers_unknown_revision_raises() -> None:
    _ledger, _revisions, processing, _finalizer, _engine = _ledgers()

    with pytest.raises(RevisionNotFound):
        processing.seal_expected_producers("does-not-exist", expected_producers=_ONE_PRODUCER)


def test_seal_expected_producers_wrong_role_raises() -> None:
    ledger, revisions, processing, _finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")

    class _NotAProcessor:
        value = "NOT_A_ROLE"

    with pytest.raises(UnauthorizedTransitionRole):
        processing.seal_expected_producers(
            revision.revision_id,
            expected_producers=_ONE_PRODUCER,
            actor_role=_NotAProcessor(),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# SilverFinalizer.record_producer_outcome
# ---------------------------------------------------------------------------


def test_record_producer_outcome_verified_publishes_single_producer_decision() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    decision = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)

    updated = finalizer.record_producer_outcome(
        decision.processing_decision_id,
        "sec_raw_object",
        outcome=ExpectedProducerOutcome.VERIFIED,
        verified_reference="raw-object-1",
    )

    assert updated.silver_outcome is SilverOutcome.PUBLISHED
    assert updated.expected_producers[0].outcome is ExpectedProducerOutcome.VERIFIED
    assert updated.expected_producers[0].verified_reference == "raw-object-1"


def test_record_producer_outcome_failed_marks_decision_failed() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    decision = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)

    updated = finalizer.record_producer_outcome(
        decision.processing_decision_id,
        "sec_raw_object",
        outcome=ExpectedProducerOutcome.FAILED,
        failure_detail="sha256 mismatch on read-back",
    )

    assert updated.silver_outcome is SilverOutcome.FAILED
    assert updated.expected_producers[0].outcome is ExpectedProducerOutcome.FAILED
    assert updated.expected_producers[0].failure_detail == "sha256 mismatch on read-back"


def test_record_producer_outcome_requires_every_producer_before_published() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    two_producers = (
        ExpectedProducerSpec("producer-a", "table_a", "scope-a"),
        ExpectedProducerSpec("producer-b", "table_b", "scope-b"),
    )
    decision = processing.seal_expected_producers(revision.revision_id, expected_producers=two_producers)

    after_first = finalizer.record_producer_outcome(
        decision.processing_decision_id,
        "producer-a",
        outcome=ExpectedProducerOutcome.VERIFIED,
        verified_reference="ref-a",
    )
    assert after_first.silver_outcome is SilverOutcome.PENDING

    after_second = finalizer.record_producer_outcome(
        decision.processing_decision_id,
        "producer-b",
        outcome=ExpectedProducerOutcome.NO_IMPACT,
    )
    assert after_second.silver_outcome is SilverOutcome.PUBLISHED


def test_record_producer_outcome_unknown_producer_raises() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    decision = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)

    with pytest.raises(ExpectedProducerNotFound):
        finalizer.record_producer_outcome(
            decision.processing_decision_id,
            "does-not-exist",
            outcome=ExpectedProducerOutcome.VERIFIED,
            verified_reference="ref",
        )


def test_record_producer_outcome_wrong_role_raises() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    decision = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)

    class _NotAFinalizer:
        value = "NOT_A_ROLE"

    with pytest.raises(UnauthorizedTransitionRole):
        finalizer.record_producer_outcome(
            decision.processing_decision_id,
            "sec_raw_object",
            outcome=ExpectedProducerOutcome.VERIFIED,
            verified_reference="ref",
            actor_role=_NotAFinalizer(),  # type: ignore[arg-type]
        )


def test_record_producer_outcome_verified_requires_reference() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    decision = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)

    with pytest.raises(ValueError, match="verified_reference"):
        finalizer.record_producer_outcome(
            decision.processing_decision_id,
            "sec_raw_object",
            outcome=ExpectedProducerOutcome.VERIFIED,
        )


def test_record_producer_outcome_failed_requires_detail() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    decision = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)

    with pytest.raises(ValueError, match="failure_detail"):
        finalizer.record_producer_outcome(
            decision.processing_decision_id,
            "sec_raw_object",
            outcome=ExpectedProducerOutcome.FAILED,
        )


def test_record_producer_outcome_idempotent_replay_returns_same_state() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    decision = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)

    first = finalizer.record_producer_outcome(
        decision.processing_decision_id,
        "sec_raw_object",
        outcome=ExpectedProducerOutcome.VERIFIED,
        verified_reference="ref-1",
    )
    second = finalizer.record_producer_outcome(
        decision.processing_decision_id,
        "sec_raw_object",
        outcome=ExpectedProducerOutcome.VERIFIED,
        verified_reference="ref-1",
    )

    assert first == second


def test_record_producer_outcome_conflicting_replay_raises() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    decision = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)
    finalizer.record_producer_outcome(
        decision.processing_decision_id,
        "sec_raw_object",
        outcome=ExpectedProducerOutcome.VERIFIED,
        verified_reference="ref-1",
    )

    with pytest.raises(ExpectedProducerAlreadySettled):
        finalizer.record_producer_outcome(
            decision.processing_decision_id,
            "sec_raw_object",
            outcome=ExpectedProducerOutcome.FAILED,
            failure_detail="disagreeing replay",
        )


# ---------------------------------------------------------------------------
# Bullet 4: same-key ordering
# ---------------------------------------------------------------------------


def test_seal_blocks_while_prior_revision_pending() -> None:
    ledger, revisions, processing, _finalizer, _engine = _ledgers()
    first = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    processing.seal_expected_producers(first.revision_id, expected_producers=_ONE_PRODUCER)

    second_decision_id = _captured_decision(ledger, candidate_id="c2", logical_source_key="key-1")
    second = revisions.materialize_from_capture(
        second_decision_id,
        raw_evidence_hash="raw-c2",
        canonical_source_hash="canonical-c2",
        domain_content_hash="different",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    with pytest.raises(PriorRevisionNotSettled):
        processing.seal_expected_producers(second.revision_id, expected_producers=_ONE_PRODUCER)


def test_seal_blocks_forever_after_prior_revision_failed_until_repaired() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    first = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    first_decision = processing.seal_expected_producers(first.revision_id, expected_producers=_ONE_PRODUCER)
    finalizer.record_producer_outcome(
        first_decision.processing_decision_id,
        "sec_raw_object",
        outcome=ExpectedProducerOutcome.FAILED,
        failure_detail="write failed",
    )

    second_decision_id = _captured_decision(ledger, candidate_id="c2", logical_source_key="key-1")
    second = revisions.materialize_from_capture(
        second_decision_id,
        raw_evidence_hash="raw-c2",
        canonical_source_hash="canonical-c2",
        domain_content_hash="different",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    # A Silver failure leaves PRIOR Silver authoritative and blocks LATER
    # revisions for the same key -- unlike an unsettled PENDING prior, a
    # FAILED prior never resolves on its own (Ticket 19 bullet 4).
    with pytest.raises(PriorRevisionNotSettled):
        processing.seal_expected_producers(second.revision_id, expected_producers=_ONE_PRODUCER)
    with pytest.raises(PriorRevisionNotSettled):
        processing.seal_expected_producers(second.revision_id, expected_producers=_ONE_PRODUCER)


def test_seal_proceeds_once_prior_revision_published() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    first = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-1")
    first_decision = processing.seal_expected_producers(first.revision_id, expected_producers=_ONE_PRODUCER)
    finalizer.record_producer_outcome(
        first_decision.processing_decision_id,
        "sec_raw_object",
        outcome=ExpectedProducerOutcome.VERIFIED,
        verified_reference="ref-1",
    )

    second_decision_id = _captured_decision(ledger, candidate_id="c2", logical_source_key="key-1")
    second = revisions.materialize_from_capture(
        second_decision_id,
        raw_evidence_hash="raw-c2",
        canonical_source_hash="canonical-c2",
        domain_content_hash="different",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    decision = processing.seal_expected_producers(second.revision_id, expected_producers=_ONE_PRODUCER)
    assert decision.silver_outcome is SilverOutcome.PENDING


def test_seal_for_unrelated_key_is_never_blocked_by_a_failed_key() -> None:
    ledger, revisions, processing, finalizer, _engine = _ledgers()
    failing = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-fails")
    failing_decision = processing.seal_expected_producers(
        failing.revision_id, expected_producers=_ONE_PRODUCER
    )
    finalizer.record_producer_outcome(
        failing_decision.processing_decision_id,
        "sec_raw_object",
        outcome=ExpectedProducerOutcome.FAILED,
        failure_detail="boom",
    )

    unrelated = _changed_revision(ledger, revisions, candidate_id="c2", logical_source_key="key-unrelated")
    decision = processing.seal_expected_producers(unrelated.revision_id, expected_producers=_ONE_PRODUCER)

    assert decision.silver_outcome is SilverOutcome.PENDING


def test_concurrent_seal_for_the_same_revision_converges_to_one_processing_decision() -> None:
    """Mirrors revisions.py's own concurrency proof: several threads racing
    to seal the same already-materialized revision must converge to exactly
    one Processing Decision row, backed by uq_source_processing_decision_revision.
    """

    db_path = Path(tempfile.mkstemp(suffix=".db")[1])
    engine = create_engine(f"sqlite:///{db_path}")
    AcquisitionBase.metadata.create_all(engine)
    ledger = AcquisitionLedger(engine)
    revisions = SourceRevisionLedger(engine)
    processing = ProcessingLedger(engine)
    revision = _changed_revision(ledger, revisions, candidate_id="c1", logical_source_key="key-race")

    results = []

    def _seal():
        results.append(
            processing.seal_expected_producers(
                revision.revision_id, expected_producers=_ONE_PRODUCER
            )
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: _seal(), range(8)))

    assert len(results) == 8
    assert len({d.processing_decision_id for d in results}) == 1
    with _session(engine) as session:
        rows = session.execute(
            select(SourceProcessingDecisionRecord).where(
                SourceProcessingDecisionRecord.revision_id == revision.revision_id
            )
        ).scalars().all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Bullet 3: extended Source Change Status projection
# ---------------------------------------------------------------------------


def test_source_change_status_detail_before_revision_materialized() -> None:
    ledger, _revisions, _processing, _finalizer, engine = _ledgers()
    decision_id = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-1")

    detail = read_source_change_status_detail(engine, decision_id)

    assert detail.fetch_disposition == FetchDisposition.FETCH_AUTHORIZED.value
    assert detail.fetch_state == FetchWorkState.CAPTURED.value
    assert detail.revision_id is None
    assert detail.processing_disposition is None
    assert detail.silver_outcome is None
    assert detail.next_action == "MATERIALIZE_SOURCE_REVISION"
    assert detail.is_fully_published is False


def test_source_change_status_detail_reflects_leased_and_failed_fetch_states() -> None:
    """Regression: read_source_change_status_detail's next_action mapping
    must match source_change_status_detail's SQL view CASE exactly for
    every fetch_state, not just CAPTURED -- an earlier version silently
    diverged for LEASED/FAILED (found by Spec review).
    """

    ledger, _revisions, _processing, _finalizer, engine = _ledgers()
    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id="c-leased",
            source_family="filing_artifact",
            logical_source_key="key-leased",
            source_url="https://www.sec.gov/Archives/c-leased.txt",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="discovery-manifest-1",
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
        )
    )
    ledger.claim_fetch(decision.decision_id, worker_id="worker-1", lease_seconds=300)
    leased = read_source_change_status_detail(engine, decision.decision_id)
    assert leased.fetch_state == FetchWorkState.LEASED.value
    assert leased.next_action == "FETCH_SOURCE"

    failed_decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id="c-failed",
            source_family="filing_artifact",
            logical_source_key="key-failed",
            source_url="https://www.sec.gov/Archives/c-failed.txt",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="discovery-manifest-1",
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
        )
    )
    lease = ledger.claim_fetch(
        failed_decision.decision_id, worker_id="worker-1", lease_seconds=300
    )
    ledger.finalize_fetch(
        failed_decision.decision_id,
        worker_id="worker-1",
        fencing_token=lease.fencing_token,
        final_state=FetchWorkState.FAILED,
    )
    failed = read_source_change_status_detail(engine, failed_decision.decision_id)
    assert failed.fetch_state == FetchWorkState.FAILED.value
    assert failed.next_action == "RETRY_FETCH"


def test_source_change_status_detail_reflects_pending_and_published() -> None:
    ledger, revisions, processing, finalizer, engine = _ledgers()
    decision_id = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-1")
    revision = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash="raw-1",
        canonical_source_hash="canonical-1",
        domain_content_hash="domain-1",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    unsealed = read_source_change_status_detail(engine, decision_id)
    assert unsealed.revision_id == revision.revision_id
    assert unsealed.content_impact == "CHANGED"
    assert unsealed.next_action == "SEAL_EXPECTED_PRODUCERS"

    decision = processing.seal_expected_producers(revision.revision_id, expected_producers=_ONE_PRODUCER)
    pending = read_source_change_status_detail(engine, decision_id)
    assert pending.processing_disposition == "PROCESS_REQUIRED"
    assert pending.silver_outcome == "PENDING"
    assert pending.expected_producer_total == 1
    assert pending.expected_producer_settled == 0
    assert pending.next_action == "FINALIZE_SILVER_PUBLICATION"

    finalizer.record_producer_outcome(
        decision.processing_decision_id,
        "sec_raw_object",
        outcome=ExpectedProducerOutcome.VERIFIED,
        verified_reference="ref-1",
    )
    published = read_source_change_status_detail(engine, decision_id)
    assert published.silver_outcome == "PUBLISHED"
    assert published.next_action == "NONE"
    assert published.is_fully_published is True


def test_ledger_source_change_status_shape_is_unchanged_by_ticket_19() -> None:
    """Ticket 19's own review constraint: AcquisitionLedger.source_change_status
    keeps its narrower shape and every existing caller untouched.
    """

    ledger, _revisions, _processing, _finalizer, _engine = _ledgers()
    decision_id = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-1")

    status = ledger.source_change_status(decision_id)

    assert not hasattr(status, "revision_id")
    assert not hasattr(status, "silver_outcome")
    assert status.captured_artifact_reference == "filing_artifact/deadbeef"
