"""Unit tests for infra/scripts/mdm_tail_helper.py's wire_mdm_tail().

state-machine-consolidation wayfinder map, ticket 02: the shared MDM Tail
Sequencing Skeleton. These test the ordering guarantee in isolation --
Export->Sync->Verify(->GoldRefresh) -- without any of the ASL/ECS plumbing
the real deploy script wraps around each state, since wire_mdm_tail is
deliberately blind to what's inside each state dict.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "infra" / "scripts"))

from mdm_tail_helper import wire_mdm_tail  # noqa: E402


def _task_state(**extra):
    return {
        "Type": "Task",
        "Resource": "arn:aws:states:::ecs:runTask.sync",
        "Parameters": {"TaskDefinition": "arn:fake"},
        **extra,
    }


def test_wires_export_sync_verify_in_order_with_gold_refresh():
    result = wire_mdm_tail(
        _task_state(), _task_state(), _task_state(),
        gold_state=_task_state(),
    )

    assert set(result) == {"MdmExport", "MdmSync", "MdmVerify", "GoldRefresh"}
    assert result["MdmExport"]["Next"] == "MdmSync"
    assert result["MdmSync"]["Next"] == "MdmVerify"
    assert result["MdmVerify"]["Next"] == "GoldRefresh"
    assert result["GoldRefresh"]["End"] is True
    assert "End" not in result["MdmExport"]
    assert "End" not in result["MdmSync"]
    assert "End" not in result["MdmVerify"]
    assert "Next" not in result["GoldRefresh"]


def test_wires_export_sync_verify_without_gold_refresh():
    result = wire_mdm_tail(_task_state(), _task_state(), _task_state())

    assert set(result) == {"MdmExport", "MdmSync", "MdmVerify"}
    assert result["MdmExport"]["Next"] == "MdmSync"
    assert result["MdmSync"]["Next"] == "MdmVerify"
    assert result["MdmVerify"]["End"] is True
    assert "Next" not in result["MdmVerify"]


def test_preserves_caller_supplied_flags_and_catch():
    export = _task_state(Parameters={"TaskDefinition": "arn:mdm-large"})
    sync = _task_state(Parameters={
        "TaskDefinition": "arn:mdm-large",
        "Overrides": {"ContainerOverrides": [{"Command.$": "States.Array('mdm', 'sync-graph', '--generation-id', $$.Execution.Name)"}]},
    })
    verify = _task_state(Catch=[{"ErrorEquals": ["States.ALL"], "Next": "GoldRefresh"}])

    result = wire_mdm_tail(export, sync, verify, gold_state=_task_state())

    # Flags/task-def/Catch pass through completely unchanged -- wire_mdm_tail
    # only ever touches Next/End.
    assert result["MdmSync"]["Parameters"]["TaskDefinition"] == "arn:mdm-large"
    assert "generation-id" in result["MdmSync"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert result["MdmVerify"]["Catch"] == [{"ErrorEquals": ["States.ALL"], "Next": "GoldRefresh"}]


def test_overwrites_pre_set_next_or_end_on_export_and_sync():
    # A caller might build export/sync states with a placeholder is_end=True
    # (this repo's own local ecs_state()/run_task_state() helpers require
    # either next_state or is_end) -- wire_mdm_tail must overwrite it, not
    # leave a state with both End and Next.
    export = _task_state(End=True)
    sync = _task_state(Next="SomethingElse")
    verify = _task_state(End=True)

    result = wire_mdm_tail(export, sync, verify, gold_state=_task_state())

    assert "End" not in result["MdmExport"]
    assert result["MdmExport"]["Next"] == "MdmSync"
    assert result["MdmSync"]["Next"] == "MdmVerify"


def test_does_not_mutate_input_dicts():
    export, sync, verify, gold = _task_state(), _task_state(), _task_state(), _task_state()
    wire_mdm_tail(export, sync, verify, gold_state=gold)

    assert "Next" not in export
    assert "Next" not in sync
    assert "Next" not in verify
    assert "End" not in gold


@pytest.mark.parametrize("gold_state", [None, {}])
def test_gold_refresh_only_appended_when_gold_state_is_not_none(gold_state):
    result = wire_mdm_tail(_task_state(), _task_state(), _task_state(), gold_state=gold_state)
    if gold_state is None:
        assert "GoldRefresh" not in result
    else:
        assert "GoldRefresh" in result
