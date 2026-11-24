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
    codes = iter([Process(0, waits=2), Process(2), Process(0)])

    def start(argv):
        started.append([Path(a).name if a.endswith(".py") else a for a in argv[1:]])
        return next(codes)
    client = Client([{"action": "readiness"}, {"action": "step", "step": "company", "plan": True}, {"action": "finish"}])
    activity_worker.work(client, "arn", start, tasks=3)
    assert started == [["readiness.py"], ["load_chain.py", "--only", "company", "--plan"], ["load_chain.py", "--finish"]]
    assert client.beats == 2
    assert client.reports == [("success", "t0", {"exit": 0, "action": "readiness"}), ("failure", "t1", "Exit2"),
                              ("success", "t2", {"exit": 0, "action": "finish"})]


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
    assert states["More"]["Default"] == "Finish?" and states["Finish?"]["Default"] == "Done"
    assert states["Finish?"]["Choices"] == [{"Variable": "$.finish", "BooleanEquals": True, "Next": "Finish"}]
    assert states["Finish"]["Parameters"] == {"action": "finish"} and states["Finish"]["Next"] == "Done"
    for task in (states["Readiness"], step, states["Finish"]):
        assert task["Resource"] == "${activity}" and task["HeartbeatSeconds"] > 2 * activity_worker.HEARTBEAT_SECONDS
    chain = yaml.safe_load((REPO / "rules" / "load-chain.yaml").read_text())
    assert not [s["name"] for s in chain["steps"] if f'"{s["name"]}"' in MACHINE.read_text()]


def test_every_variable_the_compose_file_requires_is_set_before_load_sh_first_runs_compose():
    """Compose reads every service's variables on any `up`: the emulator's `up` failed on the worker's activity, which
    exists only once the emulator answers ("required variable ACTIVITY_ARN is missing a value")."""
    import re

    required = set(re.findall(r"\$\{([A-Z_]+):\?", (MACHINE.parent / "compose.yml").read_text()))
    script = (MACHINE.parent / "load.sh").read_text()
    before = script[:script.index('"${compose[@]}" up')]
    set_before = set(re.findall(r"\b([A-Z_]+)=", before))
    assert required and not required - set_before, sorted(required - set_before)


def test_the_worker_s_client_points_at_the_emulator_the_compose_file_names(monkeypatch):
    """boto3 reads a service's endpoint from AWS_ENDPOINT_URL_<service id>, and Step Functions' id is SFN: a variable named
    for "stepfunctions" was ignored, so the worker called real AWS with the emulator's placeholder login."""
    pytest.importorskip("boto3")
    import boto3

    worker = yaml.safe_load((MACHINE.parent / "compose.yml").read_text())["services"]["worker"]["environment"]
    for name, value in worker.items():
        if name.startswith("AWS_") and "$" not in str(value):
            monkeypatch.setenv(name, str(value))
    assert boto3.client("stepfunctions").meta.endpoint_url == "http://localhost:8083"
