"""Prepare, launch, and report the ECS sizing canaries from Ticket 28.

The command is deliberately dry-run-first. ``prepare`` derives unscheduled
Standard state machines from the current production definitions and changes
only the covered task-definition references. ``start`` launches one fresh
execution. ``report`` binds Step Functions attempts to exact ECS tasks and
task-level Container Insights samples.

Examples:
    uv run python scripts/ops/ecs_sizing_canary.py prepare
    uv run python scripts/ops/ecs_sizing_canary.py prepare --apply
    uv run python scripts/ops/ecs_sizing_canary.py start sync --attempt 1
    uv run python scripts/ops/ecs_sizing_canary.py start residual --attempt 1
    uv run python scripts/ops/ecs_sizing_canary.py report --execution-arn ARN
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

EXPECTED_ACCOUNT = "690839588395"
CLUSTER_BASENAME = "warehouse"
PERFORMANCE_LOG_GROUP = "/aws/ecs/containerinsights/{cluster}/performance"
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"}
FARGATE_VCPU_HOUR_USD = 0.0404784
FARGATE_GIB_HOUR_USD = 0.004446
FARGATE_PRICING_SOURCE = "https://aws.amazon.com/fargate/pricing/"
FARGATE_PRICING_CAPTURED_AT = "2026-08-29"
CANARIES = {
    "sync": {
        "source": "mdm-utility",
        "name": "canary-ticket28-mdm-sync-graph-large",
        "source_family": "mdm-medium",
        "candidate_family": "mdm-large",
        "state_prefix": "mdm_sync_graph_",
        "expected_changes": {5, 7},
        "input": {"mode": "mdm_sync_graph", "limit": 0},
    },
    "residual": {
        "source": "residual-holds-graph",
        "name": "canary-ticket28-residual-holds-medium",
        "source_family": "mdm-large",
        "candidate_family": "mdm-medium",
        "state_prefix": "Mdm",
        "expected_changes": {8},
        "input": {},
    },
    "residual-control": {
        "source": "residual-holds-graph",
        "name": "canary-ticket28-residual-holds-large-control",
        "source_family": "mdm-large",
        "candidate_family": "mdm-large",
        "state_prefix": "Mdm",
        "expected_changes": {8},
        "input": {},
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="sec_platform_deployer")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--env", default="prod", choices=["dev", "prod"])
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="plan or upsert both canaries")
    prepare.add_argument(
        "--apply", action="store_true", help="create/update unscheduled canary machines"
    )
    prepare.add_argument("--output", type=Path)

    start = subparsers.add_parser("start", help="launch one fresh canary execution")
    start.add_argument("cohort", choices=sorted(CANARIES))
    start.add_argument("--attempt", required=True, type=int)
    start.add_argument("--output", type=Path)
    start.add_argument(
        "--allow-concurrent",
        action="store_true",
        help="allow launch while another ECS task is running in the cluster",
    )

    report = subparsers.add_parser("report", help="collect task-bound evidence")
    report.add_argument("--execution-arn", required=True)
    report.add_argument("--launch-manifest", required=True, type=Path)
    report.add_argument("--output", type=Path)
    report.add_argument(
        "--allow-running", action="store_true", help="emit provisional evidence"
    )
    return parser


class AwsCli:
    """Small injectable boundary around the AWS CLI used by the operator flow."""

    def __init__(self, profile: str, region: str) -> None:
        self.region = region
        self._base = [
            "aws",
            "--profile",
            profile,
            "--region",
            region,
            "--output",
            "json",
        ]

    def call(self, *args: str) -> dict[str, Any]:
        result = subprocess.run(
            self._base + list(args), capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(detail[:1000])
        return json.loads(result.stdout) if result.stdout.strip() else {}


def _task_definition(state: dict[str, Any]) -> str | None:
    return (state.get("Parameters") or {}).get("TaskDefinition")


def rewrite_task_definitions(
    definition: dict[str, Any],
    *,
    state_names: set[str],
    source_arn: str,
    candidate_arn: str,
) -> tuple[dict[str, Any], int]:
    """Return a copy with exact, named task references replaced.

    Every named state must be an ECS task pinned to ``source_arn``. This makes
    definition drift a hard error instead of silently creating a mixed canary.
    """
    rewritten = copy.deepcopy(definition)
    states = rewritten.get("States") or {}
    missing = sorted(state_names - states.keys())
    if missing:
        raise ValueError(f"canary states missing from source definition: {missing}")
    changes = 0
    for name in sorted(state_names):
        actual = _task_definition(states[name])
        if actual != source_arn:
            raise ValueError(
                f"{name} expected source task definition {source_arn}, found {actual}"
            )
        if actual != candidate_arn:
            states[name]["Parameters"]["TaskDefinition"] = candidate_arn
            changes += 1
    return rewritten, changes


def add_unbounded_sync_route(definition: dict[str, Any]) -> dict[str, Any]:
    """Add Ticket 28's limit=0 -> no-limit route to a legacy utility clone.

    Current source after Ticket 28 already contains the canonical unbounded
    route. Older live definitions need this isolated compatibility overlay so
    the canary does not pass an invalid ``--limit 0`` to the Python CLI.
    """
    rewritten = copy.deepcopy(definition)
    states = rewritten.get("States") or {}
    if "mdm_sync_graph_HasUnboundedLimitOverride" in states:
        return rewritten

    select_mode = states.get("SelectMode") or {}
    sync_choice = next(
        (
            choice
            for choice in select_mode.get("Choices", [])
            if choice.get("StringEquals") == "mdm_sync_graph"
        ),
        None,
    )
    if not sync_choice or not sync_choice.get("Next"):
        raise ValueError("source utility definition has no mdm_sync_graph mode route")
    original_start = sync_choice["Next"]
    template = states.get("mdm_sync_graph_RunMdmTaskWithLimit")
    if not template:
        raise ValueError("source utility definition has no sync-graph limit task")
    unbounded = copy.deepcopy(template)
    containers = (
        unbounded.get("Parameters", {})
        .get("Overrides", {})
        .get("ContainerOverrides", [])
    )
    if len(containers) != 1:
        raise ValueError("sync-graph limit task has an unexpected container override")
    containers[0]["Command.$"] = "States.Array('mdm', 'sync-graph')"
    states["Ticket28RunUnboundedSync"] = unbounded
    states["Ticket28HasUnboundedSyncLimit"] = {
        "Type": "Choice",
        "Choices": [
            {
                "And": [
                    {"Variable": "$.limit", "IsPresent": True},
                    {"Variable": "$.limit", "IsNumeric": True},
                    {"Variable": "$.limit", "NumericEquals": 0},
                ],
                "Next": "Ticket28RunUnboundedSync",
            }
        ],
        "Default": original_start,
    }
    sync_choice["Next"] = "Ticket28HasUnboundedSyncLimit"
    return rewritten


def add_unbounded_residual_sync(
    definition: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Remove the legacy per-type cap from residual graph materialization.

    The legacy production definition caps every relationship type at 200,000,
    which makes its generation-scoped verifier deterministically fail once a
    type grows beyond that count. Match only the exact known command so a
    future orchestration change cannot be silently rewritten.
    """
    rewritten = copy.deepcopy(definition)
    containers = (
        (rewritten.get("States") or {})
        .get("MdmSync", {})
        .get("Parameters", {})
        .get("Overrides", {})
        .get("ContainerOverrides", [])
    )
    if len(containers) != 1:
        raise ValueError("residual MdmSync has an unexpected container override")
    legacy = (
        "States.Array('mdm', 'sync-graph', "
        "'--generation-id', $$.Execution.Name, "
        "'--limit-per-type', '200000')"
    )
    unbounded = (
        "States.Array('mdm', 'sync-graph', "
        "'--generation-id', $$.Execution.Name)"
    )
    command = containers[0].get("Command.$")
    if command == unbounded:
        return rewritten, False
    if command != legacy:
        raise ValueError(f"unexpected residual sync command: {command!r}")
    containers[0]["Command.$"] = unbounded
    return rewritten, True


