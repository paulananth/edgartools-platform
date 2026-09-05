"""Tests for change-propagation Ticket 11's acceptance evidence schema.

The ticket's own requirement: "success cannot be inferred from row counts
or clean logs alone." The single highest-value property this file proves
is that an empty ``processed_keys``/``skipped_keys`` record can never be
``passed=True`` -- everything else is binding real existing evidence
(``ContentImpact``, ``ExpectedProducerStatus``, ``ParityVerdict``,
``CauseAlignment``) onto one shared, secret-safe shape.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from edgar_warehouse.acquisition.acceptance_evidence import (
    ACCEPTANCE_EVIDENCE_SCHEMA_VERSION,
    AcceptanceEvidence,
    AcceptanceScenario,
    build_acceptance_evidence,
    from_cause_alignment,
    from_content_impact,
    from_expected_producer_status,
    from_parity_verdict,
    unavailable,
)
from edgar_warehouse.acquisition.capture_parity import (
    ParityScope,
    ParityVerdict,
    SetDiff,
)
from edgar_warehouse.acquisition.processing import ExpectedProducerOutcome, ExpectedProducerStatus
from edgar_warehouse.acquisition.revisions import ContentImpact
from edgar_warehouse.serving.watermark_aggregator import CauseAlignment


# -- the ticket's actual requirement -----------------------------------------


def test_success_cannot_be_inferred_from_a_clean_but_empty_record() -> None:
    """A record touching zero keys must never assert passed=True.

    A clean run with nothing selected/processed/skipped looks identical in
    logs to "everything worked" -- the ticket exists specifically to close
    this gap.
    """
    evidence = build_acceptance_evidence(
        scenario=AcceptanceScenario.NOOP_REPLAY,
        cause_reference="cause:2026-09-04:test",
        selected_keys=(),
        processed_keys=(),
        skipped_keys=(),
        passed=True,  # caller's mistaken claim
        reasons=(),
    )
    assert evidence.passed is False
    assert "no keys were selected, processed, or skipped" in " ".join(evidence.reasons)


def test_success_with_only_skipped_keys_is_allowed() -> None:
    """A genuine no-op replay processes nothing but must still show its work."""
    evidence = build_acceptance_evidence(
        scenario=AcceptanceScenario.NOOP_REPLAY,
        cause_reference="cause:2026-09-04:test",
        selected_keys=("320193/0001-25",),
        processed_keys=(),
        skipped_keys=("320193/0001-25",),
        passed=True,
        reasons=(),
    )
    assert evidence.passed is True
    assert evidence.reasons == ()


def test_a_reported_reason_forces_passed_false_even_if_caller_claims_true() -> None:
    evidence = build_acceptance_evidence(
        scenario=AcceptanceScenario.MODIFIED_KEY_PROPAGATION,
        cause_reference="cause:x",
        selected_keys=("k1",),
        processed_keys=("k1",),
        skipped_keys=(),
        passed=True,
        reasons=("silent gap on Verified Source Evidence: k1",),
    )
    assert evidence.passed is False


def test_unavailable_dimension_is_never_passed() -> None:
    """No populable evidence source today -- fail closed, not silently green."""
    evidence = unavailable(
        AcceptanceScenario.BOUNDED_MDM_CLOSURE,
        reason="Ticket 49 (1-hop candidate-neighbor expansion) is not yet built",
    )
    assert evidence.available is False
    assert evidence.passed is False
    assert evidence.selected_keys == ()
    assert evidence.processed_keys == ()


# -- secret-safety: the schema's field set is locked, not open-ended ---------


def test_schema_fields_are_exactly_the_known_safe_set() -> None:
    """References/hashes/counts only -- never a payload, DSN, or presigned URL.

    Locks the field set so a future addition (e.g. a raw response body or a
    connection string) fails this test and forces a conscious decision,
    mirroring Ticket 18's identity-field lock-down precedent.
    """
    field_names = {f.name for f in dataclasses.fields(AcceptanceEvidence)}
    assert field_names == {
        "schema_version",
        "scenario",
        "cause_reference",
        "selected_keys",
        "processed_keys",
        "skipped_keys",
        "cost_seconds",
        "cost_network_calls",
        "available",
        "passed",
        "reasons",
    }


def test_schema_version_is_stamped_on_every_record() -> None:
    evidence = build_acceptance_evidence(
        scenario=AcceptanceScenario.NOOP_REPLAY,
        cause_reference="cause:x",
        selected_keys=("k1",),
        processed_keys=(),
        skipped_keys=("k1",),
        passed=True,
        reasons=(),
    )
    assert evidence.schema_version == ACCEPTANCE_EVIDENCE_SCHEMA_VERSION


def test_to_dict_round_trips_every_field() -> None:
    evidence = build_acceptance_evidence(
        scenario=AcceptanceScenario.RETIRE,
        cause_reference="cause:x",
        selected_keys=("k1", "k2"),
        processed_keys=("k1",),
        skipped_keys=("k2",),
        passed=True,
        reasons=(),
        cost_seconds=1.5,
        cost_network_calls=3,
    )
    payload = evidence.to_dict()
    assert payload["scenario"] == "RETIRE"
    assert payload["selected_keys"] == ["k1", "k2"]
    assert payload["processed_keys"] == ["k1"]
    assert payload["skipped_keys"] == ["k2"]
    assert payload["cost_seconds"] == 1.5
    assert payload["cost_network_calls"] == 3
    assert payload["passed"] is True


# -- adapters bind real existing evidence, they don't re-model it -----------


def test_from_content_impact_no_impact_is_a_noop_replay() -> None:
    evidence = from_content_impact(
        ContentImpact.NO_IMPACT,
        cause_reference="cause:x",
        logical_source_key="320193/0001-25",
    )
    assert evidence.scenario is AcceptanceScenario.NOOP_REPLAY
    assert evidence.processed_keys == ()
    assert evidence.skipped_keys == ("320193/0001-25",)
    assert evidence.passed is True


def test_from_content_impact_changed_is_modified_key_propagation() -> None:
    evidence = from_content_impact(
        ContentImpact.CHANGED,
        cause_reference="cause:x",
        logical_source_key="320193/0001-25",
    )
    assert evidence.scenario is AcceptanceScenario.MODIFIED_KEY_PROPAGATION
    assert evidence.processed_keys == ("320193/0001-25",)
    assert evidence.skipped_keys == ()
    assert evidence.passed is True


def test_from_expected_producer_status_verified_passes() -> None:
    status = ExpectedProducerStatus(
        expected_producer_id="ep-1",
        producer_name="sec_raw_object",
        target_table="sec_raw_object",
        scope_reference="0001-25",
        outcome=ExpectedProducerOutcome.VERIFIED,
        verified_reference="raw_object_id_abc",
        failure_detail=None,
    )
    evidence = from_expected_producer_status(
        status, cause_reference="cause:x", scenario=AcceptanceScenario.SCOPE_COMPLETE
    )
    assert evidence.passed is True
    assert evidence.processed_keys == ("0001-25",)


def test_from_expected_producer_status_pending_is_a_partial_load_resume() -> None:
    status = ExpectedProducerStatus(
        expected_producer_id="ep-1",
        producer_name="sec_raw_object",
        target_table="sec_raw_object",
        scope_reference="0001-25",
        outcome=ExpectedProducerOutcome.PENDING,
        verified_reference=None,
        failure_detail=None,
    )
    evidence = from_expected_producer_status(
        status, cause_reference="cause:x", scenario=AcceptanceScenario.PARTIAL_LOAD_RESUME
    )
    assert evidence.passed is False
    assert evidence.selected_keys == ("0001-25",)
    assert evidence.processed_keys == ()


def test_from_expected_producer_status_failed_reports_failure_detail() -> None:
    status = ExpectedProducerStatus(
        expected_producer_id="ep-1",
        producer_name="sec_raw_object",
        target_table="sec_raw_object",
        scope_reference="0001-25",
        outcome=ExpectedProducerOutcome.FAILED,
        verified_reference=None,
        failure_detail="read-back sha256 mismatch",
    )
    evidence = from_expected_producer_status(
        status, cause_reference="cause:x", scenario=AcceptanceScenario.SCOPE_COMPLETE
    )
    assert evidence.passed is False
    assert "read-back sha256 mismatch" in evidence.reasons


def test_from_parity_verdict_binds_ticket_51_evidence_unmodified() -> None:
    scope = ParityScope(business_date="2026-09-04", cik_list=(320193,), limit=1)
    empty_diff = SetDiff(only_legacy=frozenset(), only_gated=frozenset(), shared=frozenset({"k1"}))
    verdict = ParityVerdict(
        passed=True,
        reasons=(),
        scope=scope,
        logical_source_keys=empty_diff,
        verified_evidence=empty_diff,
        source_fetch_decisions=empty_diff,
        out_of_scope_ciks=frozenset(),
    )
    evidence = from_parity_verdict(verdict, cause_reference="cause:x")
    assert evidence.scenario is AcceptanceScenario.MODIFIED_KEY_PROPAGATION
    assert evidence.passed is True
    assert evidence.processed_keys == ("k1",)


def test_from_parity_verdict_counts_only_gated_keys_as_processed() -> None:
    """only_gated is a real, expected case under "equal-or-superset" --
    the gated path finding more than legacy must not silently vanish from
    the record (a real bug Spec review caught: the first draft dropped it).
    """
    scope = ParityScope(business_date="2026-09-04", cik_list=(320193,), limit=1)
    diff = SetDiff(only_legacy=frozenset(), only_gated=frozenset({"k2"}), shared=frozenset({"k1"}))
    verdict = ParityVerdict(
        passed=True,
        reasons=(),
        scope=scope,
        logical_source_keys=diff,
        verified_evidence=diff,
        source_fetch_decisions=diff,
        out_of_scope_ciks=frozenset(),
    )
    evidence = from_parity_verdict(verdict, cause_reference="cause:x")
    assert set(evidence.selected_keys) == {"k1", "k2"}
    assert set(evidence.processed_keys) == {"k1", "k2"}


def test_from_cause_alignment_binds_ticket_41_evidence_unmodified() -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    row = CauseAlignment(
        cause_reference="cause:x",
        business_date="2026-09-04",
        silver_complete=True,
        mdm_complete=True,
        gold_complete=True,
        graph_parity_ok=True,
        gold_run_id="gold-run-1",
        graph_generation_id="gen-1",
        aligned=True,
        stuck_stage=None,
        first_seen_at=now,
        aligned_at=now,
    )
    evidence = from_cause_alignment(row)
    assert evidence.scenario is AcceptanceScenario.DECISION_WATERMARK_ALIGNMENT
    assert evidence.passed is True
    assert evidence.processed_keys == ("cause:x",)


def test_from_cause_alignment_stuck_stage_fails_with_reason() -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    row = CauseAlignment(
        cause_reference="cause:x",
        business_date="2026-09-04",
        silver_complete=True,
        mdm_complete=False,
        gold_complete=False,
        graph_parity_ok=False,
        gold_run_id="",
        graph_generation_id="",
        aligned=False,
        stuck_stage="mdm",
        first_seen_at=now,
        aligned_at=None,
    )
    evidence = from_cause_alignment(row)
    assert evidence.passed is False
    assert "mdm" in " ".join(evidence.reasons)


@pytest.mark.parametrize(
    "scenario",
    [
        AcceptanceScenario.BOUNDED_MDM_CLOSURE,
        AcceptanceScenario.RECONCILIATION_BACKSTOP,
    ],
)
def test_genuinely_unbuilt_scenarios_are_recorded_as_unavailable(
    scenario: AcceptanceScenario,
) -> None:
    """Tickets 49/50 (1-hop expansion, reconciliation backstop) are not yet
    built -- this scenario has no populable evidence source today.
    """
    evidence = unavailable(scenario, reason="not yet built")
    assert evidence.available is False
    assert evidence.passed is False
