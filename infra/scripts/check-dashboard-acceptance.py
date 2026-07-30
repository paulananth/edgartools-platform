#!/usr/bin/env python3
"""Score a dashboard-acceptance.json against release-readiness ticket 07
(CONTEXT.md's "Release-Bound Dashboard Approval" gate).

This script never fabricates a pass. It only reads an artifact a human
Dashboard Reviewer has already filled in (one entry per launch-critical
dashboard view, opened by hand against the current Release Candidate and
Release Data Watermark) and reports whether it is READY, and if not, every
distinct reason why -- unchecked views, a stale watermark, a failed view,
or a thin-sample pass (a "pass" missing one of its three sub-checks).

Usage:
    uv run python infra/scripts/check-dashboard-acceptance.py --emit-skeleton \
        --release-candidate rc-20260729-e0fa0eaafb09 \
        --release-watermark wm-2026-07-29T02:00Z \
        --out docs/release-readiness/dashboard-acceptance.json

    uv run python infra/scripts/check-dashboard-acceptance.py --check \
        docs/release-readiness/dashboard-acceptance.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

Status = Literal["not_checked", "pass", "fail"]
VALID_STATUSES = frozenset({"not_checked", "pass", "fail"})

# Every real, Terraform-deployed, launch-critical dashboard view as of
# release-readiness ticket 07 (2026-07-29). examples/dashboard/
# edgar_universe_dashboard.py is NOT Terraform-deployed anywhere and is
# deliberately excluded -- see ticket 07's Answer.
VIEWS: list[tuple[str, str, str]] = [
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
VIEW_LABELS = {f"{dash}::{vid}": label for dash, vid, label in VIEWS}


class SchemaError(ValueError):
    """The artifact does not match the ticket-07 view inventory."""


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
    checked_at: str | None = None,
    note: str | None = None,
) -> DashboardAcceptanceState:
    """Pure: returns a new state with one view's check recorded."""
    if view_key not in state.views:
        raise KeyError(f"unknown view: {view_key}")
    check = ViewCheck(
        status=status,
        watermark_checked=watermark_checked,
        operator=operator,
        checked_at=checked_at,
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

    Does NOT clear existing checks -- staleness is detected, not auto-fixed,
    so the artifact always shows exactly which views still need a re-check.
    """
    return replace(state, release_watermark=new_watermark)


def unchecked_views(state: DashboardAcceptanceState) -> list[str]:
    return [k for k, c in state.views.items() if c.status == "not_checked"]


def _completed_check_schema_errors(check: ViewCheck) -> list[str]:
    if check.status not in VALID_STATUSES:
        return ["status"]
    if check.status == "not_checked":
        return []

    errors: list[str] = []
    for field in ("watermark_checked", "operator", "checked_at"):
        value = getattr(check, field)
        if not isinstance(value, str) or not value.strip():
            errors.append(field)
    for field in (
        "mutation_surface_clear",
        "secret_leakage_clear",
        "unbounded_output_clear",
    ):
        if type(getattr(check, field)) is not bool:
            errors.append(field)
    if (
        type(check.row_count_observed) is not int
        or check.row_count_observed < 0
    ):
        errors.append("row_count_observed")
    return errors


def invalid_views(state: DashboardAcceptanceState) -> list[str]:
    """Views whose status or completed-check attestation is malformed."""
    return [
        key
        for key, check in state.views.items()
        if _completed_check_schema_errors(check)
    ]


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
    explicitly True is a thin-sample pass in disguise -- e.g. an operator
    eyeballed the screen without confirming mutation controls, secret
    leakage, or a row-count bound."""
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


def overall_status(state: DashboardAcceptanceState) -> tuple[str, list[str]]:
    """Returns (status, reasons). Every applicable reason is reported, not
    just the first one found -- an operator fixing one failure mode must not
    be told READY while another still applies."""
    reasons: list[str] = []
    if invalid_views(state):
        reasons.append("invalid")
    if unchecked_views(state):
        reasons.append("unchecked")
    if stale_views(state):
        reasons.append("stale")
    if failed_views(state):
        reasons.append("fail")
    if thin_sample_views(state):
        reasons.append("thin_sample")
    return ("NOT_READY" if reasons else "READY", reasons)


def to_evidence_json(state: DashboardAcceptanceState) -> dict:
    status, reasons = overall_status(state)
    return {
        "schema_version": 1,
        "release_candidate": state.release_candidate,
        "release_watermark": state.release_watermark,
        "overall_status": status,
        "not_ready_reasons": reasons,
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


def emit_skeleton(release_candidate: str, release_watermark: str) -> dict:
    """A skeleton for a Dashboard Reviewer to fill in by hand. Every view
    starts not_checked -- this never fabricates a pass."""
    return to_evidence_json(init_state(release_candidate, release_watermark))


def load_acceptance(path: Path) -> DashboardAcceptanceState:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_views = payload.get("views", {})

    present = set(raw_views)
    expected = set(VIEW_IDS)
    missing = expected - present
    unknown = present - expected
    if missing:
        raise SchemaError(f"missing view(s): {sorted(missing)}")
    if unknown:
        raise SchemaError(f"unknown view(s) not in the ticket-07 inventory: {sorted(unknown)}")

    views = {}
    for key, raw in raw_views.items():
        if not isinstance(raw, dict):
            raise SchemaError(f"{key}: view record must be an object")
        check = ViewCheck(
            status=raw.get("status", "not_checked"),
            watermark_checked=raw.get("watermark_checked"),
            operator=raw.get("operator"),
            checked_at=raw.get("checked_at"),
            mutation_surface_clear=raw.get("mutation_surface_clear"),
            secret_leakage_clear=raw.get("secret_leakage_clear"),
            unbounded_output_clear=raw.get("unbounded_output_clear"),
            row_count_observed=raw.get("row_count_observed"),
            note=raw.get("note"),
        )
        errors = _completed_check_schema_errors(check)
        if errors:
            raise SchemaError(f"{key}: invalid field(s): {', '.join(errors)}")
        views[key] = check
    return DashboardAcceptanceState(
        release_candidate=payload["release_candidate"],
        release_watermark=payload["release_watermark"],
        views=views,
    )


def _print_report(state: DashboardAcceptanceState) -> str:
    status, reasons = overall_status(state)
    lines = [f"Overall: {status}"]
    if reasons:
        lines.append(f"Reasons: {', '.join(reasons)}")
        for label, views in (
            ("invalid", invalid_views(state)),
            ("unchecked", unchecked_views(state)),
            ("stale", stale_views(state)),
            ("fail", failed_views(state)),
            ("thin_sample", thin_sample_views(state)),
        ):
            if views:
                lines.append(f"  {label}:")
                for key in views:
                    lines.append(f"    - {VIEW_LABELS.get(key, key)} ({key})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--emit-skeleton", action="store_true", help="Emit an all-not_checked skeleton.")
    mode.add_argument("--check", metavar="PATH", help="Score a filled-in dashboard-acceptance.json.")
    parser.add_argument("--release-candidate", help="Required with --emit-skeleton.")
    parser.add_argument("--release-watermark", help="Required with --emit-skeleton.")
    parser.add_argument("--out", help="Write --emit-skeleton output here instead of stdout.")
    args = parser.parse_args(argv)

    if args.emit_skeleton:
        if not args.release_candidate or not args.release_watermark:
            parser.error("--emit-skeleton requires --release-candidate and --release-watermark")
        skeleton = emit_skeleton(args.release_candidate, args.release_watermark)
        text = json.dumps(skeleton, indent=2) + "\n"
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0

    try:
        state = load_acceptance(Path(args.check))
    except SchemaError as exc:
        print(f"SCHEMA ERROR: {exc}", file=sys.stderr)
        return 2
    print(_print_report(state))
    status, _ = overall_status(state)
    return 0 if status == "READY" else 1


if __name__ == "__main__":
    sys.exit(main())
