#!/usr/bin/env python3
"""Strict audit gate for the MDM Snowflake Postgres cutover."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit


class AuditFailure(RuntimeError):
    """Raised when the cutover audit detects an unsafe deployment state."""


@dataclass(frozen=True)
class DsnAudit:
    dsn: str
    masked: str
    host: str
    database: str
    sslmode: str


@dataclass(frozen=True)
class AuditConfig:
    environment: str
    aws_region: str
    aws_profile: str | None
    name_prefix: str
    manifest_path: Path
    secret_arn: str | None
    expected_host: str | None
    expected_host_suffix: str
    database: str
    resolve_dns: bool
    run_runtime_smoke: bool
    smoke_timeout_seconds: int


class AwsCli:
    def __init__(self, *, region: str, profile: str | None = None) -> None:
        self._region = region
        self._profile = profile

    def _base_command(self) -> list[str]:
        command = ["aws", "--region", self._region]
        if self._profile:
            command.extend(["--profile", self._profile])
        return command

    def json(self, *args: str) -> Any:
        completed = subprocess.run(
            [*self._base_command(), *args, "--output", "json"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if not completed.stdout.strip():
            return None
        return json.loads(completed.stdout)

    def text(self, *args: str) -> str:
        completed = subprocess.run(
            [*self._base_command(), *args, "--output", "text"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return completed.stdout.strip()


def mask_dsn(dsn: str) -> str:
    parts = urlsplit(dsn.strip())
    host = parts.hostname or ""
    netloc = host
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    if parts.username:
        netloc = f"{parts.username}:***@{netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def extract_dsn(secret_string: str) -> str:
    raw = secret_string.strip()
    if not raw:
        raise AuditFailure("MDM postgres_dsn secret is empty")
    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuditFailure("MDM postgres_dsn secret contains invalid JSON") from exc
        for key in ("dsn", "url", "MDM_DATABASE_URL"):
            value = payload.get(key)
            if value:
                return str(value)
        raise AuditFailure("MDM postgres_dsn secret JSON has no dsn/url/MDM_DATABASE_URL key")
    return raw


def validate_snowflake_postgres_dsn(
    secret_string: str,
    *,
    expected_host: str | None,
    expected_host_suffix: str,
    database: str,
    resolve_dns: bool,
    resolver: Any = socket.getaddrinfo,
) -> DsnAudit:
    dsn = extract_dsn(secret_string)
    parts = urlsplit(dsn)
    if parts.scheme not in {"postgresql", "postgres", "postgresql+psycopg2"}:
        raise AuditFailure("MDM_DATABASE_URL must use a PostgreSQL URL scheme")
    if not parts.hostname:
        raise AuditFailure("MDM_DATABASE_URL must include a host")
    if expected_host and parts.hostname != expected_host:
        raise AuditFailure(f"MDM_DATABASE_URL host {parts.hostname} does not match expected host {expected_host}")
    if not parts.hostname.endswith(expected_host_suffix):
        raise AuditFailure(f"MDM_DATABASE_URL host must end with {expected_host_suffix}; got {parts.hostname}")
    actual_database = parts.path.lstrip("/")
    if actual_database != database:
        raise AuditFailure(f"MDM_DATABASE_URL database must be {database}; got {actual_database or '<empty>'}")
    sslmode = parse_qs(parts.query).get("sslmode", [""])[0]
    if sslmode != "require":
        raise AuditFailure("MDM_DATABASE_URL must include sslmode=require")
    if resolve_dns:
        try:
            resolver(parts.hostname, parts.port or 5432)
        except OSError as exc:
            raise AuditFailure(f"MDM_DATABASE_URL host did not resolve: {parts.hostname}") from exc
    return DsnAudit(
        dsn=dsn,
        masked=mask_dsn(dsn),
        host=parts.hostname,
        database=actual_database,
        sslmode=sslmode,
    )


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AuditFailure(f"deployment manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_mdm_secret_arn(manifest: dict[str, Any]) -> str:
    try:
        arn = manifest["mdm"]["secrets"]["postgres_dsn"]
    except KeyError as exc:
        raise AuditFailure("deployment manifest has no mdm.secrets.postgres_dsn entry") from exc
    if not arn:
        raise AuditFailure("deployment manifest mdm.secrets.postgres_dsn is empty")
    return str(arn)


def manifest_task_definitions(manifest: dict[str, Any]) -> dict[str, str]:
    task_definitions = {
        key: value
        for key, value in manifest.get("task_definitions", {}).items()
        if value and key in {"small", "medium", "large", "mdm_small", "mdm_medium"}
    }
    missing = {"small", "medium", "large", "mdm_small", "mdm_medium"} - set(task_definitions)
    if missing:
        raise AuditFailure(f"deployment manifest is missing task definitions: {', '.join(sorted(missing))}")
    return {str(key): str(value) for key, value in task_definitions.items()}


def manifest_state_machines(manifest: dict[str, Any]) -> dict[str, str]:
    state_machines = {
        str(key): str(value)
        for key, value in manifest.get("state_machines", {}).items()
        if value
    }
    required = {"mdm_check_connectivity", "mdm_counts", "mdm_run"}
    missing = required - set(state_machines)
    if missing:
        raise AuditFailure(f"deployment manifest is missing required MDM state machines: {', '.join(sorted(missing))}")
    return state_machines


def task_definition_injects_secret(task_definition: dict[str, Any], expected_secret_arn: str) -> bool:
    for container in task_definition.get("containerDefinitions", []):
        for secret in container.get("secrets", []):
            if secret.get("name") == "MDM_DATABASE_URL" and secret.get("valueFrom") == expected_secret_arn:
                return True
    return False


def collect_task_definition_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "TaskDefinition" and isinstance(nested, str):
                refs.add(nested)
            else:
                refs.update(collect_task_definition_refs(nested))
    elif isinstance(value, list):
        for nested in value:
            refs.update(collect_task_definition_refs(nested))
    return refs


def first_network_config(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        config = value.get("NetworkConfiguration", {}).get("AwsvpcConfiguration")
        if isinstance(config, dict):
            return config
        for nested in value.values():
            found = first_network_config(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = first_network_config(nested)
            if found:
                return found
    return None


def assert_no_running_executions(aws: AwsCli, state_machines: dict[str, str]) -> None:
    running: list[str] = []
    for workflow, arn in sorted(state_machines.items()):
        response = aws.json(
            "stepfunctions",
            "list-executions",
            "--state-machine-arn",
            arn,
            "--status-filter",
            "RUNNING",
            "--max-results",
            "1",
        )
        if response.get("executions"):
            running.append(workflow)
    if running:
        raise AuditFailure(f"running Step Functions executions must finish before RDS removal: {', '.join(running)}")


def assert_task_definitions_inject_secret(aws: AwsCli, task_definitions: dict[str, str], secret_arn: str) -> None:
    missing: list[str] = []
    for profile, arn in sorted(task_definitions.items()):
        response = aws.json("ecs", "describe-task-definition", "--task-definition", arn)
        task_definition = response.get("taskDefinition", {})
        if not task_definition_injects_secret(task_definition, secret_arn):
            missing.append(f"{profile} ({arn})")
    if missing:
        raise AuditFailure("task definitions missing expected MDM_DATABASE_URL secret: " + ", ".join(missing))


def assert_state_machines_use_manifest_task_revisions(
    aws: AwsCli,
    state_machines: dict[str, str],
    allowed_task_definitions: set[str],
) -> dict[str, dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}
    stale: dict[str, set[str]] = {}
    for workflow, arn in sorted(state_machines.items()):
        response = aws.json("stepfunctions", "describe-state-machine", "--state-machine-arn", arn)
        definition = json.loads(response["definition"])
        definitions[workflow] = definition
        refs = collect_task_definition_refs(definition)
        invalid = refs - allowed_task_definitions
        if invalid:
            stale[workflow] = invalid
    if stale:
        details = "; ".join(f"{workflow}: {', '.join(sorted(refs))}" for workflow, refs in sorted(stale.items()))
        raise AuditFailure(f"state machines reference stale task definition revisions: {details}")
    return definitions


def start_execution_and_wait(
    aws: AwsCli,
    *,
    workflow: str,
    arn: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> None:
    name = f"mdm-sfpg-audit-{workflow.replace('_', '-')}-{int(time.time())}"[:80]
    response = aws.json(
        "stepfunctions",
        "start-execution",
        "--state-machine-arn",
        arn,
        "--name",
        name,
        "--input",
        json.dumps(payload),
    )
    execution_arn = response["executionArn"]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = aws.json("stepfunctions", "describe-execution", "--execution-arn", execution_arn).get("status")
        if status == "SUCCEEDED":
            return
        if status in {"FAILED", "TIMED_OUT", "ABORTED"}:
            raise AuditFailure(f"runtime smoke {workflow} ended with status {status}")
        time.sleep(10)
    raise AuditFailure(f"runtime smoke {workflow} did not finish within {timeout_seconds} seconds")


def run_warehouse_read_smoke(
    aws: AwsCli,
    *,
    manifest: dict[str, Any],
    task_definitions: dict[str, str],
    definitions: dict[str, dict[str, Any]],
    timeout_seconds: int,
) -> None:
    network = None
    for definition in definitions.values():
        network = first_network_config(definition)
        if network:
            break
    if not network:
        raise AuditFailure("could not derive ECS network configuration from deployed state machine definitions")

    awsvpc = {
        "subnets": network.get("Subnets", []),
        "securityGroups": network.get("SecurityGroups", []),
        "assignPublicIp": network.get("AssignPublicIp", "ENABLED"),
    }
    run_id = f"mdm-sfpg-audit-{int(time.time())}"
    response = aws.json(
        "ecs",
        "run-task",
        "--cluster",
        manifest["cluster"]["arn"],
        "--launch-type",
        "FARGATE",
        "--task-definition",
        task_definitions["medium"],
        "--network-configuration",
        json.dumps({"awsvpcConfiguration": awsvpc}),
        "--overrides",
        json.dumps({
            "containerOverrides": [{
                "name": "edgar-warehouse",
                "command": ["compute-windows", "--window-size", "1", "--run-id", run_id],
            }]
        }),
    )
    failures = response.get("failures") or []
    if failures:
        raise AuditFailure(f"warehouse tracked-CIK smoke failed to start: {failures}")
    task_arns = [task["taskArn"] for task in response.get("tasks", [])]
    if not task_arns:
        raise AuditFailure("warehouse tracked-CIK smoke returned no ECS tasks")
    aws.text("ecs", "wait", "tasks-stopped", "--cluster", manifest["cluster"]["arn"], "--tasks", *task_arns)
    described = aws.json("ecs", "describe-tasks", "--cluster", manifest["cluster"]["arn"], "--tasks", *task_arns)
    for task in described.get("tasks", []):
        for container in task.get("containers", []):
            if container.get("name") == "edgar-warehouse" and container.get("exitCode") != 0:
                raise AuditFailure(
                    "warehouse tracked-CIK smoke exited with "
                    f"{container.get('exitCode')} ({container.get('reason', 'no reason')})"
                )


def run_runtime_smokes(
    aws: AwsCli,
    *,
    manifest: dict[str, Any],
    state_machines: dict[str, str],
    task_definitions: dict[str, str],
    definitions: dict[str, dict[str, Any]],
    timeout_seconds: int,
) -> None:
    start_execution_and_wait(
        aws,
        workflow="mdm_check_connectivity",
        arn=state_machines["mdm_check_connectivity"],
        payload={"trigger": "cutover-audit", "workflow": "mdm_check_connectivity"},
        timeout_seconds=timeout_seconds,
    )
    start_execution_and_wait(
        aws,
        workflow="mdm_counts",
        arn=state_machines["mdm_counts"],
        payload={"trigger": "cutover-audit", "workflow": "mdm_counts"},
        timeout_seconds=timeout_seconds,
    )
    start_execution_and_wait(
        aws,
        workflow="mdm_run",
        arn=state_machines["mdm_run"],
        payload={"trigger": "cutover-audit", "workflow": "mdm_run", "limit": 1},
        timeout_seconds=timeout_seconds,
    )
    run_warehouse_read_smoke(
        aws,
        manifest=manifest,
        task_definitions=task_definitions,
        definitions=definitions,
        timeout_seconds=timeout_seconds,
    )


def run_audit(config: AuditConfig, aws: AwsCli) -> None:
    manifest = load_manifest(config.manifest_path)
    if manifest.get("mdm", {}).get("database_source") != "snowflake-postgres":
        raise AuditFailure("deployment manifest mdm.database_source must be snowflake-postgres")

    secret_arn = config.secret_arn or manifest_mdm_secret_arn(manifest)
    secret_string = aws.text(
        "secretsmanager",
        "get-secret-value",
        "--secret-id",
        secret_arn,
        "--query",
        "SecretString",
    )
    dsn_audit = validate_snowflake_postgres_dsn(
        secret_string,
        expected_host=config.expected_host,
        expected_host_suffix=config.expected_host_suffix,
        database=config.database,
        resolve_dns=config.resolve_dns,
    )
    print(f"PASS secret host/database/sslmode: {dsn_audit.masked}")

    state_machines = manifest_state_machines(manifest)
    task_definitions = manifest_task_definitions(manifest)

    assert_no_running_executions(aws, state_machines)
    print("PASS no running deployed Step Functions executions")

    assert_task_definitions_inject_secret(aws, task_definitions, secret_arn)
    print("PASS warehouse and MDM task definitions inject the expected MDM_DATABASE_URL secret")

    definitions = assert_state_machines_use_manifest_task_revisions(
        aws,
        state_machines,
        set(task_definitions.values()),
    )
    print("PASS deployed state machines reference current task definition revisions")

    if config.run_runtime_smoke:
        run_runtime_smokes(
            aws,
            manifest=manifest,
            state_machines=state_machines,
            task_definitions=task_definitions,
            definitions=definitions,
            timeout_seconds=config.smoke_timeout_seconds,
        )
        print("PASS runtime smokes completed")


def parse_args(argv: list[str]) -> AuditConfig:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=["dev", "prod"], required=True)
    parser.add_argument("--aws-profile")
    parser.add_argument("--aws-region", default="us-east-1")
    parser.add_argument("--name-prefix")
    parser.add_argument("--manifest")
    parser.add_argument("--secret-arn")
    parser.add_argument("--expected-host")
    parser.add_argument("--expected-host-suffix", default=".snowflake.app")
    parser.add_argument("--database", default="mdm")
    parser.add_argument("--skip-dns", action="store_true")
    parser.add_argument("--run-runtime-smoke", action="store_true")
    parser.add_argument("--smoke-timeout-seconds", type=int, default=1800)
    args = parser.parse_args(argv)
    name_prefix = args.name_prefix or f"edgartools-{args.env}"
    manifest = Path(args.manifest) if args.manifest else repo_root / "infra" / f"aws-{args.env}-application.json"
    return AuditConfig(
        environment=args.env,
        aws_region=args.aws_region,
        aws_profile=args.aws_profile,
        name_prefix=name_prefix,
        manifest_path=manifest,
        secret_arn=args.secret_arn,
        expected_host=args.expected_host,
        expected_host_suffix=args.expected_host_suffix,
        database=args.database,
        resolve_dns=not args.skip_dns,
        run_runtime_smoke=args.run_runtime_smoke,
        smoke_timeout_seconds=args.smoke_timeout_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv or sys.argv[1:])
    aws = AwsCli(region=config.aws_region, profile=config.aws_profile)
    try:
        run_audit(config, aws)
    except AuditFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"ERROR: aws cli failed: {stderr}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
