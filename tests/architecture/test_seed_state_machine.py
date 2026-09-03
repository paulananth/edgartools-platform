"""Structural checks on the generated single seed machine (write_seed_definition).

state-machine-consolidation wayfinder map, ticket 07: merges the former
standalone seed_universe (warehouse-level CIK/ticker discovery) +
mdm_seed_universe (MDM-level enrollment) machines, reversing ticket 04's
"keep both separate" call. These tests generate the real JSON by sourcing
the actual bash function and asserting on the output, mirroring
test_mdm_state_machine.py's own approach. Network-free: no AWS calls, only
local JSON generation via a python3 subprocess the deploy script itself
launches.
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

_START_MARKER = "write_seed_definition() {\n"
_END_MARKER = "\nPY\n}\n"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_START_MARKER)
    end = text.index(_END_MARKER, start) + len(_END_MARKER)
    return text[start:end]


def _generate() -> dict:
    fn_source = _extract_function_source()

    tmp_root = REPO_ROOT / ".pytest_cache" / "seed_sm_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "seed_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / "seed.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            "PUBLIC_SUBNET_IDS_JSON='[\"subnet-aaaa\",\"subnet-bbbb\"]'\n"
            "SECURITY_GROUP_IDS_JSON='[\"sg-cccc\"]'\n"
            'MDM_SEED_UNIVERSE_TRACKING_STATUS="bootstrap_pending"\n'
            f'SCRIPT_DIR="{(REPO_ROOT / "infra" / "scripts").as_posix()}"\n'
            f'source "{fn_file.as_posix()}"\n'
            f'write_seed_definition "{out_file.as_posix()}" "arn:wh-medium" "arn:mdm-small" "arn:mdm-machine"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"seed definition generation failed:\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seed_definition() -> dict:
    return _generate()


def _command_of(definition: dict, state_name: str) -> str:
    containers = definition["States"][state_name].get("Parameters", {}).get("Overrides", {}).get("ContainerOverrides", [])
    return containers[0]["Command.$"] if containers else ""


def test_generates_valid_json_with_no_dangling_references(seed_definition: dict) -> None:
    states = seed_definition["States"]
    assert seed_definition["StartAt"] in states
    for name, state in states.items():
        nxt = state.get("Next")
        if nxt is not None:
            assert nxt in states, f"{name}: Next={nxt!r} undefined"
        for choice in state.get("Choices", []):
            assert choice["Next"] in states, f"{name}: Choice Next={choice['Next']!r} undefined"
        default = state.get("Default")
        if default is not None:
            assert default in states, f"{name}: Default={default!r} undefined"


def test_starts_with_seed_universe(seed_definition: dict) -> None:
    assert seed_definition["StartAt"] == "SeedUniverse"
    command = _command_of(seed_definition, "SeedUniverse")
    assert "'seed-universe'" in command
    assert "'--run-id', $$.Execution.Name" in command
    assert seed_definition["States"]["SeedUniverse"]["Next"] == "HasLimitOverride"


def test_seed_universe_uses_the_warehouse_medium_profile(seed_definition: dict) -> None:
    assert seed_definition["States"]["SeedUniverse"]["Parameters"]["TaskDefinition"] == "arn:wh-medium"


def test_limit_override_choice_routes_correctly(seed_definition: dict) -> None:
    choice = seed_definition["States"]["HasLimitOverride"]
    assert choice["Type"] == "Choice"
    assert choice["Default"] == "MdmSeedUniverseDefault"
    assert choice["Choices"][0]["Next"] == "MdmSeedUniverseWithLimit"
    conditions = choice["Choices"][0]["And"]
    assert {"Variable": "$.limit", "IsPresent": True} in conditions
    assert {"Variable": "$.limit", "IsNumeric": True} in conditions


def test_mdm_seed_universe_default_uses_the_deploy_time_tracking_status(seed_definition: dict) -> None:
    command = _command_of(seed_definition, "MdmSeedUniverseDefault")
    assert "'mdm', 'seed-universe'" in command
    assert "'--tracking-status', 'bootstrap_pending'" in command
    assert "'--limit'" not in command
    assert seed_definition["States"]["MdmSeedUniverseDefault"]["Next"] == "RunMdmChain"


def test_mdm_seed_universe_with_limit_includes_the_override(seed_definition: dict) -> None:
    command = _command_of(seed_definition, "MdmSeedUniverseWithLimit")
    assert "'--tracking-status', 'bootstrap_pending'" in command
    assert "'--limit'" in command
    assert seed_definition["States"]["MdmSeedUniverseWithLimit"]["Next"] == "RunMdmChain"


def test_mdm_seed_universe_states_use_the_mdm_small_profile(seed_definition: dict) -> None:
    """Matches the predecessor standalone mdm_seed_universe machine's own
    profile (task_definition_for_mdm_workflow()'s mdm_seed_universe case),
    not load_history's inline mdm_medium_arn copy -- a separate, untouched
    call site with no shared history."""
    for state_name in ("MdmSeedUniverseDefault", "MdmSeedUniverseWithLimit"):
        assert seed_definition["States"][state_name]["Parameters"]["TaskDefinition"] == "arn:mdm-small"


def test_ends_by_calling_the_single_mdm_machine(seed_definition: dict) -> None:
    run_mdm_chain = seed_definition["States"]["RunMdmChain"]
    assert run_mdm_chain["Type"] == "Task"
    assert run_mdm_chain["Resource"] == "arn:aws:states:::states:startExecution.sync:2"
    assert run_mdm_chain["Parameters"]["StateMachineArn"] == "arn:mdm-machine"
    assert run_mdm_chain["Parameters"]["Input"]["run_id.$"] == "$$.Execution.Name"
    assert run_mdm_chain["End"] is True


def test_no_sec_fetch_active_lease_states(seed_definition: dict) -> None:
    """Matches the predecessor standalone seed_universe machine, which was
    deliberately never wrapped in the sec_fetch_active lease -- it doesn't
    call SEC at meaningful volume."""
    for name in seed_definition["States"]:
        assert "SecFetchLease" not in name
