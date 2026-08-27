from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.ledger import (
    TERMINAL_NO_DOWNLOAD_DISPOSITIONS,
    AcquisitionLedger,
    ActiveFetchConflict,
    DecisionCause,
    DecisionOwnerRole,
    FetchDecisionRequest,
    FetchDisposition,
    FetchTransitionRole,
    FetchWorkState,
    InvalidDecisionEvidence,
    StaleFencingToken,
    UnauthorizedDecisionRole,
    UnauthorizedTransitionRole,
    execute_source_request,
)
from edgar_warehouse.acquisition.models import AcquisitionBase


def _ledger() -> AcquisitionLedger:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AcquisitionBase.metadata.create_all(engine)
    return AcquisitionLedger(engine)


def test_out_of_scope_candidate_is_terminal_without_network_request() -> None:
    ledger = _ledger()
    source_adapter = Mock(side_effect=AssertionError("network must not be called"))

    result = execute_source_request(
        ledger,
        FetchDecisionRequest(
            candidate_id="candidate-1",
            source_family="filing_artifact",
            logical_source_key="0000320193/0000320193-26-000001/primary-document",
            source_url="https://www.sec.gov/Archives/example.txt",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="discovery-manifest-1",
            disposition=FetchDisposition.OUT_OF_SCOPE,
            blocker="outside acquisition universe v1",
            next_action="NONE",
            scope_proof_reference="acquisition-universe-v1/exclusion-1",
        ),
        source_adapter,
        worker_id="worker-terminal",
    )

    assert result.adapter_result is None
    assert result.fetch_lease is None
    assert result.status.candidate_id == "candidate-1"
    assert result.status.observation_position == 1
    assert result.status.cause == DecisionCause.CAPTURED_DISCOVERY
    assert result.status.fetch_disposition == FetchDisposition.OUT_OF_SCOPE
    assert result.status.is_terminal is True
    assert result.status.blocker == "outside acquisition universe v1"
    assert result.status.next_action == "NONE"
    source_adapter.assert_not_called()


def test_decisions_are_idempotent_per_candidate_and_monotonic_per_logical_key() -> None:
    ledger = _ledger()
    first_request = FetchDecisionRequest(
        candidate_id="candidate-1",
        source_family="company_submissions",
        logical_source_key="0000320193/submissions",
        source_url="https://data.sec.gov/submissions/CIK0000320193.json",
        cause=DecisionCause.DUE_POLICY,
        cause_reference="poll-policy-v1/2026-08-22",
        disposition=FetchDisposition.DOWNLOAD_DEFERRED,
        blocker="poll window has not opened",
        next_action="RETRY_AT_NEXT_ELIGIBILITY",
        next_eligible_at=datetime(2026, 8, 23, tzinfo=UTC),
    )

    first = ledger.create_fetch_decision(first_request)
    retried = ledger.create_fetch_decision(first_request)
    second = ledger.create_fetch_decision(
        FetchDecisionRequest(
            **{
                **first_request.__dict__,
                "candidate_id": "candidate-2",
                "cause_reference": "poll-policy-v1/2026-08-23",
            }
        )
    )

    assert retried.decision_id == first.decision_id
    assert retried.observation_position == 1
    assert second.observation_position == 2


def test_only_three_no_download_dispositions_are_terminal() -> None:
    assert TERMINAL_NO_DOWNLOAD_DISPOSITIONS == {
        FetchDisposition.ALREADY_CAPTURED_VERIFIED,
        FetchDisposition.OUT_OF_SCOPE,
        FetchDisposition.OPERATOR_EXCLUDED,
    }

    ledger = _ledger()
    deferred = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id="candidate-deferred",
            source_family="company_submissions",
            logical_source_key="0000320193/submissions",
            source_url="https://data.sec.gov/submissions/CIK0000320193.json",
            cause=DecisionCause.DUE_POLICY,
            cause_reference="poll-policy-v1/2026-08-22",
            disposition=FetchDisposition.DOWNLOAD_DEFERRED,
            blocker="rate limited",
            next_action="RETRY_AT_NEXT_ELIGIBILITY",
            next_eligible_at=datetime(2026, 8, 22, 12, tzinfo=UTC),
        )
    )

    assert deferred.is_terminal is False
    assert deferred.blocker == "rate limited"
    assert deferred.next_action == "RETRY_AT_NEXT_ELIGIBILITY"


