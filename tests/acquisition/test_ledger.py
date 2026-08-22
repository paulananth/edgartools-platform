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
        ),
        source_adapter,
    )

    assert result.adapter_result is None
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
        )
    )

    assert status.fetch_disposition is FetchDisposition.OPERATOR_EXCLUDED
    assert status.is_terminal is True

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
            now=datetime(2026, 8, 22, 10, 0, 3, tzinfo=UTC),
        )

    completed = ledger.finalize_fetch(
        decision.decision_id,
        worker_id="worker-2",
        fencing_token=second.fencing_token,
        final_state=FetchWorkState.CAPTURED,
        now=datetime(2026, 8, 22, 10, 0, 3, tzinfo=UTC),
    )
    assert completed.fetch_state is FetchWorkState.CAPTURED
    assert completed.next_action == "MATERIALIZE_SOURCE_REVISION"


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
        )

    source_adapter.assert_not_called()
