"""Structural checks on the generated mdm_utility Step Functions definition.

state-machine-consolidation wayfinder map, ticket 02 (re-grilled 2026-08-10):
collapses the genuinely-uniform single-command MDM CLI wrappers into one
deployed machine, selected via execution input {"mode": "<workflow>"}.
generation_build and mdm_seed_universe are deliberately excluded -- see
CONTEXT.md's "MDM Utility Machine" / "Graph Generation Build Machine"
entries and .scratch/state-machine-consolidation/issues/
02-decide-consolidation-mechanism-for-shared-mdm-tail.md. mdm_check_fence
(Ticket 44, change-propagation map) joined the set later, reusing this same
consolidated machine instead of a bespoke new one -- see that ticket's
Answer.

Generates the real JSON by sourcing the actual bash functions (no
duplicated/hand-maintained copy of the state machine shape), mirroring
test_load_history_state_machine.py's approach. Network-free: no AWS calls,
only local JSON generation via python3 subprocesses the deploy script
itself launches.
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

_START_MARKER = "task_definition_for_mdm_workflow() {\n"
_END_MARKER = "\n# state-machine-consolidation wayfinder map, ticket 03:"

_EXPECTED_MODES = {
    "mdm_migrate",
    "mdm_check_connectivity",
    "mdm_run",
    "mdm_backfill_relationships",
    "mdm_sync_graph",
    "mdm_verify_graph",
    "mdm_counts",
    "mdm_check_fence",
    "mdm_publication_drain",
}

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_START_MARKER)
    end = text.index(_END_MARKER, start)
    return text[start:end]


@pytest.fixture(scope="module")
def definition() -> dict:
    fn_source = _extract_function_source()
    root = REPO_ROOT / ".pytest_cache" / "mdm_utility_state_machine_test"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "mdm_utility_fns.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / "mdm_utility.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            "PUBLIC_SUBNET_IDS_JSON='[\"subnet-aaaa\",\"subnet-bbbb\"]'\n"
            "SECURITY_GROUP_IDS_JSON='[\"sg-cccc\"]'\n"
            'TASK_DEF_MDM_SMALL_ARN="arn:mdm-small"\n'
            'TASK_DEF_MDM_MEDIUM_ARN="arn:mdm-medium"\n'
            "MDM_RUN_LIMIT=0\n"
            "MDM_GRAPH_LIMIT=0\n"
            'MDM_SEED_UNIVERSE_TRACKING_STATUS="bootstrap_pending"\n'
            f'source "{fn_file.as_posix()}"\n'
            f'write_mdm_utility_definition "{out_file.as_posix()}"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30, check=False
        )
        if result.returncode != 0:
            raise AssertionError(
                f"mdm_utility definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


def test_start_at_is_select_mode(definition: dict) -> None:
    assert definition["StartAt"] == "SelectMode"
    assert definition["States"]["SelectMode"]["Type"] == "Choice"


def test_select_mode_routes_every_expected_workflow(definition: dict) -> None:
    choices = definition["States"]["SelectMode"]["Choices"]
    routed_modes = {c["StringEquals"] for c in choices}
    assert routed_modes == _EXPECTED_MODES
    for choice in choices:
        assert choice["Variable"] == "$.mode"
        assert choice["Next"] in definition["States"]


def test_select_mode_has_unknown_mode_fail_default(definition: dict) -> None:
    assert definition["States"]["SelectMode"]["Default"] == "UnknownMode"
    unknown = definition["States"]["UnknownMode"]
    assert unknown["Type"] == "Fail"


def test_generation_build_and_mdm_seed_universe_are_not_included(definition: dict) -> None:
    # Scope correction (ticket 02 re-grilling): generation_build is a bespoke
    # partition-fan-out pipeline, not a single-command wrapper; mdm_seed_universe
    # is kept as its own standalone machine (ticket 04). Neither belongs here.
    choices = definition["States"]["SelectMode"]["Choices"]
    routed_modes = {c["StringEquals"] for c in choices}
    assert "generation_build" not in routed_modes
    assert "mdm_seed_universe" not in routed_modes
    assert not any(name.startswith("generation_build_") for name in definition["States"])
    assert not any(name.startswith("mdm_seed_universe_") for name in definition["States"])


def test_no_state_name_collisions_across_workflows(definition: dict) -> None:
    # Every workflow's states are namespaced under f"{name}_" -- if two
    # workflows' builders ever produced the same raw state name, this test
    # would have caught it via len() mismatch (a dict silently overwrites).
    state_names = list(definition["States"])
    assert len(state_names) == len(set(state_names))
    for mode in _EXPECTED_MODES:
        assert any(name.startswith(f"{mode}_") for name in state_names), (
            f"expected at least one state prefixed '{mode}_'"
        )


def test_relationship_and_limit_override_chain_preserved_for_backfill_relationships(
    definition: dict,
) -> None:
    # mdm_backfill_relationships supports relationship_type + limit overrides
    # (mirrors write_mdm_workflow_definition's own branching) -- confirm the
    # full 4-way chain survived the consolidation, not just the default path.
    states = definition["States"]
    assert "mdm_backfill_relationships_HasRelationshipTypeAndLimitOverride" in states
    assert "mdm_backfill_relationships_RunMdmTaskWithRelationshipTypeAndLimit" in states
    entry = states["mdm_backfill_relationships_HasRelationshipTypeAndLimitOverride"]
    assert entry["Type"] == "Choice"


def test_limit_per_type_override_preserved_for_sync_graph_only(definition: dict) -> None:
    # Release-readiness ticket 94: only mdm_sync_graph supports --limit-per-type.
    states = definition["States"]
    assert "mdm_sync_graph_HasLimitPerTypeOverride" in states
    assert states["mdm_sync_graph_HasLimitPerTypeOverride"]["Type"] == "Choice"

    sync_graph_start = next(
        c["Next"] for c in definition["States"]["SelectMode"]["Choices"]
        if c["StringEquals"] == "mdm_sync_graph"
    )
    assert sync_graph_start == "mdm_sync_graph_HasLimitPerTypeOverride"

    # No other workflow gets a limit-per-type wrap.
    for mode in _EXPECTED_MODES - {"mdm_sync_graph"}:
        assert f"{mode}_HasLimitPerTypeOverride" not in states


def test_sync_graph_zero_limit_routes_to_unbounded_command(definition: dict) -> None:
    """Ticket 28: the operator's limit=0 contract must omit --limit at the CLI."""
    states = definition["States"]
    choice = states["mdm_sync_graph_HasUnboundedLimitOverride"]
    assert choice["Type"] == "Choice"
    assert choice["Choices"][0]["Next"] == (
        "mdm_sync_graph_RunMdmTaskUnboundedWithRelationshipType"
    )
    assert choice["Choices"][0]["And"] == [
        {"Variable": "$.limit", "IsPresent": True},
        {"Variable": "$.limit", "IsNumeric": True},
        {"Variable": "$.limit", "NumericEquals": 0},
        {"Variable": "$.relationship_type", "IsPresent": True},
        {"Variable": "$.relationship_type", "IsString": True},
    ]
    assert choice["Choices"][1] == {
        "And": [
            {"Variable": "$.limit", "IsPresent": True},
            {"Variable": "$.limit", "IsNumeric": True},
            {"Variable": "$.limit", "NumericEquals": 0},
        ],
        "Next": "mdm_sync_graph_RunMdmTaskUnbounded",
    }
    task = states["mdm_sync_graph_RunMdmTaskUnbounded"]
    command = task["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert command == "States.Array('mdm', 'publish-relationships')"
    filtered_task = states["mdm_sync_graph_RunMdmTaskUnboundedWithRelationshipType"]
    filtered_command = filtered_task["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert filtered_command == (
        "States.Array('mdm', 'publish-relationships', '--relationship-type', $.relationship_type)"
    )

    # limit_per_type remains the outermost, higher-specificity override.
    assert states["mdm_sync_graph_HasLimitPerTypeOverride"]["Default"] == (
        "mdm_sync_graph_HasUnboundedLimitOverride"
    )


def test_no_override_workflows_route_straight_to_a_single_task_state(definition: dict) -> None:
    # mdm_migrate/mdm_check_connectivity/mdm_counts have no limit or
    # relationship overrides at all -- their mode should route directly to
    # one Task state, no Choice wrapping.
    for mode in ("mdm_migrate", "mdm_check_connectivity", "mdm_counts", "mdm_check_fence", "mdm_publication_drain"):
        start = next(
            c["Next"] for c in definition["States"]["SelectMode"]["Choices"]
            if c["StringEquals"] == mode
        )
        assert start == f"{mode}_RunMdmTask"
        assert definition["States"][start]["Type"] == "Task"
        assert definition["States"][start]["End"] is True