def _task_states(definition: dict[str, Any]) -> dict[str, str]:
    return {
        name: task_arn
        for name, state in (definition.get("States") or {}).items()
        if (task_arn := _task_definition(state)) is not None
    }


def _json_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate a percentile without samples")
    rank = (len(ordered) - 1) * percentile
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _metric_summary(
    values: list[float], reserved: float, period_seconds: int
) -> dict[str, float | int]:
    average = sum(values) / len(values)
    maximum = max(values)
    p95 = _percentile(values, 0.95)
    result: dict[str, float | int] = {
        "reserved": reserved,
        "average": average,
        "maximum": maximum,
        "p95": p95,
        "average_percent": average / reserved * 100,
        "maximum_percent": maximum / reserved * 100,
        "p95_percent": p95 / reserved * 100,
    }
    for band in (70, 80, 90):
        result[f"seconds_at_or_above_{band}_percent"] = (
            sum(1 for value in values if value / reserved * 100 >= band)
            * period_seconds
        )
    return result


def summarize_utilization(
    samples: list[dict[str, float]],
    *,
    cpu_reserved: float,
    memory_reserved: float,
    period_seconds: int = 60,
) -> dict[str, Any]:
    if not samples:
        raise ValueError("task-bound telemetry is empty")
    return {
        "sample_count": len(samples),
        "period_seconds": period_seconds,
        "cpu": _metric_summary(
            [float(sample["cpu"]) for sample in samples],
            cpu_reserved,
            period_seconds,
        ),
        "memory": _metric_summary(
            [float(sample["memory"]) for sample in samples],
            memory_reserved,
            period_seconds,
        ),
    }


def fargate_usage(
    *, cpu_units: int, memory_mib: int, pull_to_stop_seconds: float
) -> dict[str, float | int]:
    """Calculate on-demand Linux/x86 usage with AWS's per-second rounding."""
    billed_seconds = math.ceil(pull_to_stop_seconds)
    vcpu_hours = cpu_units / 1024 * billed_seconds / 3600
    memory_gib_hours = memory_mib / 1024 * billed_seconds / 3600
    return {
        "billed_duration_seconds": billed_seconds,
        "requested_vcpu_hours": vcpu_hours,
        "requested_memory_gib_hours": memory_gib_hours,
        "estimated_compute_cost_usd": (
            vcpu_hours * FARGATE_VCPU_HOUR_USD
            + memory_gib_hours * FARGATE_GIB_HOUR_USD
        ),
    }


