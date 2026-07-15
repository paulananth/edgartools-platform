"""Structural checks on the generated generation_build Step Functions definition.

Covers 07-04 Task 2 (RSYNC-04): AWS fan-out/fan-in orchestration for the
parallel immutable graph generation builder. Terraform stays passive -- these
tests only assert on the JSON emitted by
`write_generation_build_definition` in infra/scripts/deploy-aws-application.sh
and confirm passive Terraform gained no new runnable workload for it.

Network-free: no AWS calls, only local JSON generation via python3
subprocesses the deploy script itself launches (same technique as
tests/architecture/test_load_history_state_machine.py).
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

_START_MARKER = "write_generation_build_definition() {\n"
_END_MARKER = "\nPY\n}\n"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_START_MARKER)
    end = text.index(_END_MARKER, start) + len(_END_MARKER)
    return text[start:end]


@pytest.fixture(scope="module")
def definition() -> dict:
    """Generate generation_build's Step Functions JSON with dummy ARNs (no AWS calls)."""
    fn_source = _extract_function_source()

    tmp_root = REPO_ROOT / ".pytest_cache" / "generation_build_sm_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "generation_build_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / "generation_build.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'BRONZE_BUCKET_NAME="fake-bronze-bucket"\n'
            "PUBLIC_SUBNET_IDS_JSON='[\"subnet-aaaa\",\"subnet-bbbb\"]'\n"
            "SECURITY_GROUP_IDS_JSON='[\"sg-cccc\"]'\n"
            "MDM_GRAPH_RULE_VERSION=\"v1\"\n"
            "MDM_GRAPH_SCHEMA_VERSION=\"v1\"\n"
            "MDM_GENERATION_PARTITION_CONCURRENCY=8\n"
            f'source "{fn_file.as_posix()}"\n'
            f'write_generation_build_definition "{out_file.as_posix()}" '
            '"arn:mdm-small" "arn:mdm-medium"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"generation_build definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


def _command_of(definition: dict, state_name: str) -> str:
    state = definition["States"][state_name]
    return _command_of_state(state)


def _command_of_state(state: dict) -> str:
    if state.get("Type") == "Map":
        proc_states = state["ItemProcessor"]["States"]
        return " ".join(_command_of_state(s) for s in proc_states.values())
    containers = state.get("Parameters", {}).get("Overrides", {}).get("ContainerOverrides", [])
    return containers[0]["Command.$"] if containers else ""


def _linear_order(definition: dict) -> list[str]:
    states = definition["States"]

    def next_of(state: dict) -> str | None:
        if "Next" in state:
            return state["Next"]
        if state.get("Type") == "Choice":
            return state.get("Default") or state["Choices"][0]["Next"]
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


def test_generates_valid_json_with_no_dangling_references(definition: dict) -> None:
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
            if state.get("Type") == "Parallel":
                for i, branch in enumerate(state["Branches"]):
                    check(branch["States"], branch["StartAt"], f"{label}.{name}(Parallel[{i}])")

    check(definition["States"], definition["StartAt"], "top")


# -- fan-out: Distributed Map with bounded concurrency ------------------------


def test_build_partitions_is_a_distributed_map_with_bounded_concurrency(definition: dict) -> None:
    state = definition["States"]["BuildPartitions"]
    assert state["Type"] == "Map"
    assert state["ItemProcessor"]["ProcessorConfig"]["Mode"] == "DISTRIBUTED"
    assert state["ItemProcessor"]["ProcessorConfig"]["ExecutionType"] == "STANDARD"
    assert isinstance(state["MaxConcurrency"], int)
    assert 1 <= state["MaxConcurrency"] <= 100


def test_build_partitions_reads_partitions_manifest_from_s3(definition: dict) -> None:
    state = definition["States"]["BuildPartitions"]
    reader = state["ItemReader"]
    assert reader["Resource"] == "arn:aws:states:::s3:getObject"
    assert "partitions.jsonl" in reader["Parameters"]["Key.$"]


def test_per_partition_command_only_needs_partition_id(definition: dict) -> None:
    cmd = _command_of(definition, "BuildPartitions")
    assert "'generation-build-partition'" in cmd
    assert "'--partition-id', $.partition_id" in cmd


