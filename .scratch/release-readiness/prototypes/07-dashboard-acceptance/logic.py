"""PROTOTYPE -- throwaway. Answers wayfinder ticket 07 (release-readiness map):
does a per-view acceptance-artifact schema correctly represent every
launch-critical dashboard view's UAT state, without letting a stale-watermark
check, a thin sample, or a mutation/secret/unbounded-output gap silently pass
as READY?

Pure logic only -- no I/O, no terminal code. tui.py is the throwaway shell.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class Status(StrEnum):
    NOT_CHECKED = "not_checked"
    PASS = "pass"
    FAIL = "fail"


class OverallStatus(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"


class ReadinessReason(StrEnum):
    INVALID_VIEW_INVENTORY = "invalid_view_inventory"
    INVALID_STATUS = "invalid_status"
    UNCHECKED_VIEWS = "unchecked_views"
    STALE_WATERMARK = "stale_watermark"
    FAILED_VIEWS = "failed_views"
    THIN_SAMPLE = "thin_sample"
    INVALID_ATTESTATION = "invalid_attestation"


class AttestingRole(StrEnum):
    DASHBOARD_REVIEWER = "dashboard_reviewer"


@dataclass(frozen=True)
class ViewDefinition:
    dashboard: str
    view_id: str
    label: str

    @property
    def key(self) -> str:
        return f"{self.dashboard}::{self.view_id}"


# Every real, Terraform-deployed, launch-critical dashboard view as of
# 2026-07-29. examples/dashboard/edgar_universe_dashboard.py is NOT deployed
# anywhere and is deliberately excluded.
VIEWS: tuple[ViewDefinition, ...] = (
    ViewDefinition("EDGARTOOLS_DASHBOARD", "summary.kpi_row", "Summary / KPI row"),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD", "summary.top_companies", "Summary / Top companies"
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD", "summary.by_form_type", "Summary / By form type"
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD", "summary.over_time_all", "Summary / Over time (all)"
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD", "summary.two_year_timeline", "Summary / 2yr timeline"
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD", "details.company_lookup", "Company Details / Lookup"
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD", "details.company_metadata", "Company Details / Metadata"
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD", "details.form_counts", "Company Details / Form counts"
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD",
        "details.recent_filings",
        "Company Details / Recent filings",
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD",
        "details.financial_factors",
        "Company Details / Financial factors",
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD", "details.company_timeline", "Company Details / Timeline"
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD",
        "details.er_consensus",
        "Company Details / Equity Research / Consensus",
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD",
        "details.er_guidance",
        "Company Details / Equity Research / Guidance",
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD",
        "details.er_earnings_calendar",
        "Company Details / Equity Research / Earnings calendar",
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD",
        "details.er_transcripts",
        "Company Details / Equity Research / Transcripts",
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD", "pipeline.pipeline_runs", "Pipeline / Pipeline runs"
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD", "pipeline.task_history", "Pipeline / Task history"
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD",
        "pipeline.dynamic_table_refresh",
        "Pipeline / Dynamic table refresh history",
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD",
        "pipeline.manifest_copy_history",
        "Pipeline / Manifest copy history",
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD",
        "pipeline.adv_fund_count_mismatches",
        "Pipeline / ADV fund count mismatches",
    ),
    ViewDefinition(
        "EDGARTOOLS_DASHBOARD",
        "pipeline.adv_fund_count_summary",
        "Pipeline / ADV fund count reconciliation summary",
    ),
    ViewDefinition("MDM_GRAPH_DASHBOARD", "overview", "Overview"),
    ViewDefinition("MDM_GRAPH_DASHBOARD", "mdm_overview", "MDM Overview"),
    ViewDefinition("MDM_GRAPH_DASHBOARD", "neo4j_overview", "Neo4j Overview"),
    ViewDefinition(
        "MDM_GRAPH_DASHBOARD", "mismatch_diagnostics", "Mismatch Diagnostics"
    ),
)

VIEW_IDS = tuple(view.key for view in VIEWS)
EXPECTED_VIEW_IDS = frozenset(VIEW_IDS)


@dataclass(frozen=True)
class SafetyChecks:
    mutation_surface_clear: bool | None = None
    secret_leakage_clear: bool | None = None
    unbounded_output_clear: bool | None = None

    @property
    def all_clear(self) -> bool:
        return (
            self.mutation_surface_clear is True
            and self.secret_leakage_clear is True
            and self.unbounded_output_clear is True
        )


@dataclass(frozen=True)
class ViewCheck:
    status: Status = Status.NOT_CHECKED
    watermark_checked: str | None = None
    operator: AttestingRole | None = None
    checked_at: str | None = None
    safety: SafetyChecks = SafetyChecks()
    row_count_observed: int | None = None
    note: str | None = None


@dataclass(frozen=True)
class DashboardAcceptanceState:
    release_candidate: str
    release_watermark: str
    views: dict[str, ViewCheck]


def init_state(
    release_candidate: str, release_watermark: str
) -> DashboardAcceptanceState:
    return DashboardAcceptanceState(
        release_candidate=release_candidate,
        release_watermark=release_watermark,
        views={key: ViewCheck() for key in VIEW_IDS},
    )


def record_check(
    state: DashboardAcceptanceState,
    view_key: str,
    *,
    status: Status | str,
    watermark_checked: str,
    operator: AttestingRole | str,
    safety: SafetyChecks,
    row_count_observed: int | None = None,
    note: str | None = None,
) -> DashboardAcceptanceState:
    """Pure: returns a new state with one view's check recorded."""
    if view_key not in state.views:
        raise KeyError(f"unknown view: {view_key}")
    status = Status(status)
    operator = AttestingRole(operator)
    check = ViewCheck(
        status=status,
        watermark_checked=watermark_checked,
        operator=operator,
        checked_at="SIMULATED_NOW",
        safety=safety,
        row_count_observed=row_count_observed,
        note=note,
    )
    new_views = dict(state.views)
    new_views[view_key] = check
    return replace(state, views=new_views)


