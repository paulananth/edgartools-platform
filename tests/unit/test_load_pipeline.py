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
    assert machine["StartAt"] == "Readiness" and states["Readiness"]["Next"] == "Mode"
    assert states["Readiness"]["Parameters"] == {"action": "readiness"}
    assert [n for n, s in states.items() if s["Type"] in ("Map", "Parallel")] == ["Run lanes"]  # the steps' branch has none
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


def test_the_worker_runs_a_lane_and_reads_the_lanes_from_the_chain_file_in_order(monkeypatch):
    client = Client([{"action": "lanes"}, {"action": "lane", "lane": "A", "plan": True}])
    started = []
    activity_worker.work(client, "arn", lambda argv: started.append(argv[2:]) or Process(0), tasks=2)
    assert started.pop(0) == ["--begin"]  # every wait checked and the start marked before the lanes
    chain = yaml.safe_load((REPO / "rules" / "load-chain.yaml").read_text())
    lanes = list(dict.fromkeys(step["lane"] for step in chain["steps"]))
    assert client.reports[0] == ("success", "t0", {"lanes": lanes}) and len(lanes) > 1
    assert started == [["--lane", "A", "--plan"]]


def test_the_worker_runs_as_many_tasks_at_once_as_it_has_pollers():
    """Every lane runs at once: one poller per lane, each running its task while the others run theirs."""
    import threading

    together = threading.Barrier(3, timeout=5)  # passes only when three tasks are running at the same time

    class Slow(Process):
        def wait(self, timeout=None):
            together.wait()
            return 0
    clients = [Client([{"action": "lane", "lane": lane}]) for lane in "ABC"]
    activity_worker.work_at_once(clients, "arn", lambda argv: Slow(0), tasks=1)
    assert [c.reports[0][0] for c in clients] == ["success"] * 3


def test_without_steps_the_state_machine_runs_every_lane_at_once_and_a_failed_lane_stops_no_other():
    """Measured on Step Functions Local: the three lanes started in the same second; with one failing, the other two ran
    to their end, then the execution failed and the finish did not run."""
    states = json.loads(MACHINE.read_text())["States"]
    assert states["Mode"]["Choices"] == [{"Variable": "$.steps", "IsPresent": True, "Next": "Begin"}]
    assert states["Mode"]["Default"] == "Lanes" and states["Lanes"]["Parameters"] == {"action": "lanes", "plan.$": "$.plan"}
    run = states["Run lanes"]
    assert run["Type"] == "Map" and run["ItemsPath"] == "$.lanes.names" and run["MaxConcurrency"] == 0
    lane = run["Iterator"]["States"]["Lane"]
    assert lane["Parameters"] == {"action": "lane", "lane.$": "$.lane", "plan.$": "$.plan"} and "Retry" not in lane
    assert lane["Catch"] == [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "Lane failed"}]
    assert run["Iterator"]["States"]["Lane failed"]["Parameters"]["failed"] is True
    assert states["Count"]["Parameters"]["failed.$"] == "States.ArrayContains($.results[*].failed, true)"
    assert states["Lanes ended"]["Choices"][0]["Next"] == "A lane failed" and states["Lanes ended"]["Default"] == "Finish?"
    for task in (states["Lanes"], lane):
        assert task["Resource"] == "${activity}" and task["HeartbeatSeconds"] > 2 * activity_worker.HEARTBEAT_SECONDS


def test_the_state_machine_names_no_lane_and_no_step_so_the_chain_file_alone_decides_what_runs():
    """What a lane runs is never fixed in the state machine: the loader reads the lanes, their steps, order and waits from
    the chain file in the image at run time."""
    text = MACHINE.read_text()
    chain = yaml.safe_load((REPO / "rules" / "load-chain.yaml").read_text())
    names = {s["name"] for s in chain["steps"]} | {s["lane"] for s in chain["steps"]}
    assert not sorted(n for n in names if f'"{n}"' in text)


def test_each_load_gets_its_own_activity_so_no_poller_of_an_older_worker_takes_its_tasks():
    """Measured: a long poll still held by the worker compose had just replaced took the readiness task 3 ms after it was
    scheduled; that poller was gone, so the task never ran and timed out on its heartbeat. A new activity per load is polled
    only by the worker started with it; the older activities are deleted."""
    import re

    script = (MACHINE.parent / "load.sh").read_text()
    (name,) = re.findall(r"create-activity --name (\S+)", script)
    assert "$" in name, name
    assert "delete-activity" in script
    assert script.index("delete-activity") < script.index("create-activity") < script.index('up -d worker')


def test_a_poll_that_fails_costs_the_poller_a_moment_never_its_slot(monkeypatch):
    class Flaky(Client):
        def get_activity_task(self, activityArn, workerName):
            if not getattr(self, "failed", False):
                self.failed = True
                raise ConnectionError("the emulator restarted")
            return super().get_activity_task(activityArn, workerName)
    monkeypatch.setattr(activity_worker.time, "sleep", lambda s: None)
    client = Flaky([{"action": "step", "step": "company"}])
    activity_worker.work(client, "arn", lambda argv: Process(0), tasks=1)
    assert client.reports[0][0] == "success"


def test_a_plan_of_every_lane_checks_the_waits_and_marks_no_load_start():
    started = []
    client = Client([{"action": "lanes", "plan": True}])
    activity_worker.work(client, "arn", lambda argv: started.append(argv[2:]) or Process(0), tasks=1)
    assert started == [["--begin", "--plan"]] and client.reports[0][0] == "success"


def test_named_steps_are_checked_in_their_order_before_the_first_runs_and_a_refusal_stops_the_load():
    """Measured: six named steps loaded, then the seventh waited on a step not in the run. The check runs first."""
    started = []
    client = Client([{"action": "begin", "steps": ["a1", "b1"], "plan": False}, {"action": "lanes"}])
    activity_worker.work(client, "arn", lambda argv: started.append(argv[2:]) or Process(2), tasks=2)
    assert started == [["--begin", "--steps", "a1,b1"], ["--begin"]]
    assert [r[0] for r in client.reports] == ["failure", "failure"]
    states = json.loads(MACHINE.read_text())["States"]
    begin = states["Begin"]
    assert begin["Parameters"] == {"action": "begin", "steps.$": "$.steps", "plan.$": "$.plan"} and begin["Next"] == "Start"
    assert "Catch" not in begin and "Retry" not in begin  # a refusal ends the execution before any step


def test_a_lane_that_ends_without_success_has_its_unfinished_steps_recorded():
    started = []
    codes = iter([Process(-9), Process(0)])
    client = Client([{"action": "lane", "lane": "A"}])
    activity_worker.work(client, "arn", lambda argv: started.append(argv[2:]) or next(codes), tasks=1)
    assert started == [["--lane", "A"], ["--lane", "A", "--mark-stopped"]]
    assert client.reports == [("failure", "t0", "Exit-9")]
