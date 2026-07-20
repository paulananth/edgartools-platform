"""Live monitor for a bronze-seed-silver-gold release execution.

Prints immediate feedback for every step as it happens: state transitions,
Distributed Map batch progress (the strict Map's per-batch work is invisible
in the top-level execution history — it only surfaces through the Map Run
APIs), ECS task starts with tail hints, and failures with error/cause.

Usage:
    python scripts/ops/watch_release.py                    # latest execution, prod
    python scripts/ops/watch_release.py --env dev
    python scripts/ops/watch_release.py --exec <execution-arn>
    python scripts/ops/watch_release.py --interval 5
    python scripts/ops/watch_release.py --profile edgartools-690

Exit codes: 0 execution SUCCEEDED, 2 FAILED/ABORTED/TIMED_OUT, 3 usage or
lookup error. Watching an already-finished execution replays its history and
exits with the same mapping, so the monitor can also be used post-hoc.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

STATE_MACHINE_BASENAME = "bronze-seed-silver-gold"
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"}

# Event types worth a line of output; everything else (lambda scheduling
# noise, etc.) stays silent so each printed line maps to a real step change.
_ENTER_TYPES = {
    "ChoiceStateEntered",
    "TaskStateEntered",
    "MapStateEntered",
    "PassStateEntered",
    "FailStateEntered",
}
_EXIT_TYPES = {
    "ChoiceStateExited",
    "TaskStateExited",
    "MapStateExited",
    "PassStateExited",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="prod", choices=["dev", "prod"])
    parser.add_argument("--exec", dest="execution_arn", default=None)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default="us-east-1")
    return parser


class AwsCli:
    def __init__(self, profile: str | None, region: str) -> None:
        self.region = region
        self._base = ["aws"]
        if profile:
            self._base += ["--profile", profile]
        self._base += ["--region", region, "--output", "json"]

    def call(self, *args: str) -> dict:
        result = subprocess.run(
            self._base + list(args), capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip()[:500])
        return json.loads(result.stdout) if result.stdout.strip() else {}


def _clock(ts: object) -> str:
    # History timestamps arrive as epoch floats or ISO strings depending on
    # CLI version; render both as local HH:MM:SS.
    if isinstance(ts, (int, float)):
        return time.strftime("%H:%M:%S", time.localtime(ts))
    text = str(ts)
    return text[11:19] if len(text) >= 19 else text


def find_execution(cli: AwsCli, env: str) -> str:
    account = cli.call("sts", "get-caller-identity")["Account"]
    sm_arn = (
        f"arn:aws:states:{cli.region}:{account}:stateMachine:"
        f"edgartools-{env}-{STATE_MACHINE_BASENAME}"
    )
    running = cli.call(
        "stepfunctions", "list-executions", "--state-machine-arn", sm_arn,
        "--status-filter", "RUNNING", "--max-results", "1",
    ).get("executions", [])
    if running:
        return running[0]["executionArn"]
    latest = cli.call(
        "stepfunctions", "list-executions", "--state-machine-arn", sm_arn,
        "--max-results", "1",
    ).get("executions", [])
    if latest:
        print(
            f"note: no RUNNING execution on {sm_arn.rsplit(':', 1)[-1]}; "
            f"replaying latest ({latest[0]['status']})"
        )
        return latest[0]["executionArn"]
    raise RuntimeError(f"no executions found for {sm_arn}")


def fetch_history(cli: AwsCli, execution_arn: str) -> list[dict]:
    events: list[dict] = []
    token: str | None = None
    while True:
        args = [
            "stepfunctions", "get-execution-history",
            "--execution-arn", execution_arn, "--max-results", "1000",
        ]
        if token:
            args += ["--next-token", token]
        page = cli.call(*args)
        events.extend(page.get("events", []))
        token = page.get("nextToken")
        if not token:
            return events


def _ecs_task_id(event: dict) -> str | None:
    output = (event.get("taskSubmittedEventDetails") or {}).get("output")
    if not output:
        return None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    tasks = payload.get("Tasks") or payload.get("tasks") or []
    if not tasks:
        return None
    arn = tasks[0].get("TaskArn") or tasks[0].get("taskArn") or ""
    return arn.rsplit("/", 1)[-1] or None


def render_event(event: dict, env: str) -> list[str]:
    """Turn one history event into zero or more human lines."""
    etype = event["type"]
    when = _clock(event.get("timestamp"))
    lines: list[str] = []
    if etype == "ExecutionStarted":
        lines.append(f"{when}  === execution started ===")
    elif etype in _ENTER_TYPES:
        name = event["stateEnteredEventDetails"]["name"]
        lines.append(f"{when}  > {name}")
    elif etype in _EXIT_TYPES:
        name = event["stateExitedEventDetails"]["name"]
        lines.append(f"{when}  ✓ {name} done")
    elif etype == "TaskSubmitted":
        task_id = _ecs_task_id(event)
        if task_id:
            lines.append(
                f"{when}    ECS task {task_id} started"
                f"  (logs: scripts/ops/tail-task.sh {task_id} --env {env})"
            )
    elif etype == "MapRunStarted":
        lines.append(f"{when}    distributed map run started")
    elif etype == "MapRunFailed":
        details = event.get("mapRunFailedEventDetails") or {}
        lines.append(
            f"{when}  ✗ MAP RUN FAILED: {details.get('error', '?')} — "
            f"{(details.get('cause') or '')[:300]}"
        )
    elif etype == "TaskFailed":
        details = event.get("taskFailedEventDetails") or {}
        lines.append(
            f"{when}  ✗ TASK FAILED: {details.get('error', '?')} — "
            f"{(details.get('cause') or '')[:300]}"
        )
    elif etype in ("ExecutionSucceeded",):
        lines.append(f"{when}  === execution SUCCEEDED ===")
    elif etype in ("ExecutionFailed", "ExecutionTimedOut", "ExecutionAborted"):
        details = (
            event.get("executionFailedEventDetails")
            or event.get("executionTimedOutEventDetails")
            or {}
        )
        suffix = ""
        if details:
            suffix = (
                f": {details.get('error', '?')} — "
                f"{(details.get('cause') or '')[:300]}"
            )
        lines.append(f"{when}  === execution {etype[9:].upper()}{suffix} ===")
    return lines


def map_run_arn_from(events: list[dict]) -> str | None:
    for event in events:
        if event["type"] == "MapRunStarted":
            details = event.get("mapRunStartedEventDetails") or {}
            if details.get("mapRunArn"):
                return details["mapRunArn"]
    return None


def format_map_progress(counts: dict) -> str:
    total = counts.get("total", 0)
    return (
        f"    map progress: {counts.get('succeeded', 0)}/{total} batches"
        f" succeeded, {counts.get('running', 0)} running,"
        f" {counts.get('pending', 0)} pending,"
        f" {counts.get('failed', 0)} failed"
    )


def exit_code_for(status: str) -> int:
    return 0 if status == "SUCCEEDED" else 2


def watch(cli: AwsCli, execution_arn: str, env: str, interval: float) -> int:
    described = cli.call(
        "stepfunctions", "describe-execution", "--execution-arn", execution_arn
    )
    print(f"watching: {described['name']}")
    print(f"  arn:    {execution_arn}")
    print(f"  status: {described['status']}  started: {described.get('startDate', '?')}")
    try:
        exec_input = json.loads(described.get("input") or "{}")
        if exec_input.get("fingerprint"):
            print(f"  fingerprint: {exec_input['fingerprint']}")
        if exec_input.get("candidate_manifest_key"):
            print(f"  manifest:    {exec_input['candidate_manifest_key']}")
    except json.JSONDecodeError:
        pass
    print()

    printed_events = 0
    map_run_arn: str | None = None
    last_map_line = ""
    reported_failed_children: set[str] = set()

    while True:
        events = fetch_history(cli, execution_arn)
        for event in events[printed_events:]:
            for line in render_event(event, env):
                print(line, flush=True)
        if map_run_arn is None:
            map_run_arn = map_run_arn_from(events[printed_events:] or events)
        printed_events = len(events)

        if map_run_arn:
            try:
                run = cli.call(
                    "stepfunctions", "describe-map-run",
                    "--map-run-arn", map_run_arn,
                )
                counts = run.get("itemCounts", {})
                line = format_map_progress(counts)
                if line != last_map_line:
                    print(f"{time.strftime('%H:%M:%S')}{line}", flush=True)
                    last_map_line = line
                if counts.get("failed", 0) > 0:
                    failed = cli.call(
                        "stepfunctions", "list-executions",
                        "--map-run-arn", map_run_arn,
                        "--status-filter", "FAILED", "--max-results", "20",
                    ).get("executions", [])
                    for child in failed:
                        if child["executionArn"] in reported_failed_children:
                            continue
                        reported_failed_children.add(child["executionArn"])
                        print(
                            f"{time.strftime('%H:%M:%S')}  ✗ FAILED batch child:"
                            f" {child['name']}\n"
                            f"      diagnose: scripts/ops/diagnose-execution.sh"
                            f" --env {env} --exec {child['executionArn']}",
                            flush=True,
                        )
            except RuntimeError as exc:
                print(f"  (map-run poll error: {exc})", flush=True)

        status = cli.call(
            "stepfunctions", "describe-execution", "--execution-arn", execution_arn
        )["status"]
        if status in TERMINAL_STATUSES:
            # One final history sweep so terminal events always print.
            for event in fetch_history(cli, execution_arn)[printed_events:]:
                for line in render_event(event, env):
                    print(line, flush=True)
            print(f"\nfinal status: {status}")
            return exit_code_for(status)
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cli = AwsCli(args.profile, args.region)
    try:
        execution_arn = args.execution_arn or find_execution(cli, args.env)
        return watch(cli, execution_arn, args.env, args.interval)
    except KeyboardInterrupt:
        print("\ninterrupted — execution continues server-side")
        return 130
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
