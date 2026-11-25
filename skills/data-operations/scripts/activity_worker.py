#!/usr/bin/env python3
"""Run the load pipeline's tasks in the loader image: take a task from Step Functions, run it, report how it ended.

    ACTIVITY_ARN=<arn> AWS_ENDPOINT_URL_SFN=<url> python activity_worker.py

A task's input says what to run: `{"action": "readiness"}`, `{"action": "begin", "steps": [...]}` (named steps: refuse the
load when a wait could never end, else mark its start), `{"action": "lanes"}` (the same for every lane, then the load jobs file's
lanes, in order, as the task's output), `{"action": "lane", "lane": "<name>", "plan": false}`, `{"action": "step", "step": "<name>", "plan": false}`,
or `{"action": "finish"}` (what follows the loads: links and lookups). The worker runs one task per lane at once, each with
the workers its step declares; the load jobs file's waits hold a step until the steps it needs are done. It
sends a heartbeat while a task runs, so the state machine learns of a worker that died. Each task's output goes to this
container's log; the run's own logs stay in `LOGS`. Beside the tasks, the lane controller (`load_jobs.control`) moves the running
steps' workers with the container's free memory, its CPU and the database.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # load_jobs sits beside this file
HEARTBEAT_SECONDS = 60
RETRY_POLL_SECONDS = 5


def forced(task: dict) -> list[str]:
    """`--force`: the task's load ignores the Change Journal and processes every document again (a plan has none to force)."""
    return ["--force"] if task.get("force") and not task.get("plan") else []


def begin_command(task: dict) -> list[str]:
    """Before a load's first step: every wait must be able to end (named steps in their order), then the start is marked."""
    named = task.get("steps")
    return [sys.executable, str(HERE / "load_jobs.py"), "--begin",
            *(["--steps", ",".join(named)] if named else []), *(["--plan"] if task.get("plan") else [])]


def command(task: dict) -> list[str]:
    """The command a task runs. An input of any other shape is refused, never guessed."""
    if task.get("action") == "begin" and isinstance(task.get("steps"), list) and task["steps"] \
            and all(isinstance(name, str) and name for name in task["steps"]):
        return begin_command(task)
    if task.get("action") == "readiness":
        return [sys.executable, str(HERE / "readiness.py")]
    if task.get("action") == "lane" and isinstance(task.get("lane"), str) and task["lane"]:
        return [sys.executable, str(HERE / "load_jobs.py"), "--lane", task["lane"], *(["--plan"] if task.get("plan") else []), *forced(task)]
    if task.get("action") == "finish":
        return [sys.executable, str(HERE / "load_jobs.py"), "--finish"]
    if task.get("action") == "step" and isinstance(task.get("step"), str) and task["step"]:
        return [sys.executable, str(HERE / "load_jobs.py"), "--only", task["step"], *(["--plan"] if task.get("plan") else []), *forced(task)]
    raise ValueError(f"a task is readiness, begin with its steps, lanes, a lane or a step with its name, or finish, not {sorted(task)}")


def run_task(client, token: str, task: dict, start=subprocess.Popen, every: float = HEARTBEAT_SECONDS) -> int:
    """Run one task to its end and report it. Returns the exit code (-1 when the input was refused)."""
    if task.get("action") == "lanes":  # read from the load jobs file in this image: the state machine names no lane
        code = start(begin_command(task)).wait()
        if code:
            client.send_task_failure(taskToken=token, error=f"Exit{code}", cause="load_jobs.py --begin refused or failed: read the worker's log")
        else:
            client.send_task_success(taskToken=token, output=json.dumps({"lanes": lanes()}))
        return code
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
    if code and task.get("action") == "lane" and not task.get("plan"):  # ended without its notes, perhaps: record them
        start([sys.executable, str(HERE / "load_jobs.py"), "--lane", task["lane"], "--mark-stopped"]).wait()
    if code == 0:
        client.send_task_success(taskToken=token, output=json.dumps({"exit": 0, **task}))
    else:
        client.send_task_failure(taskToken=token, error=f"Exit{code}",
                                 cause=f"{' '.join(Path(a).name for a in argv[1:])} ended with {code}: read the worker's log and the run's log")
    return code


def lanes() -> list[str]:
    """The load jobs file's lanes, in the order their first step appears."""
    import load_jobs

    return list(dict.fromkeys(step["lane"] for step in load_jobs.load_jobs()))


def work(client, activity: str, start=subprocess.Popen, tasks: int | None = None) -> None:
    """Take tasks until stopped (or `tasks` of them, for a test), one at a time. A poll that finds none returns empty and
    polls again."""
    name = f"{socket.gethostname()}-{threading.get_ident()}"
    taken = 0
    while tasks is None or taken < tasks:
        try:
            task = client.get_activity_task(activityArn=activity, workerName=name)
        except Exception as error:  # noqa: BLE001  a failed poll costs this poller a few seconds, never its slot
            print(f"poll failed: {type(error).__name__}; polling again", flush=True)
            time.sleep(RETRY_POLL_SECONDS)
            continue
        if not task.get("taskToken"):
            continue
        taken += 1
        print(f"task: {task['input']}", flush=True)
        try:
            run_task(client, task["taskToken"], json.loads(task["input"]), start)
        except Exception as error:  # noqa: BLE001  the task fails, the poller stays
            print(f"task failed in the worker: {type(error).__name__}", flush=True)
            try:
                client.send_task_failure(taskToken=task["taskToken"], error="WorkerError", cause=type(error).__name__)
            except Exception:  # noqa: BLE001  the heartbeat timeout reports it instead
                pass


def work_at_once(clients: list, activity: str, start=subprocess.Popen, tasks: int | None = None) -> None:
    """One poller per client, each taking one task at a time: as many tasks run at once as there are clients."""
    pollers = [threading.Thread(target=work, args=(client, activity, start, tasks), daemon=True) for client in clients]
    for poller in pollers:
        poller.start()
    for poller in pollers:
        poller.join()


def main() -> int:
    import boto3

    import load_jobs

    threading.Thread(target=load_jobs.control, daemon=True).start()
    # One poller per lane, never fewer: a lane holding a poller can wait on a step of a lane that would need another.
    work_at_once([boto3.client("stepfunctions") for _ in lanes()], os.environ["ACTIVITY_ARN"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
