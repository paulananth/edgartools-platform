"""Wayfinder release-readiness ticket 07 (Define Release-Bound Dashboard
Acceptance): validates infra/scripts/check-dashboard-acceptance.py, the
scorer for a Dashboard-Reviewer-filled dashboard-acceptance.json against the
CONTEXT.md "Release-Bound Dashboard Approval" gate.

This script only *scores* a filled-in artifact -- it never fabricates a
pass, since the whole point of the gate is that a human Dashboard Reviewer
opened all 25 views by hand.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "infra" / "scripts" / "check-dashboard-acceptance.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_dashboard_acceptance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return _load_module()


def _all_pass_state(mod, watermark: str = "wm-1"):
    state = mod.init_state(release_candidate="rc-1", release_watermark=watermark)
    for key in mod.VIEW_IDS:
        state = mod.record_check(
            state,
            key,
            status="pass",
            watermark_checked=watermark,
            operator="dashboard_reviewer",
            mutation_surface_clear=True,
            secret_leakage_clear=True,
            unbounded_output_clear=True,
            row_count_observed=10,
            checked_at="2026-07-29T12:00:00Z",
        )
    return state


class TestViewInventory:
    def test_exactly_35_views_covering_both_dashboards(self, mod):
        assert len(mod.VIEW_IDS) == 35
        dashboards = {key.split("::", 1)[0] for key in mod.VIEW_IDS}
        assert dashboards == {"EDGARTOOLS_DASHBOARD", "MDM_GRAPH_DASHBOARD"}

    def test_excludes_the_non_deployed_standalone_dashboard(self, mod):
        assert not any("edgar_universe" in key.lower() for key in mod.VIEW_IDS)

    def test_load_rejects_missing_view_key(self, mod, tmp_path):
        state = _all_pass_state(mod)
        payload = mod.to_evidence_json(state)
        del payload["views"][mod.VIEW_IDS[0]]
        path = tmp_path / "dashboard-acceptance.json"
        path.write_text(__import__("json").dumps(payload), encoding="utf-8")
        with pytest.raises(mod.SchemaError, match="missing"):
            mod.load_acceptance(path)

    def test_load_rejects_unknown_view_key(self, mod, tmp_path):
        state = _all_pass_state(mod)
        payload = mod.to_evidence_json(state)
        payload["views"]["EDGARTOOLS_DASHBOARD::not_a_real_view"] = payload["views"][mod.VIEW_IDS[0]]
        path = tmp_path / "dashboard-acceptance.json"
        path.write_text(__import__("json").dumps(payload), encoding="utf-8")
        with pytest.raises(mod.SchemaError, match="unknown"):
            mod.load_acceptance(path)

    @pytest.mark.parametrize("invalid_status", ["approved", "", None, 1])
    def test_load_rejects_status_outside_closed_enum(self, mod, tmp_path, invalid_status):
        payload = mod.to_evidence_json(_all_pass_state(mod))
        payload["views"][mod.VIEW_IDS[0]]["status"] = invalid_status
        path = tmp_path / "dashboard-acceptance.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(mod.SchemaError, match="status"):
            mod.load_acceptance(path)

    @pytest.mark.parametrize(
        ("field", "invalid_value"),
        [
            ("operator", None),
            ("operator", ""),
            ("checked_at", None),
            ("checked_at", ""),
            ("row_count_observed", None),
            ("row_count_observed", -1),
            ("row_count_observed", True),
            ("mutation_surface_clear", None),
            ("secret_leakage_clear", "yes"),
            ("unbounded_output_clear", 1),
        ],
    )
    def test_load_rejects_unattested_completed_check(
        self, mod, tmp_path, field, invalid_value
    ):
        payload = mod.to_evidence_json(_all_pass_state(mod))
        payload["views"][mod.VIEW_IDS[0]][field] = invalid_value
        path = tmp_path / "dashboard-acceptance.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(mod.SchemaError, match=field):
            mod.load_acceptance(path)


class TestOverallStatusPrecedence:
    """The four failure reasons must stay distinguishable -- collapsing them
    into a bare pass/fail is exactly the 'thin-sample approval' / 'stale-
    watermark approval' failure mode the gate exists to prevent."""

    def test_all_not_checked_is_not_ready_unchecked(self, mod):
        state = mod.init_state(release_candidate="rc-1", release_watermark="wm-1")
        status, reasons = mod.overall_status(state)
        assert status == "NOT_READY"
        assert reasons == ["unchecked"]

    def test_fully_passed_current_watermark_is_ready(self, mod):
        state = _all_pass_state(mod)
        status, reasons = mod.overall_status(state)
        assert status == "READY"
        assert reasons == []

    def test_invalid_in_memory_status_is_not_ready(self, mod):
        state = _all_pass_state(mod)
        key = mod.VIEW_IDS[0]
        state.views[key] = mod.ViewCheck(
            status="approved",
            watermark_checked="wm-1",
            operator="dashboard_reviewer",
            checked_at="2026-07-29T12:00:00Z",
            mutation_surface_clear=True,
            secret_leakage_clear=True,
            unbounded_output_clear=True,
            row_count_observed=10,
        )

        status, reasons = mod.overall_status(state)

        assert status == "NOT_READY"
        assert reasons == ["invalid"]

    def test_stale_watermark_after_rebase_is_not_ready_stale(self, mod):
        state = _all_pass_state(mod, watermark="wm-1")
        state = mod.rebase_watermark(state, "wm-2")
        status, reasons = mod.overall_status(state)
        assert status == "NOT_READY"
        assert reasons == ["stale"]

    def test_rebase_does_not_clear_prior_checks(self, mod):
        """Regression seam: a watermark rebase must flag staleness, not wipe
        the record of what was already reviewed."""
        state = _all_pass_state(mod, watermark="wm-1")
        state = mod.rebase_watermark(state, "wm-2")
        first_key = mod.VIEW_IDS[0]
        assert state.views[first_key].status == "pass"
        assert state.views[first_key].watermark_checked == "wm-1"

    def test_any_failed_view_is_not_ready_fail(self, mod):
        state = _all_pass_state(mod)
        key = mod.VIEW_IDS[3]
        state = mod.record_check(
            state, key, status="fail", watermark_checked="wm-1",
            operator="dashboard_reviewer", mutation_surface_clear=True,
            secret_leakage_clear=True, unbounded_output_clear=True,
            row_count_observed=10, checked_at="2026-07-29T12:00:00Z",
        )
        status, reasons = mod.overall_status(state)
        assert status == "NOT_READY"
        assert reasons == ["fail"]

    def test_thin_sample_pass_is_not_ready_thin_sample(self, mod):
        state = _all_pass_state(mod)
        key = mod.VIEW_IDS[5]
        state = mod.record_check(
            state, key, status="pass", watermark_checked="wm-1",
            operator="dashboard_reviewer", mutation_surface_clear=True,
            secret_leakage_clear=True, unbounded_output_clear=False,
            row_count_observed=10, checked_at="2026-07-29T12:00:00Z",
        )
        status, reasons = mod.overall_status(state)
        assert status == "NOT_READY"
        assert reasons == ["thin_sample"]

    def test_precedence_reports_unchecked_before_stale_before_fail_before_thin_sample(self, mod):
        """When multiple failure modes coexist, every applicable reason is
        reported (not just the first one found) -- an operator fixing 'fail'
        alone must not be told 'READY' while a thin-sample view still lurks."""
        state = _all_pass_state(mod, watermark="wm-1")
        state = mod.rebase_watermark(state, "wm-2")
        state = mod.record_check(
            state, mod.VIEW_IDS[10], status="fail", watermark_checked="wm-2",
            operator="dashboard_reviewer", mutation_surface_clear=True,
            secret_leakage_clear=True, unbounded_output_clear=True,
            row_count_observed=10, checked_at="2026-07-29T12:00:00Z",
        )
        status, reasons = mod.overall_status(state)
        assert status == "NOT_READY"
        assert set(reasons) == {"stale", "fail"}


class TestSkeletonEmission:
    def test_skeleton_has_all_35_views_not_checked(self, mod):
        skeleton = mod.emit_skeleton(release_candidate="rc-1", release_watermark="wm-1")
        assert len(skeleton["views"]) == 35
        assert all(v["status"] == "not_checked" for v in skeleton["views"].values())

    def test_skeleton_never_fabricates_a_pass(self, mod):
        skeleton = mod.emit_skeleton(release_candidate="rc-1", release_watermark="wm-1")
        assert all(v["status"] != "pass" for v in skeleton["views"].values())
