"""Verifies daily_incremental's bounded Daily Identity Refresh wiring
(release-readiness ticket 45/49: "Decide whether/how to narrow
daily_incremental's Stage 0 and set its actual schedule").

Generates the real write_warehouse_mdm_gold_definition() state machine JSON
(same driver mechanism as
tests/architecture/test_gold_affecting_commands_task_sizing.py) and asserts:

- daily_incremental's default path (no refresh_mode input, or refresh_mode
  != "backstop") routes through the new bounded ComputeIdentityRefreshWindow
  -> Stage0CompanyIdentityBounded stages, NOT the full-universe ComputeWindows
  path that took 10h16m alone on the first prod execution (ticket 45's
  evidence).
- refresh_mode="backstop" still routes through the original, unchanged
  full-universe ComputeWindows -> Stage0CompanyIdentity pair (the weekly
  Identity Backstop Sweep ticket 45 requires as a coverage backstop).
- bootstrap's definition (a different workflow_name) is untouched by any of
  this -- it never had the full-universe Stage0 prefix in the first place.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

_WMG_START = "write_warehouse_mdm_gold_definition() {\n"
_WMG_END = "\nPY\n}\n"

_FAKE_MEDIUM_ARN = "arn:fake-wh-medium"
_FAKE_LARGE_ARN = "arn:fake-wh-large"


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_WMG_START)
    end = text.index(_WMG_END, start) + len(_WMG_END)
    return text[start:end]


def _generate_definition(workflow_name: str) -> dict:
    fn_source = _extract_function_source()
    tmp_root = REPO_ROOT / ".pytest_cache" / "daily_identity_refresh_state_machine_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "wmg_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / f"{workflow_name}.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'PUBLIC_SUBNET_IDS_JSON=\'["subnet-aaaa","subnet-bbbb"]\'\n'
            'SECURITY_GROUP_IDS_JSON=\'["sg-cccc"]\'\n'
            'MDM_RUN_LIMIT=100\n'
            'MDM_GRAPH_LIMIT=200\n'
            f'source "{fn_file.as_posix()}"\n'
            f'write_warehouse_mdm_gold_definition "{out_file.as_posix()}" '
            f'"{_FAKE_MEDIUM_ARN}" "arn:fake-mdm-small" "arn:fake-mdm-medium" "{_FAKE_LARGE_ARN}" '
            f'"{workflow_name}" "fake-bronze-bucket"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"{workflow_name} definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def daily_incremental_definition() -> dict:
    return _generate_definition("daily_incremental")


@pytest.fixture(scope="module")
def bootstrap_definition() -> dict:
    return _generate_definition("bootstrap")


def test_daily_incremental_starts_at_refresh_mode_check(daily_incremental_definition) -> None:
    assert daily_incremental_definition["StartAt"] == "RefreshModeCheck"


def test_daily_incremental_default_path_is_bounded_not_full_universe(daily_incremental_definition) -> None:
    """The Choice state's Default (no refresh_mode, or anything other than
    'backstop') must route to the new bounded stage, not the full-universe
    ComputeWindows path that caused the 10h16m Stage0 runtime."""
    states = daily_incremental_definition["States"]
    refresh_mode = states["RefreshMode"]
    assert refresh_mode["Type"] == "Choice"
    assert refresh_mode["Default"] == "ComputeIdentityRefreshWindow"

    compute_window = states["ComputeIdentityRefreshWindow"]
    cmd = compute_window["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "compute-identity-refresh-window" in cmd
    assert compute_window["Next"] == "Stage0CompanyIdentityBounded"

    bounded_stage0 = states["Stage0CompanyIdentityBounded"]
    assert bounded_stage0["Type"] == "Map"
    assert bounded_stage0["Next"] == "RunWarehouseTask"
    item_reader_key = bounded_stage0["ItemReader"]["Parameters"]["Key.$"]
    assert "cik_batches.jsonl" in item_reader_key, (
        "bounded Stage0 must read the cik_list batches file (seed-universe's batch shape), "
        f"got {item_reader_key!r}"
    )
    inner_cmd = bounded_stage0["ItemProcessor"]["States"]["RunCompanyIdentityBatch"][
        "Parameters"
    ]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "--cik-list" in inner_cmd
    assert "company-identity" in inner_cmd


def test_daily_incremental_backstop_path_is_unchanged_full_universe(daily_incremental_definition) -> None:
    """refresh_mode='backstop' must still route through the original,
    byte-for-byte-unchanged full-universe ComputeWindows -> Stage0CompanyIdentity
    pair -- ticket 45's Identity Backstop Sweep."""
    states = daily_incremental_definition["States"]
    refresh_mode = states["RefreshMode"]
    backstop_choice = next(
        c for c in refresh_mode["Choices"] if c.get("StringEquals") == "backstop"
    )
    assert backstop_choice["Next"] == "ComputeWindows"

    compute_windows = states["ComputeWindows"]
    cmd = compute_windows["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "compute-windows" in cmd
    assert "--total-cik-limit" in cmd and "'0'" in cmd, "backstop must still process the full, unbounded universe"
    assert compute_windows["Next"] == "Stage0CompanyIdentity"

    stage0 = states["Stage0CompanyIdentity"]
    assert stage0["Type"] == "Map"
    assert stage0["Next"] == "RunWarehouseTask"


def test_daily_incremental_both_stage0_variants_converge_on_run_warehouse_task(
    daily_incremental_definition,
) -> None:
    states = daily_incremental_definition["States"]
    assert states["Stage0CompanyIdentityBounded"]["Next"] == "RunWarehouseTask"
    assert states["Stage0CompanyIdentity"]["Next"] == "RunWarehouseTask"


def test_bootstrap_definition_has_no_refresh_mode_states(bootstrap_definition) -> None:
    """bootstrap never had the full-universe Stage0 prefix (it goes
    SeedUniverse -> RunWarehouseTask directly) -- ticket 45/49's narrowing is
    daily_incremental-specific and must not leak new states into bootstrap."""
    assert bootstrap_definition["StartAt"] == "SeedUniverse"
    for leaked_state in (
        "RefreshModeCheck",
        "RefreshMode",
        "ComputeIdentityRefreshWindow",
        "Stage0CompanyIdentityBounded",
        "ComputeWindows",
        "Stage0CompanyIdentity",
    ):
        assert leaked_state not in bootstrap_definition["States"]
