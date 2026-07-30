from dataclasses import replace

import logic
import pytest


def ready_state() -> logic.DashboardAcceptanceState:
    state = logic.init_state("rc-test", "wm-test")
    for view in logic.VIEWS:
        state = logic.record_check(
            state,
            view.key,
            status=logic.Status.PASS,
            watermark_checked=state.release_watermark,
            operator=logic.AttestingRole.DASHBOARD_REVIEWER,
            safety=logic.SafetyChecks(True, True, True),
            row_count_observed=0,
        )
    return state


def test_inventory_contains_exactly_25_unique_views() -> None:
    assert len(logic.VIEWS) == 25
    assert len(logic.EXPECTED_VIEW_IDS) == 25


def test_initial_state_is_not_ready_with_plain_schema_status() -> None:
    evidence = logic.to_evidence_json(logic.init_state("rc-test", "wm-test"))

    assert evidence["overall_status"] == "NOT_READY"
    assert evidence["not_ready_reasons"] == ["unchecked_views"]


def test_empty_inventory_cannot_be_ready() -> None:
    state = logic.DashboardAcceptanceState("rc-test", "wm-test", views={})

    assert logic.overall_status(state) == logic.OverallStatus.NOT_READY
    assert logic.readiness_reasons(state) == [
        logic.ReadinessReason.INVALID_VIEW_INVENTORY
    ]


def test_arbitrary_status_cannot_be_ready() -> None:
    state = ready_state()
    first_key = logic.VIEW_IDS[0]
    malformed = replace(
        state,
        views={
            **state.views,
            first_key: replace(state.views[first_key], status="approved"),
        },
    )

    assert logic.overall_status(malformed) == logic.OverallStatus.NOT_READY
    assert logic.ReadinessReason.INVALID_STATUS in logic.readiness_reasons(malformed)


def test_record_check_rejects_unknown_status_and_role() -> None:
    state = logic.init_state("rc-test", "wm-test")

    with pytest.raises(ValueError):
        logic.record_check(
            state,
            logic.VIEW_IDS[0],
            status="approved",
            watermark_checked="wm-test",
            operator=logic.AttestingRole.DASHBOARD_REVIEWER,
            safety=logic.SafetyChecks(True, True, True),
        )
    with pytest.raises(ValueError):
        logic.record_check(
            state,
            logic.VIEW_IDS[0],
            status=logic.Status.PASS,
            watermark_checked="wm-test",
            operator="release_owner",
            safety=logic.SafetyChecks(True, True, True),
        )


def test_all_25_valid_checks_are_ready() -> None:
    evidence = logic.to_evidence_json(ready_state())

    assert evidence["overall_status"] == "READY"
    assert evidence["not_ready_reasons"] == []
    assert len(evidence["views"]) == 25


def test_watermark_rebase_preserves_checks_and_marks_them_stale() -> None:
    state = logic.rebase_watermark(ready_state(), "wm-new")

    assert logic.overall_status(state) == logic.OverallStatus.NOT_READY
    assert logic.ReadinessReason.STALE_WATERMARK in logic.readiness_reasons(state)
    assert all(check.watermark_checked == "wm-test" for check in state.views.values())


def test_thin_sample_cannot_be_ready() -> None:
    state = ready_state()
    first_key = logic.VIEW_IDS[0]
    thin = replace(
        state,
        views={
            **state.views,
            first_key: replace(
                state.views[first_key],
                safety=logic.SafetyChecks(True, True, None),
            ),
        },
    )

    assert logic.ReadinessReason.THIN_SAMPLE in logic.readiness_reasons(thin)


def test_invalid_dashboard_reviewer_attestation_cannot_be_ready() -> None:
    state = ready_state()
    first_key = logic.VIEW_IDS[0]
    unattested = replace(
        state,
        views={
            **state.views,
            first_key: replace(state.views[first_key], operator=None),
        },
    )

    assert logic.ReadinessReason.INVALID_ATTESTATION in logic.readiness_reasons(
        unattested
    )
