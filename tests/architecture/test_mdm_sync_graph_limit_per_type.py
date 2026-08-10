"""Structural checks on the generated mdm_sync_graph Step Functions definition.

Release-readiness ticket 94: `mdm sync-graph`'s CLI supports `--limit-per-type`,
but the state machine's ASL only ever wired `$.limit` into the ECS command
override -- an execution input of {"limit_per_type": N} was silently ignored,
falling through to the bare default command (which itself resolves to a small
~200-edge cap deep in snowflake_graph.py, confirmed live). The only way to run
a real full sync was bypassing Step Functions entirely with a raw
`aws ecs run-task` call.

These tests generate the real JSON by sourcing the actual bash functions (no
duplicated/hand-maintained copy of the state machine shape), mirroring
test_load_history_state_machine.py's approach. Network-free: no AWS calls,
only local JSON generation via python3 subprocesses the deploy script itself
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

_START_MARKER = "mdm_workflow_command_expression() {\n"
_END_MARKER = "\nwrite_load_history_definition() {"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_START_MARKER)
    end = text.index(_END_MARKER, start)
    return text[start:end]


def _generate(workflow: str, tmp_root: Path) -> dict:
    fn_source = _extract_function_source()
    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "mdm_workflow_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / f"{workflow}.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            "PUBLIC_SUBNET_IDS_JSON='[\"subnet-aaaa\",\"subnet-bbbb\"]'\n"
            "SECURITY_GROUP_IDS_JSON='[\"sg-cccc\"]'\n"
            "MDM_RUN_LIMIT=0\n"
            "MDM_GRAPH_LIMIT=0\n"
            'MDM_SEED_UNIVERSE_TRACKING_STATUS="bootstrap_pending"\n'
            'MDM_SEED_FROM_SILVER_TRACKING_STATUS="bootstrap_pending"\n'
            f'source "{fn_file.as_posix()}"\n'
            f'command_expression="$(mdm_workflow_command_expression "{workflow}")"\n'
            f'limit_command_expression="$(mdm_workflow_limit_command_expression "{workflow}")"\n'
            f'relationship_command_expression="$(mdm_workflow_relationship_command_expression "{workflow}")"\n'
            f'relationship_limit_command_expression="$(mdm_workflow_relationship_limit_command_expression "{workflow}")"\n'
            f'limit_per_type_command_expression="$(mdm_workflow_limit_per_type_command_expression "{workflow}")"\n'
            f'write_mdm_workflow_definition "{out_file.as_posix()}" "arn:mdm-medium" '
            '"$command_expression" "$limit_command_expression" '
            '"$relationship_command_expression" "$relationship_limit_command_expression" '
            '"$limit_per_type_command_expression"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"{workflow} definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


def _command_of(definition: dict, state_name: str) -> str:
    containers = definition["States"][state_name]["Parameters"]["Overrides"]["ContainerOverrides"]
    return containers[0]["Command.$"]


@pytest.fixture(scope="module")
def tmp_root() -> Path:
    root = REPO_ROOT / ".pytest_cache" / "mdm_sync_graph_limit_per_type_test"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_sync_graph_wires_limit_per_type_as_new_entrypoint(tmp_root: Path) -> None:
    definition = _generate("mdm_sync_graph", tmp_root)

    assert definition["StartAt"] == "HasLimitPerTypeOverride"
    choice = definition["States"]["HasLimitPerTypeOverride"]
    assert choice["Type"] == "Choice"
    conditions = {c["Variable"] for c in choice["Choices"][0]["And"]}
    assert conditions == {"$.limit_per_type"}
    assert choice["Choices"][0]["Next"] == "RunMdmTaskWithLimitPerType"

    command = _command_of(definition, "RunMdmTaskWithLimitPerType")
    assert "'--limit-per-type'" in command
    assert "$.limit_per_type" in command
    assert "sync-graph" in command


def test_sync_graph_falls_through_to_original_chain_when_limit_per_type_absent(
    tmp_root: Path,
) -> None:
    definition = _generate("mdm_sync_graph", tmp_root)

    # Default must point at whatever the pre-existing chain's StartAt was --
    # this is the exact behavior this fix must not disturb (relationship_type
    # + limit combos, limit-only, and the bare default command).
    default_next = definition["States"]["HasLimitPerTypeOverride"]["Default"]
    assert default_next == "HasRelationshipTypeAndLimitOverride"
    assert "HasRelationshipTypeAndLimitOverride" in definition["States"]
    assert "RunMdmTaskDefault" in definition["States"]
    assert "RunMdmTaskWithRelationshipTypeAndLimit" in definition["States"]


def test_workflow_without_limit_per_type_support_is_unaffected(tmp_root: Path) -> None:
    # mdm_run has no --limit-per-type CLI flag; the helper returns empty for
    # it, so no HasLimitPerTypeOverride wrapping should appear at all.
    definition = _generate("mdm_run", tmp_root)

    assert "HasLimitPerTypeOverride" not in definition["States"]
    assert "RunMdmTaskWithLimitPerType" not in definition["States"]
    assert definition["StartAt"] == "HasLimitOverride"
