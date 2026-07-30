from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "infra/scripts/check-dashboard-uat.py"


def _load():
    spec = importlib.util.spec_from_file_location("dashboard_uat", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skeleton_is_fail_closed_and_complete() -> None:
    module = _load()
    payload = module.skeleton("rc-1")
    failures = module.errors(payload)
    assert failures
    assert set(payload["browser_uat"]) == set(module.SCENARIOS)
    assert set(payload["automated_smoke"]["representative_reads"]) == set(
        module.WORKFLOWS
    )
    assert "operator_signoff.approved" in failures


def test_complete_evidence_passes_and_keeps_scope_separate() -> None:
    module = _load()
    payload = module.skeleton("rc-1")
    payload["release"] = {
        "git_commit": "a" * 40,
        "app_version": "sha-" + "a" * 12,
        "combined_source_digest": "b" * 64,
        "role": "EDGARTOOLS_PROD_DASHBOARD_OWNER",
        "decision_watermark": "unavailable",
        "graph_generation_id": "generation-1",
    }
    payload["automated_smoke"].update(
        app_exists=True,
        owner_grants_bounded=True,
        viewer_grants_bounded=True,
        stage_digest_verified=True,
    )
    for read in payload["automated_smoke"]["representative_reads"].values():
        read.update(query_id="query-1", elapsed_ms=10, row_count=0, passed=True)
    for result in payload["browser_uat"].values():
        result.update(
            passed=True, raw_exception_absent=True, secret_leakage_absent=True
        )
    payload["rollback"].update(
        restored_app_version="sha-" + "c" * 12,
        owner_smoke_passed=True,
        viewer_smoke_passed=True,
        verified_at="2026-07-29T12:00:00Z",
    )
    payload["operator_signoff"].update(
        operator="operator",
        signed_at="2026-07-29T12:01:00Z",
        approved=True,
    )
    assert module.errors(payload) == []
    assert "does not satisfy warehouse full-chain" in payload[
        "operator_signoff"
    ]["scope_acknowledgement"]