def test_operator_exclusion_requires_the_operator_decision_role() -> None:
    ledger = _ledger()

    status = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id="candidate-excluded",
            source_family="filing_artifact",
            logical_source_key="accession/document",
            source_url="https://www.sec.gov/Archives/example.txt",
            cause=DecisionCause.OPERATOR_REQUEST,
            cause_reference="operator-exclusion-42",
            disposition=FetchDisposition.OPERATOR_EXCLUDED,
            blocker="legal hold excludes acquisition",
            next_action="NONE",
            owner_role=DecisionOwnerRole.ACQUISITION_OPERATOR,
            operator_authorization_reference="operator-exclusion-42",
            exclusion_reason="Legal hold #42 excludes this filing from acquisition.",
        )
    )

    assert status.fetch_disposition is FetchDisposition.OPERATOR_EXCLUDED
    assert status.is_terminal is True
    assert status.exclusion_reason == "Legal hold #42 excludes this filing from acquisition."

    with pytest.raises(UnauthorizedDecisionRole):
        ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-unauthorized",
                source_family="filing_artifact",
                logical_source_key="other-accession/document",
                source_url="https://www.sec.gov/Archives/other.txt",
                cause=DecisionCause.OPERATOR_REQUEST,
                cause_reference="operator-exclusion-43",
                disposition=FetchDisposition.OPERATOR_EXCLUDED,
                blocker="attempted exclusion",
                next_action="NONE",
                operator_authorization_reference="operator-exclusion-43",
                exclusion_reason="Attempted exclusion.",
            )
        )


def test_operator_exclusion_requires_a_non_empty_reason() -> None:
    """Ticket 34: an exclusion must be reasoned, not just authorized --
    exclusion_reason and operator_authorization_reference are two distinct
    kinds of evidence (why vs. proof-of-authority), each independently
    required."""
    ledger = _ledger()

    with pytest.raises(InvalidDecisionEvidence, match="exclusion_reason"):
        ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-unreasoned-exclusion",
                source_family="filing_artifact",
                logical_source_key="accession/unreasoned",
                source_url="https://www.sec.gov/Archives/unreasoned.txt",
                cause=DecisionCause.OPERATOR_REQUEST,
                cause_reference="operator-exclusion-44",
                disposition=FetchDisposition.OPERATOR_EXCLUDED,
                blocker="attempted exclusion",
                next_action="NONE",
                owner_role=DecisionOwnerRole.ACQUISITION_OPERATOR,
                operator_authorization_reference="operator-exclusion-44",
                exclusion_reason="   ",
            )
        )


def _authorized_request(candidate_id: str) -> FetchDecisionRequest:
    return FetchDecisionRequest(
        candidate_id=candidate_id,
        source_family="filing_artifact",
        logical_source_key="0000320193/0000320193-26-000001/primary-document",
        source_url="https://www.sec.gov/Archives/example.txt",
        cause=DecisionCause.CAPTURED_DISCOVERY,
        cause_reference=f"discovery/{candidate_id}",
        disposition=FetchDisposition.FETCH_AUTHORIZED,
        blocker=None,
        next_action="ACQUIRE_FETCH_LEASE",
    )


def test_database_rejects_duplicate_active_fetch_for_one_logical_key() -> None:
    ledger = _ledger()
    first = ledger.create_fetch_decision(_authorized_request("candidate-active-1"))

    with pytest.raises(ActiveFetchConflict):
        ledger.create_fetch_decision(_authorized_request("candidate-active-2"))

    status = ledger.source_change_status(first.decision_id)
    assert status.fetch_state is FetchWorkState.READY
    assert status.next_action == "ACQUIRE_FETCH_LEASE"