def rebase_watermark(
    state: DashboardAcceptanceState, new_watermark: str
) -> DashboardAcceptanceState:
    """A new Release Data Watermark arrived (e.g. gold refreshed again).
    Pure: does NOT clear existing checks -- staleness is *detected*, not
    auto-fixed, so the acceptance artifact can show exactly which views
    still need a re-check.
    """
    return replace(state, release_watermark=new_watermark)


def unchecked_views(state: DashboardAcceptanceState) -> list[str]:
    return [k for k, c in state.views.items() if c.status == Status.NOT_CHECKED]


def failed_views(state: DashboardAcceptanceState) -> list[str]:
    return [k for k, c in state.views.items() if c.status == Status.FAIL]


def stale_views(state: DashboardAcceptanceState) -> list[str]:
    """Views checked pass/fail against a watermark that isn't the current one."""
    return [
        k
        for k, c in state.views.items()
        if c.status in {Status.PASS, Status.FAIL}
        and c.watermark_checked != state.release_watermark
    ]


def thin_sample_views(state: DashboardAcceptanceState) -> list[str]:
    """A view marked 'pass' but with one of the three hard sub-checks not
    explicitly cleared (None, not False) is a thin-sample pass in disguise --
    e.g. an operator eyeballed the screen without confirming mutation
    controls or checking for unbounded output.
    """
    return [
        k
        for k, c in state.views.items()
        if c.status == Status.PASS and not c.safety.all_clear
    ]


def invalid_status_views(state: DashboardAcceptanceState) -> list[str]:
    return [k for k, c in state.views.items() if not isinstance(c.status, Status)]


def invalid_attestation_views(state: DashboardAcceptanceState) -> list[str]:
    return [
        k
        for k, c in state.views.items()
        if c.status == Status.PASS
        and (
            c.operator != AttestingRole.DASHBOARD_REVIEWER
            or not c.checked_at
            or not isinstance(c.row_count_observed, int)
            or c.row_count_observed < 0
        )
    ]


def readiness_reasons(state: DashboardAcceptanceState) -> list[ReadinessReason]:
    reasons: list[ReadinessReason] = []
    if set(state.views) != EXPECTED_VIEW_IDS:
        reasons.append(ReadinessReason.INVALID_VIEW_INVENTORY)
    if invalid_status_views(state):
        reasons.append(ReadinessReason.INVALID_STATUS)
    if unchecked_views(state):
        reasons.append(ReadinessReason.UNCHECKED_VIEWS)
    if stale_views(state):
        reasons.append(ReadinessReason.STALE_WATERMARK)
    if failed_views(state):
        reasons.append(ReadinessReason.FAILED_VIEWS)
    if thin_sample_views(state):
        reasons.append(ReadinessReason.THIN_SAMPLE)
    if invalid_attestation_views(state):
        reasons.append(ReadinessReason.INVALID_ATTESTATION)
    return reasons


def overall_status(state: DashboardAcceptanceState) -> OverallStatus:
    if readiness_reasons(state):
        return OverallStatus.NOT_READY
    return OverallStatus.READY


def to_evidence_json(state: DashboardAcceptanceState) -> dict:
    return {
        "schema_version": 1,
        "release_candidate": state.release_candidate,
        "release_watermark": state.release_watermark,
        "overall_status": overall_status(state).value,
        "not_ready_reasons": [reason.value for reason in readiness_reasons(state)],
        "views": {
            k: {
                "dashboard": view.dashboard,
                "view_id": view.view_id,
                "status": c.status.value if isinstance(c.status, Status) else c.status,
                "watermark_checked": c.watermark_checked,
                "operator": c.operator.value
                if isinstance(c.operator, AttestingRole)
                else c.operator,
                "checked_at": c.checked_at,
                "mutation_surface_clear": c.safety.mutation_surface_clear,
                "secret_leakage_clear": c.safety.secret_leakage_clear,
                "unbounded_output_clear": c.safety.unbounded_output_clear,
                "row_count_observed": c.row_count_observed,
                "note": c.note,
            }
            for view in VIEWS
            if (k := view.key) in state.views
            for c in (state.views[k],)
        },
    }
