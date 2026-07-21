"""Structural checks on the generated daily_incremental Step Functions definition.

Covers the Company Identity Pipeline wayfinder map's ticket 06 (see
.scratch/company-master-pipeline/issues/06-daily-mode-state-machine-shape.md):

- daily_incremental is restructured with a new Stage0CompanyIdentity phase,
  reusing ticket 05's exact windowed capture shape (ComputeWindows + a
  strict, MaxConcurrency=1 Map), ahead of the existing RunWarehouseTask/MDM
  chain.
- bootstrap (the other caller of write_warehouse_mdm_gold_definition) is
  explicitly untouched -- ticket 06 scoped the restructure to
  daily_incremental only.

These tests generate the real JSON by sourcing the actual bash function (no
duplicated/hand-maintained copy of the state machine shape) and asserting on
the output, mirroring test_load_history_state_machine.py's approach.
Network-free: no AWS calls, only local JSON generation via python3
subprocesses that the deploy script itself launches.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

_START_MARKER = "write_warehouse_mdm_gold_definition() {\n"
_END_MARKER = "\nPY\n}\n"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_START_MARKER)
    end = text.index(_END_MARKER, start) + len(_END_MARKER)
    return text[start:end]


def _generate(workflow_name: str) -> dict:
    fn_source = _extract_function_source()

    tmp_root = REPO_ROOT / ".pytest_cache" / "daily_incremental_sm_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "warehouse_mdm_gold_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / f"{workflow_name}.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'BRONZE_BUCKET_NAME="fake-bronze-bucket"\n'
            "PUBLIC_SUBNET_IDS_JSON='[\"subnet-aaaa\",\"subnet-bbbb\"]'\n"
            "SECURITY_GROUP_IDS_JSON='[\"sg-cccc\"]'\n"
            "MDM_RUN_LIMIT=100\n"
            "MDM_GRAPH_LIMIT=200\n"
            f'source "{fn_file.as_posix()}"\n'
            f'write_warehouse_mdm_gold_definition "{out_file.as_posix()}" '
            '"arn:wh-medium" "arn:mdm-small" "arn:mdm-medium" "arn:wh-large" '
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
def daily_definition() -> dict:
    return _generate("daily_incremental")


@pytest.fixture(scope="module")
def bootstrap_definition() -> dict:
    return _generate("bootstrap")


def _command_of_state(state: dict) -> str:
    if state.get("Type") == "Map":
        proc_states = state["ItemProcessor"]["States"]
        return " ".join(_command_of_state(s) for s in proc_states.values())
    containers = state.get("Parameters", {}).get("Overrides", {}).get("ContainerOverrides", [])
    return containers[0]["Command.$"] if containers else ""


def _command_of(definition: dict, state_name: str) -> str:
    return _command_of_state(definition["States"][state_name])


def _linear_order(definition: dict) -> list[str]:
    states = definition["States"]

    def next_of(state: dict) -> str | None:
        if "Next" in state:
            return state["Next"]
        return None

    order: list[str] = []
    seen: set[str] = set()
    name = definition["StartAt"]
    while name and name not in seen:
        seen.add(name)
        order.append(name)
        name = next_of(states[name])
    return order


# -- structural integrity ----------------------------------------------------


def test_generates_valid_json_with_no_dangling_references(daily_definition: dict) -> None:
    def check(states: dict, start_at: str, label: str) -> None:
        assert start_at in states, f"{label}: StartAt not defined"
        for name, state in states.items():
            nxt = state.get("Next")
            if nxt is not None:
                assert nxt in states, f"{label}.{name}: Next={nxt!r} undefined"
            for catch in state.get("Catch", []):
                cnxt = catch.get("Next")
                if cnxt is not None:
                    assert cnxt in states, f"{label}.{name}: Catch Next={cnxt!r} undefined"
            if state.get("Type") == "Map":
                proc = state["ItemProcessor"]
                check(proc["States"], proc["StartAt"], f"{label}.{name}(Map)")

    check(daily_definition["States"], daily_definition["StartAt"], "top")


# -- ticket 06: Stage0CompanyIdentity woven into daily_incremental -----------


def test_daily_incremental_starts_with_compute_windows(daily_definition: dict) -> None:
    assert daily_definition["StartAt"] == "ComputeWindows"


def test_daily_incremental_stage0_company_identity_runs_before_run_warehouse_task(
    daily_definition: dict,
) -> None:
    order = _linear_order(daily_definition)
    assert "ComputeWindows" in order
    assert "Stage0CompanyIdentity" in order
    assert "RunWarehouseTask" in order
    assert order.index("ComputeWindows") < order.index("Stage0CompanyIdentity")
    assert order.index("Stage0CompanyIdentity") < order.index("RunWarehouseTask")


def test_daily_incremental_stage0_company_identity_command_shape(daily_definition: dict) -> None:
    cmd = _command_of(daily_definition, "Stage0CompanyIdentity")
    assert "'bootstrap-fundamentals'" in cmd
    assert "'--mode', 'company-identity'" in cmd
    assert "'--cik-offset'" in cmd
    assert "'--cik-limit'" in cmd


def test_daily_incremental_stage0_company_identity_is_strict_not_lenient(
    daily_definition: dict,
) -> None:
    state = daily_definition["States"]["Stage0CompanyIdentity"]
    assert state["Type"] == "Map"
    assert state["MaxConcurrency"] == 1
    assert state["ToleratedFailurePercentage"] == 0
    assert "Catch" not in state


def test_daily_incremental_stage0_company_identity_uses_distributed_mode(
    daily_definition: dict,
) -> None:
    """AWS Step Functions rejects ItemReader on an INLINE Map -- must match
    load_history's already-working DISTRIBUTED pattern (fix-pipelines 06-03)."""
    state = daily_definition["States"]["Stage0CompanyIdentity"]
    assert "ItemReader" in state
    assert state["ItemProcessor"]["ProcessorConfig"]["Mode"] == "DISTRIBUTED"
    assert state["ItemProcessor"]["ProcessorConfig"]["ExecutionType"] == "STANDARD"


