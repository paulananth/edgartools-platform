#!/usr/bin/env python3
"""Run the load pipeline's tasks in the loader image: take a task from Step Functions, run it, report how it ended.

    ACTIVITY_ARN=<arn> AWS_ENDPOINT_URL_STEPFUNCTIONS=<url> python activity_worker.py

A task's input says what to run: `{"action": "readiness"}`, `{"action": "step", "step": "<name>", "plan": false}`, or
`{"action": "finish"}` (what follows the loads: links and lookups). The
worker takes one task at a time, so one load runs at once. It sends a heartbeat while the task runs, so the state machine
learns of a worker that died. Each task's output goes to this container's log; the chain's own logs stay in `LOGS`.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEARTBEAT_SECONDS = 60


def command(task: dict) -> list[str]:
    """The command a task runs. An input of any other shape is refused, never guessed."""
    if task.get("action") == "readiness":
        return [sys.executable, str(HERE / "readiness.py")]
    if task.get("action") == "finish":
        return [sys.executable, str(HERE / "load_chain.py"), "--finish"]
    if task.get("action") == "step" and isinstance(task.get("step"), str) and task["step"]:
        return [sys.executable, str(HERE / "load_chain.py"), "--only", task["step"], *(["--plan"] if task.get("plan") else [])]
    raise ValueError(f"a task is readiness, a step with its name, or finish, not {sorted(task)}")


def run_task(client, token: str, task: dict, start=subprocess.Popen, every: float = HEARTBEAT_SECONDS) -> int:
    """Run one task to its end and report it. Returns the exit code (-1 when the input was refused)."""
    try:
        argv = command(task)
    except ValueError as refused:
        client.send_task_failure(taskToken=token, error="BadInput", cause=str(refused))
        return -1
    process = start(argv)
    while True:
        try:
            code = process.wait(timeout=every)
            break
        except subprocess.TimeoutExpired:
            try:
                client.send_task_heartbeat(taskToken=token)
            except client.exceptions.TaskTimedOut:  # the execution gave up on this task: stop the work it no longer waits for
                process.terminate()
                return process.wait()
    if code == 0:
        client.send_task_success(taskToken=token, output=json.dumps({"exit": 0, **task}))
    else:
        client.send_task_failure(taskToken=token, error=f"Exit{code}",
                                 cause=f"{' '.join(Path(a).name for a in argv[1:])} ended with {code}: read the worker's log and the chain's log")
    return code


def work(client, activity: str, start=subprocess.Popen, tasks: int | None = None) -> None:
    """Take tasks until stopped (or `tasks` of them, for a test). A poll that finds none returns empty and polls again."""
    name = socket.gethostname()
    taken = 0
    while tasks is None or taken < tasks:
        task = client.get_activity_task(activityArn=activity, workerName=name)
        if not task.get("taskToken"):
            continue
        taken += 1
        print(f"task: {task['input']}", flush=True)
        run_task(client, task["taskToken"], json.loads(task["input"]), start)


def main() -> int:
    import boto3

    work(boto3.client("stepfunctions"), os.environ["ACTIVITY_ARN"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
