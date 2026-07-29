"""PROTOTYPE -- throwaway. Answers wayfinder ticket 07 (release-readiness map):
does a per-view acceptance-artifact schema correctly represent every
launch-critical dashboard view's UAT state, without letting a stale-watermark
check, a thin sample, or a mutation/secret/unbounded-output gap silently pass
as READY?

Pure logic only -- no I/O, no terminal code. tui.py is the throwaway shell.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

Status = Literal["not_checked", "pass", "fail"]

# Every real, Terraform-deployed, launch-critical dashboard view as of
# 2026-07-29. examples/dashboard/edgar_universe_dashboard.py is NOT deployed
# anywhere and is deliberately excluded.
VIEWS: list[tuple[str, str, str]] = [
    # (dashboard, view_id, label)
    ("EDGARTOOLS_DASHBOARD", "summary.kpi_row", "Summary / KPI row"),
    ("EDGARTOOLS_DASHBOARD", "summary.top_companies", "Summary / Top companies"),
    ("EDGARTOOLS_DASHBOARD", "summary.by_form_type", "Summary / By form type"),
    ("EDGARTOOLS_DASHBOARD", "summary.over_time_all", "Summary / Over time (all)"),
    ("EDGARTOOLS_DASHBOARD", "summary.two_year_timeline", "Summary / 2yr timeline"),
    ("EDGARTOOLS_DASHBOARD", "details.company_lookup", "Company Details / Lookup"),
    ("EDGARTOOLS_DASHBOARD", "details.company_metadata", "Company Details / Metadata"),
    ("EDGARTOOLS_DASHBOARD", "details.form_counts", "Company Details / Form counts"),
    ("EDGARTOOLS_DASHBOARD", "details.recent_filings", "Company Details / Recent filings"),
    ("EDGARTOOLS_DASHBOARD", "details.financial_factors", "Company Details / Financial factors"),
    ("EDGARTOOLS_DASHBOARD", "details.company_timeline", "Company Details / Timeline"),
    ("EDGARTOOLS_DASHBOARD", "details.er_consensus", "Company Details / Equity Research / Consensus"),
    ("EDGARTOOLS_DASHBOARD", "details.er_guidance", "Company Details / Equity Research / Guidance"),
    ("EDGARTOOLS_DASHBOARD", "details.er_earnings_calendar", "Company Details / Equity Research / Earnings calendar"),
    ("EDGARTOOLS_DASHBOARD", "details.er_transcripts", "Company Details / Equity Research / Transcripts"),
    ("EDGARTOOLS_DASHBOARD", "pipeline.pipeline_runs", "Pipeline / Pipeline runs"),
    ("EDGARTOOLS_DASHBOARD", "pipeline.task_history", "Pipeline / Task history"),
    ("EDGARTOOLS_DASHBOARD", "pipeline.dynamic_table_refresh", "Pipeline / Dynamic table refresh history"),
    ("EDGARTOOLS_DASHBOARD", "pipeline.manifest_copy_history", "Pipeline / Manifest copy history"),
    ("EDGARTOOLS_DASHBOARD", "pipeline.adv_fund_count_mismatches", "Pipeline / ADV fund count mismatches"),
    ("EDGARTOOLS_DASHBOARD", "pipeline.adv_fund_count_summary", "Pipeline / ADV fund count reconciliation summary"),
    ("MDM_GRAPH_DASHBOARD", "overview", "Overview"),
    ("MDM_GRAPH_DASHBOARD", "mdm_overview", "MDM Overview"),
    ("MDM_GRAPH_DASHBOARD", "neo4j_overview", "Neo4j Overview"),
    ("MDM_GRAPH_DASHBOARD", "mismatch_diagnostics", "Mismatch Diagnostics"),
]

VIEW_IDS = [f"{dash}::{vid}" for dash, vid, _label in VIEWS]


@dataclass(frozen=True)
class ViewCheck:
    status: Status = "not_checked"
    watermark_checked: str | None = None
    operator: str | None = None
    checked_at: str | None = None
    mutation_surface_clear: bool | None = None
    secret_leakage_clear: bool | None = None
    unbounded_output_clear: bool | None = None
    row_count_observed: int | None = None
    note: str | None = None


@dataclass(frozen=True)
class DashboardAcceptanceState:
    release_candidate: str
    release_watermark: str
    views: dict[str, ViewCheck]


def init_state(release_candidate: str, release_watermark: str) -> DashboardAcceptanceState:
    return DashboardAcceptanceState(
        release_candidate=release_candidate,
        release_watermark=release_watermark,
        views={key: ViewCheck() for key in VIEW_IDS},
    )


def record_check(
    state: DashboardAcceptanceState,
    view_key: str,
    *,
    status: Status,
    watermark_checked: str,
    operator: str,
    mutation_surface_clear: bool,
    secret_leakage_clear: bool,
    unbounded_output_clear: bool,
    row_count_observed: int | None = None,
    note: str | None = None,
) -> DashboardAcceptanceState:
    """Pure: returns a new state with one view's check recorded."""
    if view_key not in state.views:
        raise KeyError(f"unknown view: {view_key}")
    check = ViewCheck(
        status=status,
        watermark_checked=watermark_checked,
        operator=operator,
        checked_at="SIMULATED_NOW",
        mutation_surface_clear=mutation_surface_clear,
        secret_leakage_clear=secret_leakage_clear,
        unbounded_output_clear=unbounded_output_clear,
        row_count_observed=row_count_observed,
        note=note,
    )
    new_views = dict(state.views)
    new_views[view_key] = check
    return replace(state, views=new_views)