def test_daily_incremental_no_seed_universe(daily_definition: dict) -> None:
    """daily_incremental deliberately skips seed-universe/MdmSeedUniverse --
    it processes the already-tracked universe for daily updates, not
    newly-discovered CIKs. This must remain true after the restructure."""
    assert "SeedUniverse" not in daily_definition["States"]
    assert "MdmSeedUniverse" not in daily_definition["States"]


def test_daily_incremental_mdm_run_still_uses_entity_type_all(daily_definition: dict) -> None:
    """No dedicated --entity-type company MDM call: the existing
    --entity-type all call already resolves companies as part of its sweep
    (run_all() calls run_companies())."""
    cmd = _command_of(daily_definition, "MdmRun")
    assert "'--entity-type', 'all'" in cmd


def test_daily_incremental_no_dedicated_gold_refresh_for_company_identity(
    daily_definition: dict,
) -> None:
    """Exactly one GoldRefresh state -- company-identity feeds the existing
    single gold-refresh, no dedicated refresh added."""
    gold_refresh_states = [name for name in daily_definition["States"] if "Gold" in name]
    assert gold_refresh_states == ["GoldRefresh"]


# -- ticket 06: bootstrap is explicitly untouched -----------------------------


def test_bootstrap_unaffected_by_daily_incremental_restructure(bootstrap_definition: dict) -> None:
    """Ticket 06 scoped the restructure to daily_incremental only -- bootstrap
    (recent-filings-only mode) keeps its original shape: SeedUniverse ->
    RunWarehouseTask, no Stage0CompanyIdentity, no ComputeWindows."""
    assert bootstrap_definition["StartAt"] == "SeedUniverse"
    assert "Stage0CompanyIdentity" not in bootstrap_definition["States"]
    assert "ComputeWindows" not in bootstrap_definition["States"]
    order = _linear_order(bootstrap_definition)
    assert order.index("SeedUniverse") < order.index("RunWarehouseTask")
