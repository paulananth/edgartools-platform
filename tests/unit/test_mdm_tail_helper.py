"""Unit tests for infra/scripts/mdm_tail_helper.py's wire_mdm_tail() and
call_mdm_machine().

state-machine-consolidation wayfinder map, ticket 02 (wire_mdm_tail) and
ticket 07 (call_mdm_machine): wire_mdm_tail tests the ordering guarantee in
isolation -- Export->Sync->Verify(->GoldRefresh) -- without any of the
ASL/ECS plumbing the real deploy script wraps around each state, since
wire_mdm_tail is deliberately blind to what's inside each state dict.
call_mdm_machine tests the nested-execution Task shape, in particular the
$$.Execution.Name -> run_id input handoff ticket 07's own MDM Run Identity
finding depends on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "infra" / "scripts"))

from mdm_tail_helper import call_mdm_machine, wire_mdm_tail  # noqa: E402


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

    assert set(result) == {"Publish", "Publish Relationships", "Reconcile", "GoldRefresh"}
    assert result["Publish"]["Next"] == "Publish Relationships"
    assert result["Publish Relationships"]["Next"] == "Reconcile"
    assert result["Reconcile"]["Next"] == "GoldRefresh"
    assert result["GoldRefresh"]["End"] is True
    assert "End" not in result["Publish"]
    assert "End" not in result["Publish Relationships"]
    assert "End" not in result["Reconcile"]
    assert "Next" not in result["GoldRefresh"]


def test_wires_export_sync_verify_without_gold_refresh():
    result = wire_mdm_tail(_task_state(), _task_state(), _task_state())

    assert set(result) == {"Publish", "Publish Relationships", "Reconcile"}
    assert result["Publish"]["Next"] == "Publish Relationships"
    assert result["Publish Relationships"]["Next"] == "Reconcile"
    assert result["Reconcile"]["End"] is True
    assert "Next" not in result["Reconcile"]


def test_preserves_caller_supplied_flags_and_catch():
    export = _task_state(Parameters={"TaskDefinition": "arn:mdm-large"})
    sync = _task_state(Parameters={
        "TaskDefinition": "arn:mdm-large",
        "Overrides": {"ContainerOverrides": [{"Command.$": "States.Array('mdm', 'publish-relationships', '--generation-id', $$.Execution.Name)"}]},
    })
    verify = _task_state(Catch=[{"ErrorEquals": ["States.ALL"], "Next": "GoldRefresh"}])

    result = wire_mdm_tail(export, sync, verify, gold_state=_task_state())

    # Flags/task-def/Catch pass through completely unchanged -- wire_mdm_tail
    # only ever touches Next/End.
    assert result["Publish Relationships"]["Parameters"]["TaskDefinition"] == "arn:mdm-large"
    assert "generation-id" in result["Publish Relationships"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert result["Reconcile"]["Catch"] == [{"ErrorEquals": ["States.ALL"], "Next": "GoldRefresh"}]


def test_overwrites_pre_set_next_or_end_on_export_and_sync():
    # A caller might build export/sync states with a placeholder is_end=True
    # (this repo's own local ecs_state()/run_task_state() helpers require
    # either next_state or is_end) -- wire_mdm_tail must overwrite it, not
    # leave a state with both End and Next.
    export = _task_state(End=True)
    sync = _task_state(Next="SomethingElse")
    verify = _task_state(End=True)

    result = wire_mdm_tail(export, sync, verify, gold_state=_task_state())

    assert "End" not in result["Publish"]
    assert result["Publish"]["Next"] == "Publish Relationships"
    assert result["Publish Relationships"]["Next"] == "Reconcile"


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


class TestCallMdmMachine:
    def test_starts_a_synchronous_nested_execution_of_the_given_machine(self):
        result = call_mdm_machine("arn:aws:states:us-east-1:1:stateMachine:mdm", next_state="FactPublishtoGold")

        assert result["Type"] == "Task"
        assert result["Resource"] == "arn:aws:states:::states:startExecution.sync:2"
        assert result["Parameters"]["StateMachineArn"] == "arn:aws:states:us-east-1:1:stateMachine:mdm"
        assert result["Next"] == "FactPublishtoGold"
        assert "End" not in result

    def test_propagates_the_calling_executions_own_name_as_run_id(self):
        # The one thing this function exists to guarantee: $$.Execution.Name
        # (the CALLING machine's own execution name) is threaded into the
        # nested execution's input as run_id -- inside the nested execution,
        # $$.Execution.Name would resolve to ITS OWN auto-generated name
        # instead, silently fragmenting one logical run's MDM Run Identity.
        result = call_mdm_machine("arn:fake", is_end=True)

        assert result["Parameters"]["Input"]["run_id.$"] == "$$.Execution.Name"

    def test_is_end_true_sets_end_not_next(self):
        result = call_mdm_machine("arn:fake", is_end=True)

        assert result["End"] is True
        assert "Next" not in result

    def test_requires_either_next_state_or_is_end(self):
        with pytest.raises(ValueError):
            call_mdm_machine("arn:fake")

    def test_has_a_retry_policy(self):
        result = call_mdm_machine("arn:fake", is_end=True, retry_secs=60)

        assert result["Retry"] == [{
            "ErrorEquals": ["States.TaskFailed"],
            "IntervalSeconds": 60,
            "BackoffRate": 2.0,
            "MaxAttempts": 2,
        }]