def rebase_watermark(state: DashboardAcceptanceState, new_watermark: str) -> DashboardAcceptanceState:
    """A new Release Data Watermark arrived (e.g. gold refreshed again).
    Pure: does NOT clear existing checks -- staleness is *detected*, not
    auto-fixed, so the acceptance artifact can show exactly which views
    still need a re-check.
    """
    return replace(state, release_watermark=new_watermark)


def unchecked_views(state: DashboardAcceptanceState) -> list[str]:
    return [k for k, c in state.views.items() if c.status == "not_checked"]


def failed_views(state: DashboardAcceptanceState) -> list[str]:
    return [k for k, c in state.views.items() if c.status == "fail"]


def stale_views(state: DashboardAcceptanceState) -> list[str]:
    """Views checked pass/fail against a watermark that isn't the current one."""
    return [
        k
        for k, c in state.views.items()
        if c.status != "not_checked" and c.watermark_checked != state.release_watermark
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
        if c.status == "pass"
        and (
            c.mutation_surface_clear is not True
            or c.secret_leakage_clear is not True
            or c.unbounded_output_clear is not True
        )
    ]


def overall_status(state: DashboardAcceptanceState) -> str:
    if unchecked_views(state):
        return "NOT_READY (unchecked views remain)"
    if stale_views(state):
        return "NOT_READY (stale-watermark views)"
    if failed_views(state):
        return "NOT_READY (failed views)"
    if thin_sample_views(state):
        return "NOT_READY (thin-sample pass)"
    return "READY"


def to_evidence_json(state: DashboardAcceptanceState) -> dict:
    return {
        "schema_version": 1,
        "release_candidate": state.release_candidate,
        "release_watermark": state.release_watermark,
        "overall_status": overall_status(state),
        "views": {
            k: {
                "dashboard": k.split("::", 1)[0],
                "view_id": k.split("::", 1)[1],
                **{
                    field: getattr(c, field)
                    for field in (
                        "status",
                        "watermark_checked",
                        "operator",
                        "checked_at",
                        "mutation_surface_clear",
                        "secret_leakage_clear",
                        "unbounded_output_clear",
                        "row_count_observed",
                        "note",
                    )
                },
            }
            for k, c in state.views.items()
        },
    }
