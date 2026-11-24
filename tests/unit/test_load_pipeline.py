"""The load pipeline: the state machine runs readiness then the given steps one at a time; the worker runs each task."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "skills" / "data-operations" / "scripts"))
import activity_worker  # noqa: E402

MACHINE = REPO / "infra" / "load-pipeline" / "state-machine.asl.json"


class TimedOut(Exception):
    pass


class Client:
    """Step Functions as the worker sees it: hands out the queued tasks and records each report."""

    class exceptions:
        TaskTimedOut = TimedOut

    def __init__(self, inputs, give_up_after=None):
        self.queue = [{}] + [{"taskToken": f"t{i}", "input": json.dumps(x)} for i, x in enumerate(inputs)]
        self.reports, self.beats, self.give_up_after = [], 0, give_up_after

    def get_activity_task(self, activityArn, workerName):
        return self.queue.pop(0)

    def send_task_heartbeat(self, taskToken):
        self.beats += 1
        if self.give_up_after is not None and self.beats > self.give_up_after:
            raise TimedOut()

    def send_task_success(self, taskToken, output):
        self.reports.append(("success", taskToken, json.loads(output)))

    def send_task_failure(self, taskToken, error, cause):
        self.reports.append(("failure", taskToken, error))


class Process:
    """A command that runs for `waits` heartbeats, then exits with `code`."""

    def __init__(self, code, waits=0):
        self.code, self.waits, self.terminated = code, waits, False

    def wait(self, timeout=None):
        if self.terminated:
            return -15
        if self.waits and timeout is not None:
            self.waits -= 1
            raise subprocess.TimeoutExpired("x", timeout)
        return self.code

    def terminate(self):
        self.terminated = True


def test_the_worker_runs_readiness_then_a_step_and_reports_each_end():
    started = []
    codes = iter([Process(0, waits=2), Process(2)])

    def start(argv):
        started.append([Path(a).name if a.endswith(".py") else a for a in argv[1:]])
        return next(codes)
    client = Client([{"action": "readiness"}, {"action": "step", "step": "company", "plan": True}])
    activity_worker.work(client, "arn", start, tasks=2)
    assert started == [["readiness.py"], ["load_chain.py", "--only", "company", "--plan"]]
    assert client.beats == 2
    assert client.reports == [("success", "t0", {"exit": 0, "action": "readiness"}), ("failure", "t1", "Exit2")]


@pytest.mark.parametrize("task", [{}, {"action": "step"}, {"action": "step", "step": ""}, {"action": "load", "step": "x"}])
def test_a_task_of_another_shape_is_refused_and_runs_nothing(task):
    client = Client([task])
    activity_worker.work(client, "arn", lambda argv: pytest.fail("a refused task runs nothing"), tasks=1)
    assert client.reports == [("failure", "t0", "BadInput")]


def test_a_task_the_execution_gave_up_on_is_stopped():
    process = Process(0, waits=5)
    client = Client([{"action": "step", "step": "company"}], give_up_after=1)
    activity_worker.work(client, "arn", lambda argv: process, tasks=1)
    assert process.terminated and client.reports == []


def test_the_state_machine_runs_readiness_then_the_given_steps_in_order_and_stops_at_the_first_failure():
    """Measured on Step Functions Local: a Map of one at a time still started the step after a failed one, so the steps
    are a loop, and a failed step (no Catch, no Retry) ends the execution before the next starts."""
    machine = json.loads(MACHINE.read_text())
    states = machine["States"]
    assert machine["StartAt"] == "Readiness" and states["Readiness"]["Next"] == "Start"
    assert states["Readiness"]["Parameters"] == {"action": "readiness"}
    assert not [s for s in states.values() if s["Type"] in ("Map", "Parallel")]
    assert states["Start"]["Parameters"]["next"] == 0 and states["Start"]["Next"] == "More"
    assert states["More"]["Choices"] == [{"Variable": "$.next", "NumericLessThanPath": "$.count", "Next": "Step"}]
    step = states["Step"]
    assert step["Parameters"] == {"action": "step", "step.$": "States.ArrayGetItem($.steps, $.next)", "plan.$": "$.plan"}
    assert step["Next"] == "Advance" and "Catch" not in step and "Retry" not in step
    assert states["Advance"]["Parameters"]["next.$"] == "States.MathAdd($.next, 1)" and states["Advance"]["Next"] == "More"
    for task in (states["Readiness"], step):
        assert task["Resource"] == "${activity}" and task["HeartbeatSeconds"] > 2 * activity_worker.HEARTBEAT_SECONDS
    chain = yaml.safe_load((REPO / "rules" / "load-chain.yaml").read_text())
    assert not [s["name"] for s in chain["steps"] if f'"{s["name"]}"' in MACHINE.read_text()]
