"""Structural checks on the generated single MDM machine (write_mdm_definition).

state-machine-consolidation wayfinder map, ticket 07: the MDM machine every
caller (daily_incremental, load_history, the seed machine) invokes as a
nested execution instead of hand-duplicating Mastering..Reconcile. These
tests generate the real JSON by sourcing the actual bash function (no
duplicated/hand-maintained copy of the state machine shape) and asserting
on the output, mirroring test_daily_incremental_state_machine.py's/
test_load_history_state_machine.py's own approach. Network-free: no AWS
calls, only local JSON generation via a python3 subprocess the deploy
script itself launches.
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

_START_MARKER = "write_mdm_definition() {\n"
_END_MARKER = "\nPY\n}\n"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_START_MARKER)
    end = text.index(_END_MARKER, start) + len(_END_MARKER)
    return text[start:end]


def _generate() -> dict:
    fn_source = _extract_function_source()

    tmp_root = REPO_ROOT / ".pytest_cache" / "mdm_sm_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "mdm_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / "mdm.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            "PUBLIC_SUBNET_IDS_JSON='[\"subnet-aaaa\",\"subnet-bbbb\"]'\n"
            "SECURITY_GROUP_IDS_JSON='[\"sg-cccc\"]'\n"
            "MDM_RUN_LIMIT=100\n"
            "MDM_GRAPH_LIMIT=200\n"
            f'source "{fn_file.as_posix()}"\n'
            f'write_mdm_definition "{out_file.as_posix()}" "arn:mdm-small" "arn:mdm-medium" "arn:wh-medium"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"mdm definition generation failed:\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mdm_definition() -> dict:
    return _generate()


def _command_of(definition: dict, state_name: str) -> str:
    containers = definition["States"][state_name].get("Parameters", {}).get("Overrides", {}).get("ContainerOverrides", [])
    return containers[0]["Command.$"] if containers else ""


def _linear_order(definition: dict) -> list[str]:
    states = definition["States"]
    order: list[str] = []
    seen: set[str] = set()
    name = definition["StartAt"]
    while name and name not in seen:
        seen.add(name)
        order.append(name)
        name = states[name].get("Next")
    return order


def test_generates_valid_json_with_no_dangling_references(mdm_definition: dict) -> None:
    states = mdm_definition["States"]
    assert mdm_definition["StartAt"] in states
    for name, state in states.items():
        nxt = state.get("Next")
        if nxt is not None:
            assert nxt in states, f"{name}: Next={nxt!r} undefined"
        for catch in state.get("Catch", []):
            cnxt = catch.get("Next")
            if cnxt is not None:
                assert cnxt in states, f"{name}: Catch Next={cnxt!r} undefined"


def test_tail_order_is_mastering_through_reconcile(mdm_definition: dict) -> None:
    assert _linear_order(mdm_definition) == [
        "Mastering",
        "BackpropagateIdsToSilver",
        "Infer Relationships",
        "Publish",
        "Publish Relationships",
        "Reconcile",
    ]


def test_ends_at_reconcile_gold_refresh_is_not_part_of_this_machine(mdm_definition: dict) -> None:
    assert "GoldRefresh" not in mdm_definition["States"]
    assert "FactPublishtoGold" not in mdm_definition["States"]
    assert mdm_definition["States"]["Reconcile"]["End"] is True


def test_mastering_uses_entity_type_all(mdm_definition: dict) -> None:
    """No dedicated --entity-type company MDM call: the existing
    --entity-type all call already resolves companies as part of its sweep
    (run_all() calls run_companies())."""
    command = _command_of(mdm_definition, "Mastering")
    assert "'--entity-type', 'all'" in command


def test_mastering_and_infer_relationships_bind_run_id_not_execution_name(mdm_definition: dict) -> None:
    # MDM Run Identity (CONTEXT.md; Ticket 30, e45bcd30): every
    # commit-evidence-producing command must bind one shared identity per
    # logical run. Inside this nested execution, $$.Execution.Name would
    # resolve to ITS OWN auto-generated name, not the calling machine's --
    # every evidence-producing command here must use $.run_id instead.
    for state_name in ("Mastering", "Infer Relationships"):
        command = _command_of(mdm_definition, state_name)
        assert "'--run-id', $.run_id" in command, f"{state_name}: {command}"
        assert "$$.Execution.Name" not in command, f"{state_name}: {command}"


def test_backpropagate_ids_to_silver_uses_backfill_mdm_entity_ids_command(mdm_definition: dict) -> None:
    command = _command_of(mdm_definition, "BackpropagateIdsToSilver")
    assert "'backfill-mdm-entity-ids'" in command
    assert "'--run-id', $.run_id" in command


def test_backpropagate_ids_to_silver_failure_is_non_fatal(mdm_definition: dict) -> None:
    state = mdm_definition["States"]["BackpropagateIdsToSilver"]
    assert state["Catch"] == [{
        "ErrorEquals": ["States.ALL"],
        "ResultPath": None,
        "Next": "Infer Relationships",
    }]


def test_reconcile_failure_is_non_fatal_and_falls_through_to_a_terminal_state(mdm_definition: dict) -> None:
    reconcile = mdm_definition["States"]["Reconcile"]
    assert reconcile["Catch"] == [{
        "ErrorEquals": ["States.ALL"],
        "ResultPath": None,
        "Next": "ReconcileFailedNonFatal",
    }]
    terminal = mdm_definition["States"]["ReconcileFailedNonFatal"]
    assert terminal["Type"] == "Pass"
    assert terminal["End"] is True


def test_reconcile_uses_the_small_task_profile(mdm_definition: dict) -> None:
    assert mdm_definition["States"]["Reconcile"]["Parameters"]["TaskDefinition"] == "arn:mdm-small"


def test_every_other_mdm_state_uses_the_medium_task_profile(mdm_definition: dict) -> None:
    for name in ("Mastering", "Infer Relationships", "Publish", "Publish Relationships"):
        assert mdm_definition["States"][name]["Parameters"]["TaskDefinition"] == "arn:mdm-medium", name


def test_backpropagate_ids_to_silver_uses_the_warehouse_medium_profile(mdm_definition: dict) -> None:
    state = mdm_definition["States"]["BackpropagateIdsToSilver"]
    assert state["Parameters"]["TaskDefinition"] == "arn:wh-medium"


def test_publish_precedes_publish_relationships(mdm_definition: dict) -> None:
    # data-architecture Issue 3: publish-relationships materializes
    # Snowflake graph tables from the Snowflake MDM mirror -- without a
    # publish first, the mirror can be stale relative to this run.
    order = _linear_order(mdm_definition)
    assert order.index("Publish") < order.index("Publish Relationships")


def test_every_task_state_preserves_input_via_result_path_none(mdm_definition: dict) -> None:
    # Confirmed live 2026-09-03/04: an ecs:runTask.sync Task state's default
    # ResultPath ($) replaces the ENTIRE state input with its own ECS
    # task-description result. Since Mastering/BackpropagateIdsToSilver/
    # Infer Relationships all read $.run_id (see the run-id test above),
    # any state in this chain missing ResultPath=None destroys $.run_id for
    # every state after it -- and the resulting error is an uncatchable
    # States.Runtime (Catch: States.ALL does not intercept it), so it
    # silently exhausts this chain's own Retry and fails the whole
    # execution. A real daily_incremental execution hit exactly this at
    # BackpropagateIdsToSilver before this test existed.
    for name, state in mdm_definition["States"].items():
        if state.get("Type") != "Task":
            continue
        assert "ResultPath" in state and state["ResultPath"] is None, (
            f"{name}: ResultPath must be explicitly null (found "
            f"{state.get('ResultPath', '<key absent, defaults to $>')!r}) "
            f"-- an absent ResultPath replaces the whole state input with "
            f"this task's own ECS result, destroying $.run_id"
        )