def test_expired_lease_reacquires_with_higher_token_and_rejects_stale_finalize() -> (
    None
):
    ledger = _ledger()
    decision = ledger.create_fetch_decision(_authorized_request("candidate-fenced"))
    first = ledger.claim_fetch(
        decision.decision_id,
        worker_id="worker-1",
        lease_seconds=1,
        now=datetime(2026, 8, 22, 10, tzinfo=UTC),
    )
    second = ledger.claim_fetch(
        decision.decision_id,
        worker_id="worker-2",
        lease_seconds=60,
        now=datetime(2026, 8, 22, 10, 0, 2, tzinfo=UTC),
    )

    assert first.fencing_token == 1
    assert second.fencing_token == 2
    with pytest.raises(StaleFencingToken):
        ledger.finalize_fetch(
            decision.decision_id,
            worker_id="worker-1",
            fencing_token=first.fencing_token,
            final_state=FetchWorkState.CAPTURED,
            artifact_reference="filing_artifact/deadbeef",
            now=datetime(2026, 8, 22, 10, 0, 3, tzinfo=UTC),
        )

    completed = ledger.finalize_fetch(
        decision.decision_id,
        worker_id="worker-2",
        fencing_token=second.fencing_token,
        final_state=FetchWorkState.CAPTURED,
        artifact_reference="filing_artifact/deadbeef",
        now=datetime(2026, 8, 22, 10, 0, 3, tzinfo=UTC),
    )
    assert completed.fetch_state is FetchWorkState.CAPTURED
    assert completed.next_action == "MATERIALIZE_SOURCE_REVISION"


def test_failed_fetch_retries_same_decision_with_higher_fencing_token() -> None:
    ledger = _ledger()
    decision = ledger.create_fetch_decision(_authorized_request("candidate-retry"))
    first = ledger.claim_fetch(
        decision.decision_id,
        worker_id="worker-1",
        lease_seconds=60,
        now=datetime(2026, 8, 22, 10, tzinfo=UTC),
    )
    failed = ledger.finalize_fetch(
        decision.decision_id,
        worker_id="worker-1",
        fencing_token=first.fencing_token,
        final_state=FetchWorkState.FAILED,
        now=datetime(2026, 8, 22, 10, 0, 1, tzinfo=UTC),
    )

    retried = ledger.claim_fetch(
        decision.decision_id,
        worker_id="worker-2",
        lease_seconds=60,
        now=datetime(2026, 8, 22, 10, 0, 2, tzinfo=UTC),
    )

    assert failed.next_action == "RETRY_FETCH"
    assert retried.fencing_token == 2


def test_failed_finalize_records_failure_detail_as_durable_fetch_attempt_evidence() -> (
    None
):
    ledger = _ledger()
    decision = ledger.create_fetch_decision(_authorized_request("candidate-failure-detail"))
    lease = ledger.claim_fetch(
        decision.decision_id, worker_id="worker-1", lease_seconds=60
    )

    ledger.finalize_fetch(
        decision.decision_id,
        worker_id="worker-1",
        fencing_token=lease.fencing_token,
        final_state=FetchWorkState.FAILED,
        failure_detail="HTTP 503 Service Unavailable",
    )

    assert (
        ledger.latest_transition_reason(decision.decision_id)
        == "HTTP 503 Service Unavailable"
    )


def test_failed_finalize_without_detail_falls_back_to_the_generic_reason() -> None:
    ledger = _ledger()
    decision = ledger.create_fetch_decision(_authorized_request("candidate-no-detail"))
    lease = ledger.claim_fetch(
        decision.decision_id, worker_id="worker-1", lease_seconds=60
    )

    ledger.finalize_fetch(
        decision.decision_id,
        worker_id="worker-1",
        fencing_token=lease.fencing_token,
        final_state=FetchWorkState.FAILED,
    )

    assert ledger.latest_transition_reason(decision.decision_id) == "FETCH_FAILED"


def test_failure_detail_is_rejected_when_final_state_is_captured() -> None:
    ledger = _ledger()
    decision = ledger.create_fetch_decision(_authorized_request("candidate-bad-detail"))
    lease = ledger.claim_fetch(
        decision.decision_id, worker_id="worker-1", lease_seconds=60
    )

    with pytest.raises(ValueError, match="failure_detail"):
        ledger.finalize_fetch(
            decision.decision_id,
            worker_id="worker-1",
            fencing_token=lease.fencing_token,
            final_state=FetchWorkState.CAPTURED,
            artifact_reference="filing_artifact/deadbeef",
            failure_detail="this should never be set alongside CAPTURED",
        )


