#!/usr/bin/env python3
"""Safely schedule deletion of explicitly retired EdgarTools AWS secrets.

The command is dry-run by default. Apply requires an exact secret allowlist,
the canonical AWS account, Terraform state reconciliation, empty secret
containers, no access history, and no live ECS or Step Functions references.

Example:
  uv run python scripts/ops/delete_unused_aws_secrets.py \
    --environment prod \
    --profile aws-admin-prod \
    --expected-account-id 690839588395 \
    --secret-id edgartools-prod-runner-credentials \
    --secret-id edgartools-prod/mdm/api_keys \
    --secret-id edgartools-prod/mdm/neo4j

Add both flags below only after reviewing the dry-run JSON:
  --apply --confirm-delete-unused-secrets
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RECOVERY_WINDOW_DAYS = 30
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RetirementPolicy:
    name_template: str
    terraform_address: str
    source_reference_token: str
    required_tag_key: str
    required_tag_value: str
    reason: str


RETIREMENT_POLICIES = (
    RetirementPolicy(
        name_template="edgartools-{environment}-runner-credentials",
        terraform_address="module.runtime.aws_secretsmanager_secret.runner_credentials",
        source_reference_token="runner-credentials",
        required_tag_key="Legacy",
        required_tag_value="runner-credentials",
        reason="Legacy empty container; AWS runtimes use service-assumed IAM roles.",
    ),
    RetirementPolicy(
        name_template="edgartools-{environment}/mdm/api_keys",
        terraform_address="module.runtime.aws_secretsmanager_secret.mdm_api_keys",
        source_reference_token="mdm/api_keys",
        required_tag_key="RuntimeSecret",
        required_tag_value="mdm-api-keys",
        reason="Deferred API consumer was never deployed and the container was never populated.",
    ),
    RetirementPolicy(
        name_template="edgartools-{environment}/mdm/neo4j",
        terraform_address="module.runtime.aws_secretsmanager_secret.mdm_neo4j",
        source_reference_token="mdm/neo4j",
        required_tag_key="RuntimeSecret",
        required_tag_value="mdm-neo4j",
        reason="External Neo4j was retired in favor of Snowflake-native graph storage.",
    ),
)


def approved_retirements(environment: str) -> dict[str, RetirementPolicy]:
    if not environment or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
        for character in environment
    ):
        raise ValueError(
            "environment must contain only lowercase letters, digits, and hyphens"
        )
    return {
        policy.name_template.format(environment=environment): policy
        for policy in RETIREMENT_POLICIES
    }


class AwsCli:
    def __init__(self, *, profile: str | None, region: str) -> None:
        self.profile = profile
        self.region = region

    def _base(self) -> list[str]:
        command = ["aws"]
        if self.profile:
            command.extend(["--profile", self.profile])
        command.extend(
            [
                "--region",
                self.region,
                "--no-cli-pager",
                "--output",
                "json",
            ]
        )
        return command

    def call(self, service: str, operation: str, *arguments: str) -> dict[str, Any]:
        result = subprocess.run(
            [*self._base(), service, operation, *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"aws {service} {operation} failed: {detail[:2000]}")
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def delete_secret(self, name: str) -> dict[str, Any]:
        return self.call(
            "secretsmanager",
            "delete-secret",
            "--secret-id",
            name,
            "--recovery-window-in-days",
            str(RECOVERY_WINDOW_DAYS),
        )


def _tags(metadata: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(tag.get("Key")): str(tag.get("Value"))
        for tag in metadata.get("Tags") or []
        if tag.get("Key") is not None and tag.get("Value") is not None
    }


def assess_candidate(
    *,
    name: str,
    environment: str,
    expected_account_id: str,
    region: str,
    metadata: Mapping[str, Any],
    versions: Sequence[Mapping[str, Any]],
    resource_policy: str | None,
    references: Sequence[str],
    repository_references: Sequence[str] = (),
) -> dict[str, Any]:
    approved = approved_retirements(environment)
    policy = approved.get(name)
    blockers: list[str] = []
    if policy is None:
        blockers.append("not_in_reviewed_allowlist")

    if str(metadata.get("Name") or "") != name:
        blockers.append("name_mismatch")

    arn = str(metadata.get("ARN") or "")
    arn_prefix = f"arn:aws:secretsmanager:{region}:{expected_account_id}:secret:{name}-"
    if not arn.startswith(arn_prefix):
        blockers.append("wrong_account_or_region")

    tags = _tags(metadata)
    if tags.get("Project") != "edgartools":
        blockers.append("missing_project_tag")
    if tags.get("Environment") != environment:
        blockers.append("missing_environment_tag")
    if policy and tags.get(policy.required_tag_key) != policy.required_tag_value:
        blockers.append("missing_retirement_tag")

    if metadata.get("DeletedDate"):
        blockers.append("already_scheduled_for_deletion")
    if metadata.get("LastAccessedDate"):
        blockers.append("has_access_history")
    if metadata.get("RotationEnabled"):
        blockers.append("rotation_enabled")
    if metadata.get("ReplicationStatus"):
        blockers.append("has_replica")
    if versions:
        blockers.append("has_secret_versions")
    if resource_policy:
        blockers.append("has_resource_policy")
    if references:
        blockers.append("has_live_reference")
    if repository_references:
        blockers.append("has_repository_reference")

    return {
        "name": name,
        "arn": arn,
        "eligible": not blockers,
        "blockers": sorted(set(blockers)),
        "references": sorted(set(references)),
        "repository_references": sorted(set(repository_references)),
        "reason": policy.reason if policy else None,
        "recovery_window_days": RECOVERY_WINDOW_DAYS,
    }


def require_apply_ready(plan: Sequence[Mapping[str, Any]], *, confirmed: bool) -> None:
    if not confirmed:
        raise RuntimeError(
            "apply requires --confirm-delete-unused-secrets confirmation"
        )
    ineligible = [str(item.get("name")) for item in plan if not item.get("eligible")]
    if ineligible:
        raise RuntimeError(
            f"refusing apply because candidates are ineligible: {', '.join(ineligible)}"
        )


def terraform_state_resources(terraform_root: Path, *, profile: str | None) -> set[str]:
    environment = os.environ.copy()
    if profile:
        environment["AWS_PROFILE"] = profile
    result = subprocess.run(
        ["terraform", f"-chdir={terraform_root}", "state", "list"],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            "could not inspect Terraform state; initialize the selected root and apply the "
            f"reviewed removed blocks first: {detail[:2000]}"
        )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def terraform_state_blockers(
    names: Iterable[str], environment: str, state_resources: set[str]
) -> dict[str, list[str]]:
    approved = approved_retirements(environment)
    return {
        name: ["still_managed_by_terraform"]
        for name in names
        if name in approved and approved[name].terraform_address in state_resources
    }


def repository_reference_blockers(
    names: Iterable[str], environment: str, repo_root: Path
) -> dict[str, list[str]]:
    approved = approved_retirements(environment)
    selected = {name: approved[name] for name in names if name in approved}
    references = {name: [] for name in selected}
    script_path = Path(__file__).resolve()
    for relative_root in ("scripts", "infra/scripts", "edgar_warehouse"):
        root = repo_root / relative_root
        if not root.exists():
            raise RuntimeError(f"repository reference root is missing: {root}")
        for path in root.rglob("*"):
            if not path.is_file() or path.resolve() == script_path:
                continue
            if path.suffix not in {".json", ".py", ".sh", ".toml", ".yaml", ".yml"}:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            for name, policy in selected.items():
                for line_number, line in enumerate(content.splitlines(), start=1):
                    if policy.source_reference_token in line:
                        references[name].append(
                            f"{path.relative_to(repo_root)}:{line_number}"
                        )
    return {name: values for name, values in references.items() if values}


def _value_references_secret(value: str, name: str) -> bool:
    return value == name or f":secret:{name}-" in value


def _task_definition_references(
    task_definition: Mapping[str, Any], selected_names: Sequence[str]
) -> dict[str, list[str]]:
    found = {name: [] for name in selected_names}
    arn = str(task_definition.get("taskDefinitionArn") or "<unknown-task-definition>")
    for container in task_definition.get("containerDefinitions") or []:
        container_name = str(container.get("name") or "<unknown-container>")
        for secret in container.get("secrets") or []:
            value_from = str(secret.get("valueFrom") or "")
            for name in selected_names:
                if _value_references_secret(value_from, name):
                    found[name].append(f"ecs:{arn}:{container_name}")
    return found


def collect_live_references(
    cli: AwsCli, *, environment: str, selected_names: Sequence[str]
) -> dict[str, list[str]]:
    references = {name: [] for name in selected_names}
    prefix = f"edgartools-{environment}"

    families = (
        cli.call(
            "ecs",
            "list-task-definition-families",
            "--status",
            "ACTIVE",
            "--family-prefix",
            prefix,
        ).get("families")
        or []
    )
    checked_task_definitions: set[str] = set()
    for family in families:
        task_definition = (
            cli.call(
                "ecs", "describe-task-definition", "--task-definition", str(family)
            ).get("taskDefinition")
            or {}
        )
        arn = str(task_definition.get("taskDefinitionArn") or "")
        if arn:
            checked_task_definitions.add(arn)
        found = _task_definition_references(task_definition, selected_names)
        for name, values in found.items():
            references[name].extend(values)

    cluster = f"{prefix}-warehouse"
    running_tasks = (
        cli.call(
            "ecs",
            "list-tasks",
            "--cluster",
            cluster,
            "--desired-status",
            "RUNNING",
        ).get("taskArns")
        or []
    )
    if running_tasks:
        described = cli.call(
            "ecs",
            "describe-tasks",
            "--cluster",
            cluster,
            "--tasks",
            *map(str, running_tasks),
        )
        for task in described.get("tasks") or []:
            task_definition_arn = str(task.get("taskDefinitionArn") or "")
            if (
                not task_definition_arn
                or task_definition_arn in checked_task_definitions
            ):
                continue
            definition = (
                cli.call(
                    "ecs",
                    "describe-task-definition",
                    "--task-definition",
                    task_definition_arn,
                ).get("taskDefinition")
                or {}
            )
            found = _task_definition_references(definition, selected_names)
            for name, values in found.items():
                references[name].extend(values)

    machines = (
        cli.call("stepfunctions", "list-state-machines").get("stateMachines") or []
    )
    for machine in machines:
        machine_name = str(machine.get("name") or "")
        if not machine_name.startswith(prefix):
            continue
        machine_arn = str(machine.get("stateMachineArn") or "")
        definition = str(
            cli.call(
                "stepfunctions",
                "describe-state-machine",
                "--state-machine-arn",
                machine_arn,
            ).get("definition")
            or ""
        )
        for name in selected_names:
            if name in definition:
                references[name].append(f"stepfunctions:{machine_arn}")

    return {name: sorted(set(values)) for name, values in references.items()}


def require_account(cli: AwsCli, expected_account_id: str) -> dict[str, Any]:
    if len(expected_account_id) != 12 or not expected_account_id.isdigit():
        raise ValueError("expected_account_id must be exactly 12 digits")
    identity = cli.call("sts", "get-caller-identity")
    actual = str(identity.get("Account") or "")
    if actual != expected_account_id:
        raise RuntimeError(
            f"AWS account mismatch: expected {expected_account_id}, resolved {actual or '<missing>'}"
        )
    return identity


def build_plan(
    cli: AwsCli,
    *,
    environment: str,
    expected_account_id: str,
    region: str,
    selected_names: Sequence[str],
    state_resources: set[str],
    repository_references: Mapping[str, Sequence[str]] | None = None,
) -> list[dict[str, Any]]:
    approved = approved_retirements(environment)
    if not selected_names:
        raise ValueError("at least one --secret-id is required")
    if len(set(selected_names)) != len(selected_names):
        raise ValueError("duplicate --secret-id values are not allowed")
    unknown = sorted(set(selected_names) - set(approved))
    if unknown:
        raise RuntimeError(
            f"secret is not in the reviewed allowlist: {', '.join(unknown)}"
        )

    require_account(cli, expected_account_id)
    references = collect_live_references(
        cli, environment=environment, selected_names=selected_names
    )
    state_blockers = terraform_state_blockers(
        selected_names, environment, state_resources
    )
    plan: list[dict[str, Any]] = []
    for name in selected_names:
        metadata = cli.call("secretsmanager", "describe-secret", "--secret-id", name)
        versions = (
            cli.call(
                "secretsmanager",
                "list-secret-version-ids",
                "--secret-id",
                name,
                "--include-deprecated",
            ).get("Versions")
            or []
        )
        resource_policy = cli.call(
            "secretsmanager", "get-resource-policy", "--secret-id", name
        ).get("ResourcePolicy")
        result = assess_candidate(
            name=name,
            environment=environment,
            expected_account_id=expected_account_id,
            region=region,
            metadata=metadata,
            versions=versions,
            resource_policy=str(resource_policy) if resource_policy else None,
            references=references.get(name, []),
            repository_references=(repository_references or {}).get(name, []),
        )
        result["blockers"] = sorted(
            set(result["blockers"] + state_blockers.get(name, []))
        )
        result["eligible"] = not result["blockers"]
        plan.append(result)
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--profile")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--expected-account-id", required=True)
    parser.add_argument(
        "--secret-id", action="append", dest="secret_ids", required=True
    )
    parser.add_argument(
        "--terraform-root",
        type=Path,
        help="initialized passive-infrastructure root; defaults to accounts/<environment>",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-delete-unused-secrets", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    terraform_root = args.terraform_root or (
        REPO_ROOT / "infra" / "terraform" / "accounts" / args.environment
    )
    cli = AwsCli(profile=args.profile, region=args.region)
    state = terraform_state_resources(terraform_root, profile=args.profile)
    source_references = repository_reference_blockers(
        args.secret_ids, args.environment, REPO_ROOT
    )
    plan = build_plan(
        cli,
        environment=args.environment,
        expected_account_id=args.expected_account_id,
        region=args.region,
        selected_names=args.secret_ids,
        state_resources=state,
        repository_references=source_references,
    )
    output: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry_run",
        "account_id": args.expected_account_id,
        "region": args.region,
        "environment": args.environment,
        "recovery_window_days": RECOVERY_WINDOW_DAYS,
        "candidates": plan,
    }
    if not args.apply:
        output["next_step"] = (
            "Reconcile Terraform state, resolve every blocker, then repeat with "
            "--apply --confirm-delete-unused-secrets."
        )
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if all(item["eligible"] for item in plan) else 2

    require_apply_ready(plan, confirmed=args.confirm_delete_unused_secrets)
    deleted: list[dict[str, Any]] = []
    for candidate in plan:
        name = str(candidate["name"])
        cli.delete_secret(name)
        verified = cli.call("secretsmanager", "describe-secret", "--secret-id", name)
        deleted_date = verified.get("DeletedDate")
        if not deleted_date:
            raise RuntimeError(
                f"post-delete verification failed for {name}: DeletedDate is absent"
            )
        deleted.append(
            {
                "name": name,
                "deleted_date": deleted_date,
                "restore_command": (
                    f"aws secretsmanager restore-secret --profile {args.profile or '<profile>'} "
                    f"--region {args.region} --secret-id {name}"
                ),
            }
        )
    output["deleted"] = deleted
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