def _ancestor_state(event: dict[str, Any], by_id: dict[int, dict[str, Any]]) -> str:
    cursor = event
    visited: set[int] = set()
    while previous := cursor.get("previousEventId"):
        if previous in visited:
            break
        visited.add(previous)
        cursor = by_id.get(previous, {})
        details = cursor.get("stateEnteredEventDetails") or {}
        if details.get("name"):
            return str(details["name"])
    return "unknown"


def extract_task_attempts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bind every TaskSubmitted event to its state and retry ordinal."""
    by_id = {int(event["id"]): event for event in events if "id" in event}
    terminal_tasks: dict[str, dict[str, Any]] = {}
    for event in events:
        event_type = event.get("type")
        if event_type == "TaskSucceeded":
            raw_terminal = (event.get("taskSucceededEventDetails") or {}).get(
                "output"
            )
        elif event_type == "TaskFailed":
            raw_terminal = (event.get("taskFailedEventDetails") or {}).get("cause")
        else:
            continue
        try:
            terminal_payload = json.loads(raw_terminal or "{}")
        except json.JSONDecodeError:
            continue
        candidates = terminal_payload.get("Tasks") or terminal_payload.get("tasks")
        if not candidates:
            candidates = [terminal_payload]
        for candidate in candidates:
            task_arn = candidate.get("TaskArn") or candidate.get("taskArn") or ""
            task_id = task_arn.rsplit("/", 1)[-1]
            if task_id:
                terminal_tasks[task_id] = candidate

    ordinals: dict[str, int] = {}
    attempts: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "TaskSubmitted":
            continue
        raw = (event.get("taskSubmittedEventDetails") or {}).get("output")
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            continue
        tasks = payload.get("Tasks") or payload.get("tasks") or []
        if not tasks:
            continue
        task_arn = tasks[0].get("TaskArn") or tasks[0].get("taskArn") or ""
        task_id = task_arn.rsplit("/", 1)[-1]
        if not task_id:
            continue
        state = _ancestor_state(event, by_id)
        ordinals[state] = ordinals.get(state, 0) + 1
        attempt = {"state": state, "retry_ordinal": ordinals[state], "task_id": task_id}
        if task_id in terminal_tasks:
            attempt["task_snapshot"] = terminal_tasks[task_id]
        attempts.append(attempt)
    return attempts


def extract_json_documents(messages: list[str]) -> list[dict[str, Any]]:
    """Extract single-line and pretty-printed JSON objects from awslogs messages."""
    documents: list[dict[str, Any]] = []
    buffer: list[str] = []
    depth = 0
    for message in messages:
        stripped = message.strip()
        if not buffer:
            try:
                parsed = json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                documents.append(parsed)
                continue
            if not stripped.startswith("{"):
                continue
        buffer.append(message)
        depth += stripped.count("{") - stripped.count("}")
        if depth > 0:
            continue
        try:
            parsed = json.loads("\n".join(buffer))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            documents.append(parsed)
        buffer = []
        depth = 0
    return documents


def evaluate_execution(
    *, execution_status: str, tasks: list[dict[str, Any]]
) -> dict[str, Any]:
    """Apply the fail-closed execution-local Ticket 03/04 gates."""
    failures: list[str] = []
    warnings: list[str] = []
    if execution_status != "SUCCEEDED":
        failures.append(f"execution status is {execution_status}, not SUCCEEDED")
    if not tasks:
        failures.append("no ECS task attempts found in execution history")
    for task in tasks:
        state = task["state"]
        if task.get("retry_ordinal", 1) > 1:
            failures.append(
                f"workload retry observed: {state} attempt {task['retry_ordinal']}"
            )
        if task.get("exit_code") not in (0, None):
            failures.append(f"non-zero exit for {state}: {task['exit_code']}")
        if task.get("exit_code") is None:
            failures.append(f"exit code missing for {state}")
        telemetry = task.get("telemetry")
        if not telemetry or not telemetry.get("sample_count"):
            failures.append(f"task-bound telemetry missing for {state}")
            continue
        memory = telemetry["memory"]
        if memory["maximum_percent"] >= 85:
            failures.append(
                f"memory peak gate failed for {state}: "
                f"{memory['maximum_percent']:.2f}% >= 85%"
            )
        if memory["p95_percent"] >= 75:
            failures.append(
                f"memory p95 gate failed for {state}: "
                f"{memory['p95_percent']:.2f}% >= 75%"
            )
        cpu = telemetry.get("cpu") or {}
        if cpu.get("p95_percent", 0) >= 90:
            warnings.append(
                f"CPU constrained for {state}: {cpu['p95_percent']:.2f}% >= 90%"
            )
    return {"passed": not failures, "failures": failures, "warnings": warnings}


def validate_attempt_sequence(
    executions: list[dict[str, Any]], *, cohort: str, attempt: int
) -> None:
    """Require one terminal predecessor, no active execution, and no reuse."""
    running = [
        execution["name"]
        for execution in executions
        if execution["status"] == "RUNNING"
    ]
    if running:
        raise ValueError(f"cohort execution is still RUNNING: {running[0]}")
    current_prefix = f"ticket28-{cohort}-{attempt}-"
    if any(execution["name"].startswith(current_prefix) for execution in executions):
        raise ValueError(f"attempt {attempt} has already been used for {cohort}")
    if attempt == 1:
        return
    prior_prefix = f"ticket28-{cohort}-{attempt - 1}-"
    if not any(execution["name"].startswith(prior_prefix) for execution in executions):
        raise ValueError(f"prior attempt {attempt - 1} is absent for {cohort}")


def sequencing_cohorts(cohort: str) -> tuple[str, ...]:
    """Return cohorts that must never overlap at the Step Functions level."""
    if cohort in {"residual", "residual-control"}:
        return ("residual", "residual-control")
    return (cohort,)


@contextmanager
def residual_launch_lock(
    cli: AwsCli, *, env: str, account: str
) -> Iterator[None]:
    """Serialize candidate/control check+start with a durable S3 lock.

    The object has no automatic expiry. A crashed operator leaves a safe,
    fail-closed lock that must be inspected and manually removed before a
    later residual launch.
    """
    bucket = f"edgartools-{env}-warehouse-{account}"
    key = "warehouse/release/ecs_sizing_ticket28.lock"
    payload = {
        "operator": f"ticket28:{os.getpid()}:{uuid.uuid4().hex}",
        "acquired_at": datetime.now(UTC).isoformat(),
    }
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", delete=False
        ) as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            path = Path(handle.name)
        created = cli.call(
            "s3api",
            "put-object",
            "--bucket",
            bucket,
            "--key",
            key,
            "--body",
            str(path),
            "--content-type",
            "application/json",
            "--if-none-match",
            "*",
        )
    except (OSError, RuntimeError) as exc:
        raise RuntimeError(
            f"could not acquire durable Ticket 28 launch lock s3://{bucket}/{key}; "
            f"another operator may be launching a residual canary, or a stale "
            f"lock needs manual review: {exc}"
        ) from exc
    finally:
        if path is not None:
            path.unlink(missing_ok=True)

    etag = created.get("ETag")
    if not etag:
        raise RuntimeError("durable Ticket 28 launch lock has no ETag")
    try:
        yield
    finally:
        try:
            cli.call(
                "s3api",
                "delete-object",
                "--bucket",
                bucket,
                "--key",
                key,
                "--if-match",
                str(etag),
            )
        except RuntimeError as exc:
            print(
                "WARNING: Ticket 28 execution launch completed, but its durable "
                f"lock could not be released; inspect s3://{bucket}/{key} before "
                f"another launch: {exc}",
                file=sys.stderr,
            )


def validate_task_definition_parity(
    source: dict[str, Any], candidate: dict[str, Any]
) -> None:
    """Prove the two task definitions differ only in tier identity/resources."""
    ignored = {
        "compatibilities",
        "cpu",
        "deregisteredAt",
        "family",
        "memory",
        "registeredAt",
        "registeredBy",
        "requiresAttributes",
        "revision",
        "status",
        "taskDefinitionArn",
    }

    def normalized(task_definition: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(task_definition)
        for key in ignored:
            result.pop(key, None)
        for container in result.get("containerDefinitions", []):
            options = (container.get("logConfiguration") or {}).get("options") or {}
            prefix = options.get("awslogs-stream-prefix")
            if prefix:
                base, separator, tier = prefix.rpartition("-")
                if separator and tier in {"small", "medium", "large"}:
                    options["awslogs-stream-prefix"] = f"{base}-<tier>"
        return result

    if normalized(source) != normalized(candidate):
        raise ValueError(
            "source and candidate task definitions differ beyond sizing and "
            "registration metadata"
        )


def validate_report_contract(
    execution: dict[str, Any],
    launch: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> None:
    """Bind a report to the immutable launch, expected states, tasks, and image."""
    if execution.get("executionArn") != launch.get("execution_arn"):
        raise ValueError("launch manifest execution ARN does not match report target")
    if execution.get("stateMachineArn") != launch.get("state_machine_arn"):
        raise ValueError("launch manifest state-machine ARN does not match execution")
    expected_states = set(launch.get("expected_task_states") or [])
    actual_states = {str(task["state"]) for task in tasks}
    if actual_states != expected_states:
        raise ValueError(
            f"executed task-state set mismatch: expected {sorted(expected_states)}, "
            f"found {sorted(actual_states)}"
        )
    task_contract = launch.get("task_definition_contract") or {}
    expected_image = launch.get("image")
    if not expected_image:
        raise ValueError("launch manifest is missing the immutable image identity")
    for task in tasks:
        state = task["state"]
        expected_task_definition = task_contract.get(state)
        if task.get("task_definition_arn") != expected_task_definition:
            raise ValueError(
                f"task definition mismatch for {state}: expected "
                f"{expected_task_definition}, found {task.get('task_definition_arn')}"
            )
        if task.get("image") != expected_image:
            raise ValueError(
                f"image mismatch for {state}: expected {expected_image}, "
                f"found {task.get('image')}"
            )


def _state_machine_arn(region: str, account: str, name: str) -> str:
    return f"arn:aws:states:{region}:{account}:stateMachine:{name}"


def _source_name(env: str, suffix: str) -> str:
    return f"edgartools-{env}-{suffix}"


def _family_name(env: str, suffix: str) -> str:
    return f"edgartools-{env}-{suffix}"


def _describe_task_definition(cli: AwsCli, family: str) -> dict[str, Any]:
    return cli.call("ecs", "describe-task-definition", "--task-definition", family)[
        "taskDefinition"
    ]


def _image_identity(task_definition: dict[str, Any]) -> str:
    containers = task_definition.get("containerDefinitions") or []
    if len(containers) != 1:
        raise RuntimeError("expected exactly one container in MDM task definition")
    image = containers[0].get("image") or ""
    if "@sha256:" not in image:
        raise RuntimeError(f"task definition image is not digest-pinned: {image}")
    return image


def _canary_state_names(
    definition: dict[str, Any], *, cohort: str, source_arn: str
) -> set[str]:
    config = CANARIES[cohort]
    return {
        name
        for name, task_arn in _task_states(definition).items()
        if name.startswith(config["state_prefix"]) and task_arn == source_arn
    }


def _definition_plan(
    cli: AwsCli, *, env: str, account: str, cohort: str
) -> dict[str, Any]:
    config = CANARIES[cohort]
    source_name = _source_name(env, config["source"])
    source_arn = _state_machine_arn(cli.region, account, source_name)
    source = cli.call(
        "stepfunctions", "describe-state-machine", "--state-machine-arn", source_arn
    )
    definition = json.loads(source["definition"])

    source_task = _describe_task_definition(
        cli, _family_name(env, config["source_family"])
    )
    candidate_task = _describe_task_definition(
        cli, _family_name(env, config["candidate_family"])
    )
    source_task_arn = source_task["taskDefinitionArn"]
    candidate_task_arn = candidate_task["taskDefinitionArn"]
    validate_task_definition_parity(source_task, candidate_task)
    if _image_identity(source_task) != _image_identity(candidate_task):
        raise RuntimeError(
            f"{cohort} source and candidate task definitions use different images"
        )

    state_names = _canary_state_names(
        definition, cohort=cohort, source_arn=source_task_arn
    )
    if len(state_names) not in config["expected_changes"]:
        raise RuntimeError(
            f"{cohort} expected one of {sorted(config['expected_changes'])} "
            "covered task-state counts, "
            f"found {len(state_names)}: {sorted(state_names)}"
        )
    rewritten, changes = rewrite_task_definitions(
        definition,
        state_names=state_names,
        source_arn=source_task_arn,
        candidate_arn=candidate_task_arn,
    )
    compatibility_overlays: list[str] = []
    added_unbounded_overlay = False
    if cohort == "sync":
        added_unbounded_overlay = (
            "mdm_sync_graph_HasUnboundedLimitOverride"
            not in rewritten.get("States", {})
        )
        rewritten = add_unbounded_sync_route(rewritten)
        if added_unbounded_overlay:
            compatibility_overlays.append(
                "limit=0 routes to sync-graph with no --limit flag"
            )
    elif cohort.startswith("residual"):
        rewritten, removed_legacy_cap = add_unbounded_residual_sync(rewritten)
        if removed_legacy_cap:
            compatibility_overlays.append(
                "legacy 200000 per-type graph cap removed before candidate verify"
            )
    canary_definition_hash = _json_hash(rewritten)
    canary_name = f"{config['name']}-{canary_definition_hash[:12]}"
    expected_task_states = (
        ["Ticket28RunUnboundedSync"]
        if added_unbounded_overlay
        else (
            ["mdm_sync_graph_RunMdmTaskUnbounded"]
            if cohort == "sync"
            else sorted(_task_states(rewritten))
        )
    )
    return {
        "cohort": cohort,
        "canary_name": canary_name,
        "source_state_machine_arn": source_arn,
        "source_definition_hash": _json_hash(definition),
        "canary_definition_hash": canary_definition_hash,
        "source_task_definition_arn": source_task_arn,
        "candidate_task_definition_arn": candidate_task_arn,
        "image": _image_identity(candidate_task),
        "covered_states": sorted(state_names),
        "changed_reference_count": changes,
        "compatibility_overlays": compatibility_overlays,
        "task_definition_contract": _task_states(rewritten),
        "expected_task_states": expected_task_states,
        "role_arn": source["roleArn"],
        "logging_configuration": source.get("loggingConfiguration") or {},
        "tracing_configuration": source.get("tracingConfiguration") or {},
        "definition": rewritten,
    }


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    omitted = {
        "role_arn",
        "logging_configuration",
        "tracing_configuration",
        "definition",
    }
    return {key: value for key, value in plan.items() if key not in omitted}


def _list_state_machines(cli: AwsCli) -> list[dict[str, Any]]:
    machines: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        args = ["stepfunctions", "list-state-machines", "--max-results", "1000"]
        if token:
            args += ["--next-token", token]
        page = cli.call(*args)
        machines.extend(page.get("stateMachines", []))
        token = page.get("nextToken")
        if not token:
            return machines


def _find_state_machine(cli: AwsCli, name: str) -> dict[str, Any] | None:
    return next(
        (machine for machine in _list_state_machines(cli) if machine["name"] == name),
        None,
    )


def _machine_executions(cli: AwsCli, machine_arn: str) -> list[dict[str, Any]]:
    executions: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        args = [
            "stepfunctions",
            "list-executions",
            "--state-machine-arn",
            machine_arn,
            "--max-results",
            "1000",
        ]
        if token:
            args += ["--next-token", token]
        page = cli.call(*args)
        executions.extend(page.get("executions", []))
        token = page.get("nextToken")
        if not token:
            return executions


def _cohort_executions(cli: AwsCli, cohort: str) -> list[dict[str, Any]]:
    prefix = CANARIES[cohort]["name"]
    executions: list[dict[str, Any]] = []
    for machine in _list_state_machines(cli):
        if machine["name"].startswith(prefix):
            executions.extend(_machine_executions(cli, machine["stateMachineArn"]))
    return executions


def _ensure_immutable_canary(cli: AwsCli, plan: dict[str, Any]) -> str:
    name = plan["canary_name"]
    existing = _find_state_machine(cli, name)
    args = [
        "--definition",
        json.dumps(plan["definition"], separators=(",", ":")),
        "--role-arn",
        plan["role_arn"],
        "--logging-configuration",
        json.dumps(plan["logging_configuration"], separators=(",", ":")),
        "--tracing-configuration",
        json.dumps(plan["tracing_configuration"], separators=(",", ":")),
    ]
    if existing:
        deployed = cli.call(
            "stepfunctions",
            "describe-state-machine",
            "--state-machine-arn",
            existing["stateMachineArn"],
        )
        deployed_hash = _json_hash(json.loads(deployed["definition"]))
        if deployed_hash != plan["canary_definition_hash"]:
            raise RuntimeError(
                f"immutable canary name collision for {name}: definition hash differs"
            )
        arn = existing["stateMachineArn"]
    else:
        result = cli.call(
            "stepfunctions",
            "create-state-machine",
            "--name",
            name,
            "--type",
            "STANDARD",
            *args,
            "--tags",
            "key=managed-by,value=ecs-sizing-canary",
            "key=ticket,value=28",
        )
        arn = result["stateMachineArn"]
    cli.call(
        "stepfunctions",
        "tag-resource",
        "--resource-arn",
        arn,
        "--tags",
        "key=managed-by,value=ecs-sizing-canary",
        "key=ticket,value=28",
    )
    return arn


def _account(cli: AwsCli) -> str:
    account = str(cli.call("sts", "get-caller-identity")["Account"])
    if account != EXPECTED_ACCOUNT:
        raise RuntimeError(
            f"refusing account {account}; Ticket 28 targets {EXPECTED_ACCOUNT}"
        )
    return account


def _write_json(path: Path | None, payload: Any) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        print(f"wrote {path}")
    else:
        print(rendered, end="")


def prepare(cli: AwsCli, args: argparse.Namespace) -> int:
    account = _account(cli)
    plans = [
        _definition_plan(cli, env=args.env, account=account, cohort=cohort)
        for cohort in sorted(CANARIES)
    ]
    result: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry-run",
        "account": account,
        "region": cli.region,
        "plans": [_public_plan(plan) for plan in plans],
    }
    if args.apply:
        result["state_machine_arns"] = {
            plan["cohort"]: _ensure_immutable_canary(cli, plan) for plan in plans
        }
    _write_json(args.output, result)
    return 0


def _cluster_name(env: str) -> str:
    return f"edgartools-{env}-{CLUSTER_BASENAME}"


def start(cli: AwsCli, args: argparse.Namespace) -> int:
    account = _account(cli)
    if args.attempt < 1:
        raise RuntimeError("--attempt must be at least 1")
    current_plan = _definition_plan(
        cli, env=args.env, account=account, cohort=args.cohort
    )
    machine = _find_state_machine(cli, current_plan["canary_name"])
    if not machine:
        raise RuntimeError("immutable canary is absent; run prepare --apply first")
    launch_guard = (
        residual_launch_lock(cli, env=args.env, account=account)
        if args.cohort in {"residual", "residual-control"}
        else nullcontext()
    )
    with launch_guard:
        sequence_executions = [
            execution
            for cohort in sequencing_cohorts(args.cohort)
            for execution in _cohort_executions(cli, cohort)
        ]
        validate_attempt_sequence(
            sequence_executions, cohort=args.cohort, attempt=args.attempt
        )
        cluster = _cluster_name(args.env)
        active_tasks: list[str] = []
        for desired_status in ("RUNNING", "PENDING"):
            active_tasks.extend(
                cli.call(
                    "ecs",
                    "list-tasks",
                    "--cluster",
                    cluster,
                    "--desired-status",
                    desired_status,
                ).get("taskArns", [])
            )
        if active_tasks and not args.allow_concurrent:
            raise RuntimeError(
                f"refusing concurrent canary: {len(set(active_tasks))} "
                f"running/pending task(s) already exist in {cluster}"
            )
        deployed = cli.call(
            "stepfunctions",
            "describe-state-machine",
            "--state-machine-arn",
            machine["stateMachineArn"],
        )
        deployed_hash = _json_hash(json.loads(deployed["definition"]))
        if deployed_hash != current_plan["canary_definition_hash"]:
            raise RuntimeError(
                "canary definition drifted from the current production source; "
                "rerun prepare --apply"
            )
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        name = f"ticket28-{args.cohort}-{args.attempt}-{timestamp}"
        started = cli.call(
            "stepfunctions",
            "start-execution",
            "--state-machine-arn",
            machine["stateMachineArn"],
            "--name",
            name,
            "--input",
            json.dumps(CANARIES[args.cohort]["input"], separators=(",", ":")),
        )
    launch_manifest = {
        **_public_plan(current_plan),
        "attempt": args.attempt,
        "execution_arn": started["executionArn"],
        "start_date": started["startDate"],
        "state_machine_arn": machine["stateMachineArn"],
    }
    _write_json(
        args.output,
        launch_manifest,
    )
    return 0


def _execution_history(cli: AwsCli, execution_arn: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        args = [
            "stepfunctions",
            "get-execution-history",
            "--execution-arn",
            execution_arn,
            "--max-results",
            "1000",
        ]
        if token:
            args += ["--next-token", token]
        page = cli.call(*args)
        events.extend(page.get("events", []))
        token = page.get("nextToken")
        if not token:
            return events


def _parse_datetime(value: str | float | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=UTC)
    return datetime.fromisoformat(value).astimezone(UTC)


def _normalize_terminal_task(task: dict[str, Any]) -> dict[str, Any]:
    """Normalize the retained Step Functions ECS payload to DescribeTasks shape."""
    containers = []
    for container in task.get("Containers") or task.get("containers") or []:
        containers.append(
            {
                "containerArn": container.get("ContainerArn")
                or container.get("containerArn"),
                "exitCode": container.get("ExitCode", container.get("exitCode")),
                "image": container.get("Image") or container.get("image"),
                "imageDigest": container.get("ImageDigest")
                or container.get("imageDigest"),
                "logStreamName": container.get("LogStreamName")
                or container.get("logStreamName"),
                "name": container.get("Name") or container.get("name"),
                "reason": container.get("Reason") or container.get("reason"),
            }
        )
    return {
        "taskArn": task.get("TaskArn") or task.get("taskArn"),
        "taskDefinitionArn": task.get("TaskDefinitionArn")
        or task.get("taskDefinitionArn"),
        "containers": containers,
        "createdAt": task.get("CreatedAt", task.get("createdAt")),
        "pullStartedAt": task.get("PullStartedAt", task.get("pullStartedAt")),
        "startedAt": task.get("StartedAt", task.get("startedAt")),
        "stoppedAt": task.get("StoppedAt", task.get("stoppedAt")),
        "stopCode": task.get("StopCode") or task.get("stopCode"),
        "stoppedReason": task.get("StoppedReason") or task.get("stoppedReason"),
    }


def _insights_rows(
    cli: AwsCli,
    *,
    cluster: str,
    task_id: str,
    start: datetime,
    end: datetime,
) -> list[dict]:
    for ingestion_attempt in range(3):
        query = (
            "fields @timestamp, CpuUtilized, MemoryUtilized "
            f"| filter Type = 'Task' and TaskId = '{task_id}' "
            "| sort @timestamp asc | limit 10000"
        )
        started = cli.call(
            "logs",
            "start-query",
            "--log-group-name",
            PERFORMANCE_LOG_GROUP.format(cluster=cluster),
            "--start-time",
            str(int((start - timedelta(minutes=5)).timestamp())),
            "--end-time",
            str(int((end + timedelta(minutes=5)).timestamp())),
            "--query-string",
            query,
        )
        query_id = started["queryId"]
        rows: list[dict[str, Any]] = []
        for _ in range(60):
            result = cli.call("logs", "get-query-results", "--query-id", query_id)
            if result["status"] == "Complete":
                for raw in result.get("results", []):
                    row = {field["field"]: field["value"] for field in raw}
                    if row.get("CpuUtilized") and row.get("MemoryUtilized"):
                        rows.append(
                            {
                                "timestamp": row.get("@timestamp"),
                                "cpu": float(row["CpuUtilized"]),
                                "memory": float(row["MemoryUtilized"]),
                            }
                        )
                break
            if result["status"] in {"Failed", "Cancelled", "Timeout"}:
                raise RuntimeError(
                    f"Container Insights query {query_id} {result['status']}"
                )
            time.sleep(1)
        else:
            raise RuntimeError(f"Container Insights query {query_id} did not complete")
        if any(row["cpu"] > 0 or row["memory"] > 0 for row in rows):
            return rows
        if ingestion_attempt < 2:
            time.sleep(10)
    return rows


def _task_log_documents(
    cli: AwsCli,
    *,
    log_group: str,
    log_stream: str | None,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    if not log_stream:
        return []
    # The high-volume MDM commands can emit millions of per-SQL events. The
    # command result and completion event are at the tail, so read a bounded
    # final page and discard SQL tracing rather than downloading the stream.
    page = cli.call(
        "logs",
        "get-log-events",
        "--log-group-name",
        log_group,
        "--log-stream-name",
        log_stream,
        "--start-time",
        str(int(start.timestamp() * 1000)),
        "--end-time",
        str(int((end + timedelta(minutes=1)).timestamp() * 1000)),
        "--limit",
        "1000",
        "--no-start-from-head",
    )
    documents = extract_json_documents(
        [event["message"] for event in page.get("events", [])]
    )
    return [
        document
        for document in documents
        if not str(document.get("event", "")).startswith("mdm_sql_")
    ]


def _describe_attempt(
    cli: AwsCli, *, cluster: str, attempt: dict[str, Any]
) -> dict[str, Any]:
    result = cli.call(
        "ecs", "describe-tasks", "--cluster", cluster, "--tasks", attempt["task_id"]
    )
    if result.get("tasks"):
        task = result["tasks"][0]
    elif attempt.get("task_snapshot"):
        task = _normalize_terminal_task(attempt["task_snapshot"])
        expected_task_id = attempt["task_id"]
        if (task.get("taskArn") or "").rsplit("/", 1)[-1] != expected_task_id:
            raise RuntimeError(
                f"retained ECS task identity does not match {expected_task_id}"
            )
    else:
        raise RuntimeError(
            f"ECS task {attempt['task_id']} is no longer describable; evidence fails closed"
        )
    task_definition = _describe_task_definition(cli, task["taskDefinitionArn"])
    container = (task.get("containers") or [{}])[0]
    task_container = (task_definition.get("containerDefinitions") or [{}])[0]
    created = _parse_datetime(task["createdAt"])
    stopped_raw = task.get("stoppedAt")
    stopped = _parse_datetime(stopped_raw) if stopped_raw else datetime.now(UTC)
    billable_duration_seconds = (
        (stopped - _parse_datetime(task["pullStartedAt"])).total_seconds()
        if stopped_raw and task.get("pullStartedAt")
        else None
    )
    usage = (
        fargate_usage(
            cpu_units=int(task_definition["cpu"]),
            memory_mib=int(task_definition["memory"]),
            pull_to_stop_seconds=billable_duration_seconds,
        )
        if billable_duration_seconds is not None
        else {
            "billed_duration_seconds": None,
            "requested_vcpu_hours": None,
            "requested_memory_gib_hours": None,
            "estimated_compute_cost_usd": None,
        }
    )
    samples = _insights_rows(
        cli,
        cluster=cluster,
        task_id=attempt["task_id"],
        start=created,
        end=stopped,
    )
    telemetry = None
    if samples:
        telemetry = summarize_utilization(
            samples,
            cpu_reserved=float(task_definition["cpu"]),
            memory_reserved=float(task_definition["memory"]),
        )
    log_stream = container.get("logStreamName")
    if not log_stream:
        log_options = (task_container.get("logConfiguration") or {}).get(
            "options"
        ) or {}
        log_prefix = log_options.get("awslogs-stream-prefix")
        container_name = task_container.get("name")
        if log_prefix and container_name:
            log_stream = f"{log_prefix}/{container_name}/{attempt['task_id']}"
    log_documents = _task_log_documents(
        cli,
        log_group=f"/aws/ecs/{cluster}",
        log_stream=log_stream,
        start=created,
        end=stopped,
    )
    enriched = {
        **{key: value for key, value in attempt.items() if key != "task_snapshot"},
        "task_arn": task["taskArn"],
        "task_definition_arn": task["taskDefinitionArn"],
        "image": _image_identity(task_definition),
        "cpu_reserved": int(task_definition["cpu"]),
        "memory_reserved_mib": int(task_definition["memory"]),
        "created_at": task["createdAt"],
        "pull_started_at": task.get("pullStartedAt"),
        "started_at": task.get("startedAt"),
        "stopped_at": stopped_raw,
        "billable_duration_seconds": billable_duration_seconds,
        **usage,
        "exit_code": container.get("exitCode"),
        "reason": container.get("reason"),
        "stop_code": task.get("stopCode"),
        "stopped_reason": task.get("stoppedReason"),
        "telemetry": telemetry,
        "application_evidence": log_documents,
    }
    return enriched


def report(cli: AwsCli, args: argparse.Namespace) -> int:
    _account(cli)
    try:
        launch = json.loads(args.launch_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read launch manifest: {exc}") from exc
    execution = cli.call(
        "stepfunctions",
        "describe-execution",
        "--execution-arn",
        args.execution_arn,
    )
    status = execution["status"]
    if status not in TERMINAL_STATUSES and not args.allow_running:
        raise RuntimeError(
            f"execution is {status}; use --allow-running for provisional data"
        )
    attempts = extract_task_attempts(_execution_history(cli, args.execution_arn))
    cluster = _cluster_name(args.env)
    tasks = [
        _describe_attempt(cli, cluster=cluster, attempt=attempt) for attempt in attempts
    ]
    validate_report_contract(execution, launch, tasks)
    gates = evaluate_execution(execution_status=status, tasks=tasks)
    start_date = _parse_datetime(execution["startDate"])
    stop_date = (
        _parse_datetime(execution["stopDate"])
        if execution.get("stopDate")
        else datetime.now(UTC)
    )
    evidence = {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "launch_contract": launch,
        "execution": {
            "arn": args.execution_arn,
            "name": execution["name"],
            "state_machine_arn": execution["stateMachineArn"],
            "status": status,
            "start_date": execution["startDate"],
            "stop_date": execution.get("stopDate"),
            "duration_seconds": (stop_date - start_date).total_seconds(),
        },
        "tasks": tasks,
        "fargate_pricing": {
            "operating_system": "Linux",
            "cpu_architecture": "x86_64",
            "region": cli.region,
            "vcpu_hour_usd": FARGATE_VCPU_HOUR_USD,
            "memory_gib_hour_usd": FARGATE_GIB_HOUR_USD,
            "additional_ephemeral_storage_gib": 0,
            "captured_at": FARGATE_PRICING_CAPTURED_AT,
            "source": FARGATE_PRICING_SOURCE,
        },
        "estimated_compute_cost_usd": sum(
            float(task.get("estimated_compute_cost_usd") or 0) for task in tasks
        ),
        "execution_local_gates": gates,
        "promotion_gates_not_inferred": [
            "representative non-zero input/output record funnel",
            "matched current-image large-profile duration baseline",
            "cost per successful validated output improvement of at least 10%",
            "cross-run cohort count",
        ],
    }
    _write_json(args.output, evidence)
    return 0 if gates["passed"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cli = AwsCli(args.profile, args.region)
    try:
        if args.command == "prepare":
            return prepare(cli, args)
        if args.command == "start":
            return start(cli, args)
        return report(cli, args)
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