def test_stale_worker_finalize_cannot_overwrite_a_newer_fenced_success() -> None:
    """Bullet 5, exercised through the widened finalize_fetch signature: a
    stale worker holding an old fencing token must not be able to overwrite
    or downgrade work a newer fenced attempt already finalized as CAPTURED.
    """
    ledger = _ledger()
    decision = ledger.create_fetch_decision(_authorized_request("candidate-stale-worker"))
    stale = ledger.claim_fetch(
        decision.decision_id,
        worker_id="worker-stale",
        lease_seconds=1,
        now=datetime(2026, 8, 22, 10, tzinfo=UTC),
    )
    fresh = ledger.claim_fetch(
        decision.decision_id,
        worker_id="worker-fresh",
        lease_seconds=60,
        now=datetime(2026, 8, 22, 10, 0, 2, tzinfo=UTC),
    )
    ledger.finalize_fetch(
        decision.decision_id,
        worker_id="worker-fresh",
        fencing_token=fresh.fencing_token,
        final_state=FetchWorkState.CAPTURED,
        artifact_reference="filing_artifact/real-evidence",
        now=datetime(2026, 8, 22, 10, 0, 3, tzinfo=UTC),
    )

    with pytest.raises(StaleFencingToken):
        ledger.finalize_fetch(
            decision.decision_id,
            worker_id="worker-stale",
            fencing_token=stale.fencing_token,
            final_state=FetchWorkState.FAILED,
            failure_detail="stale worker's belated failure report",
            now=datetime(2026, 8, 22, 10, 0, 4, tzinfo=UTC),
        )

    status = ledger.source_change_status(decision.decision_id)
    assert status.fetch_state is FetchWorkState.CAPTURED
    assert status.captured_artifact_reference == "filing_artifact/real-evidence"


def test_source_adapter_receives_only_a_fenced_leased_decision() -> None:
    ledger = _ledger()
    source_adapter = Mock(return_value=b"source-bytes")

    result = execute_source_request(
        ledger,
        _authorized_request("candidate-gated-adapter"),
        source_adapter,
        worker_id="worker-gated",
        lease_seconds=60,
    )

    assert result.status.fetch_state is FetchWorkState.LEASED
    assert result.status.may_fetch is True
    assert result.fetch_lease is not None
    assert result.fetch_lease.fencing_token == 1
    source_adapter.assert_called_once_with(result.status, result.fetch_lease)

    second_adapter = Mock(side_effect=AssertionError("leased work cannot refetch"))
    with pytest.raises(ActiveFetchConflict):
        execute_source_request(
            ledger,
            _authorized_request("candidate-gated-adapter"),
            second_adapter,
            worker_id="worker-duplicate",
            lease_seconds=60,
        )
    second_adapter.assert_not_called()


def test_terminal_no_download_requires_authoritative_proof_reference() -> None:
    ledger = _ledger()

    with pytest.raises(InvalidDecisionEvidence, match="verified_evidence_reference"):
        ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-unproved-skip",
                source_family="filing_artifact",
                logical_source_key="accession/document",
                source_url="https://www.sec.gov/Archives/example.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="manifest-1",
                disposition=FetchDisposition.ALREADY_CAPTURED_VERIFIED,
                blocker="claimed prior capture",
                next_action="NONE",
            )
        )

    with pytest.raises(InvalidDecisionEvidence, match="scope_proof_reference"):
        ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-blank-proof",
                source_family="filing_artifact",
                logical_source_key="accession/blank-proof",
                source_url="https://www.sec.gov/Archives/blank-proof.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="manifest-2",
                disposition=FetchDisposition.OUT_OF_SCOPE,
                blocker="claimed scope exclusion",
                next_action="NONE",
                scope_proof_reference="   ",
            )
        )


def test_non_worker_role_cannot_claim_fetch_work() -> None:
    ledger = _ledger()
    decision = ledger.create_fetch_decision(_authorized_request("candidate-role-check"))

    with pytest.raises(UnauthorizedTransitionRole):
        ledger.claim_fetch(
            decision.decision_id,
            worker_id="not-a-worker",
            lease_seconds=60,
            actor_role=FetchTransitionRole.ACQUISITION_COORDINATOR,
        )


def test_postgres_unavailability_fails_closed_before_source_adapter() -> None:
    ledger = Mock(spec=AcquisitionLedger)
    ledger.create_fetch_decision.side_effect = OperationalError(
        "INSERT source_fetch_decision", {}, ConnectionError("postgres unavailable")
    )
    source_adapter = Mock(side_effect=AssertionError("network must not be called"))

    with pytest.raises(OperationalError):
        execute_source_request(
            ledger,
            _authorized_request("candidate-postgres-down"),
            source_adapter,
            worker_id="worker-postgres-down",
        )

    source_adapter.assert_not_called()
