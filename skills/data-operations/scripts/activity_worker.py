#!/usr/bin/env python3
"""Run the load pipeline's tasks in the loader image: take a task from Step Functions, run it, report how it ended.

    ACTIVITY_ARN=<arn> AWS_ENDPOINT_URL_SFN=<url> python activity_worker.py

A task's input says what to run: `{"action": "readiness"}`, `{"action": "lanes"}` (the chain file's lanes, in order, as the
task's output), `{"action": "lane", "lane": "<name>", "plan": false}`, `{"action": "step", "step": "<name>", "plan": false}`,
or `{"action": "finish"}` (what follows the loads: links and lookups). The worker runs up to `WORKER_TASKS` tasks at once, one
per lane, each with the workers its step declares; the chain file's waits hold a step until the steps it needs are done. It
sends a heartbeat while a task runs, so the state machine learns of a worker that died. Each task's output goes to this
container's log; the chain's own logs stay in `LOGS`.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEARTBEAT_SECONDS = 60


def command(task: dict) -> list[str]:
    """The command a task runs. An input of any other shape is refused, never guessed."""
    if task.get("action") == "readiness":
        return [sys.executable, str(HERE / "readiness.py")]
    if task.get("action") == "lane" and isinstance(task.get("lane"), str) and task["lane"]:
        return [sys.executable, str(HERE / "load_chain.py"), "--lane", task["lane"], *(["--plan"] if task.get("plan") else [])]
    if task.get("action") == "finish":
        return [sys.executable, str(HERE / "load_chain.py"), "--finish"]
    if task.get("action") == "step" and isinstance(task.get("step"), str) and task["step"]:
        return [sys.executable, str(HERE / "load_chain.py"), "--only", task["step"], *(["--plan"] if task.get("plan") else [])]
    raise ValueError(f"a task is readiness, lanes, a lane or a step with its name, or finish, not {sorted(task)}")


def run_task(client, token: str, task: dict, start=subprocess.Popen, every: float = HEARTBEAT_SECONDS) -> int:
    """Run one task to its end and report it. Returns the exit code (-1 when the input was refused)."""
    if task.get("action") == "lanes":  # read from the chain file in this image: the state machine names no lane
        client.send_task_success(taskToken=token, output=json.dumps({"lanes": lanes()}))
        return 0
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


def lanes() -> list[str]:
    """The chain file's lanes, in the order their first step appears."""
    sys.path.insert(0, str(HERE))
    import load_chain

    return list(dict.fromkeys(step["lane"] for step in load_chain.chain_steps()))


def work(client, activity: str, start=subprocess.Popen, tasks: int | None = None) -> None:
    """Take tasks until stopped (or `tasks` of them, for a test), one at a time. A poll that finds none returns empty and
    polls again."""
    name = f"{socket.gethostname()}-{threading.get_ident()}"
    taken = 0
    while tasks is None or taken < tasks:
        task = client.get_activity_task(activityArn=activity, workerName=name)
        if not task.get("taskToken"):
            continue
        taken += 1
        print(f"task: {task['input']}", flush=True)
        run_task(client, task["taskToken"], json.loads(task["input"]), start)


def work_at_once(clients: list, activity: str, start=subprocess.Popen, tasks: int | None = None) -> None:
    """One poller per client, each taking one task at a time: as many tasks run at once as there are clients."""
    pollers = [threading.Thread(target=work, args=(client, activity, start, tasks), daemon=True) for client in clients]
    for poller in pollers:
        poller.start()
    for poller in pollers:
        poller.join()


def main() -> int:
    import boto3

    slots = int(os.environ.get("WORKER_TASKS") or len(lanes()))
    work_at_once([boto3.client("stepfunctions") for _ in range(slots)], os.environ["ACTIVITY_ARN"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