def test_partition_worker_has_retry_configured(definition: dict) -> None:
    per_partition_state = definition["States"]["BuildPartitions"]["ItemProcessor"]["States"]["BuildPartition"]
    retries = per_partition_state.get("Retry")
    assert retries, "expected a Retry block on the per-partition worker task"
    assert retries[0]["MaxAttempts"] >= 1


# -- fan-in: activation is gated on verification, never on the raw Map -------


def test_activation_is_only_reachable_via_fan_in_success(definition: dict) -> None:
    order = _linear_order(definition)
    assert "FanIn" in order
    assert "Activate" in order
    assert order.index("FanIn") < order.index("Activate")

    fan_in = definition["States"]["FanIn"]
    assert fan_in.get("Next") == "Activate"

    # No other state may transition directly into Activate.
    for name, state in definition["States"].items():
        if name in ("FanIn", "Activate"):
            continue
        assert state.get("Next") != "Activate", f"{name} must not bypass FanIn to reach Activate"
        for catch in state.get("Catch", []):
            assert catch.get("Next") != "Activate", f"{name}'s Catch must not bypass FanIn to reach Activate"


def test_fan_in_failure_routes_to_retry_never_to_activate(definition: dict) -> None:
    fan_in = definition["States"]["FanIn"]
    catches = fan_in.get("Catch") or []
    assert catches, "FanIn must Catch failures rather than let them abort the execution"
    for catch in catches:
        assert catch["Next"] == "RetryFailedPartitions"
        assert catch["Next"] != "Activate"


def test_retry_failed_partitions_command_shape(definition: dict) -> None:
    cmd = _command_of(definition, "RetryFailedPartitions")
    assert "'generation-retry-failed-partitions'" in cmd


def test_activate_command_shape(definition: dict) -> None:
    cmd = _command_of(definition, "Activate")
    assert "'generation-activate'" in cmd


def test_worker_failure_within_the_map_does_not_abort_the_whole_generation(definition: dict) -> None:
    """BuildPartitions must tolerate individual partition failures (ToleratedFailurePercentage)
    so FanIn -- not the Map -- is the single authority that decides pass/fail."""
    state = definition["States"]["BuildPartitions"]
    assert state.get("ToleratedFailurePercentage") == 100
    assert state["Next"] == "FanIn"


# -- generation-plan command shape --------------------------------------------


def test_generation_plan_command_shape(definition: dict) -> None:
    cmd = _command_of(definition, "GenerationPlan")
    assert "'generation-plan'" in cmd
    assert "'--run-id', $$.Execution.Name" in cmd
    assert "'--rule-version', $.rule_version" in cmd
    assert "'--schema-version', $.schema_version" in cmd


def test_rule_and_schema_version_defaults_are_backward_compatible(definition: dict) -> None:
    """{} must be a valid trigger input, same D-15 contract as load_history."""
    order = _linear_order(definition)
    assert order[0] == "RuleVersionCheck"
    assert "RuleVersionDefault" in definition["States"]
    assert "SchemaVersionDefault" in definition["States"]
    assert definition["States"]["RuleVersionDefault"]["Result"] == "v1"
    assert definition["States"]["SchemaVersionDefault"]["Result"] == "v1"


# -- passive Terraform: no new runnable workload ------------------------------


def test_passive_terraform_gained_no_new_task_definitions_or_state_machines() -> None:
    """RSYNC-04's Task 2 action is explicit: do not add task definitions, state
    machines, commands, schedules, or image rollout to passive Terraform. All
    of the generation_build orchestration lives in this deploy script instead."""
    terraform_root = REPO_ROOT / "infra" / "terraform" / "accounts"
    if not terraform_root.exists():
        pytest.skip("passive Terraform accounts directory not present in this checkout")
    for tf_file in terraform_root.rglob("*.tf"):
        text = tf_file.read_text(encoding="utf-8", errors="ignore")
        assert "generation_build" not in text, (
            f"{tf_file} references generation_build -- Task 2 must stay Terraform-passive"
        )
        assert "generation-plan" not in text
        assert "mdm_graph_generation" not in text
