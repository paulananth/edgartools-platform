#!/usr/bin/env python3
"""Audit AWS cost and apply classified, year-based S3 artifact retention.

Examples:
  uv run python scripts/ops/aws_cost_optimizer.py --profile aws-admin-dev audit \
    --expected-account-id 690839588395 --output report.json

  uv run python scripts/ops/aws_cost_optimizer.py --profile aws-admin-dev retention-plan \
    --expected-account-id 690839588395 \
    --authority-jsonl retention-authority.jsonl --output retention-plan.json

  uv run python scripts/ops/aws_cost_optimizer.py --profile sec_platform_deployer retention-apply \
    --plan retention-plan.json \
    --plan-hash <sha256> --confirm-delete-expired-s3 --evidence-dir evidence/
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from edgar_warehouse.application.aws_cost_optimizer import (
    AccessionAuthority,
    AwsOperationGuard,
    CostPolicy,
    ObjectVersion,
    RetentionReference,
    build_cost_findings,
    build_s3_retention_plan,
    effective_retention_deadline,
    validate_s3_retention_plan_for_apply,
    verify_plan_hash,
)


class AwsCli:
    def __init__(self, *, profile: str | None, region: str) -> None:
        self.profile = profile
        self.region = region
        self.guard = AwsOperationGuard()

    def _base(self) -> list[str]:
        command = ["aws"]
        if self.profile:
            command.extend(["--profile", self.profile])
        command.extend(
            ["--region", self.region, "--no-cli-pager", "--no-paginate", "--output", "json"]
        )
        return command

    def read(self, service: str, operation: str, *arguments: str) -> dict[str, Any]:
        self.guard.require_read(service, operation)
        return self._run(service, operation, *arguments)

    def delete_versions(self, *, bucket: str, batch_file: Path) -> dict[str, Any]:
        self.guard.require_s3_delete("s3api", "delete-objects")
        return self._run(
            "s3api",
            "delete-objects",
            "--bucket",
            bucket,
            "--delete",
            f"file://{batch_file}",
        )

    def _run(self, service: str, operation: str, *arguments: str) -> dict[str, Any]:
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


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile")
    parser.add_argument("--region", default="us-east-1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="collect the weekly read-only AWS cost audit")
    audit.add_argument("--expected-account-id", required=True)
    audit.add_argument("--resource-prefix", default="edgartools-prod")
    audit.add_argument("--minimum-monthly-savings-usd", type=float, default=1.0)
    audit.add_argument("--drift-percent", type=float, default=20.0)
    audit.add_argument("--output", type=Path, required=True)

    plan = subparsers.add_parser(
        "retention-plan", help="inventory and plan exact expired S3 artifact versions"
    )
    plan.add_argument("--expected-account-id", required=True)
    plan.add_argument("--authority-jsonl", type=Path, required=True)
    plan.add_argument(
        "--as-of", type=date.fromisoformat, default=datetime.now(UTC).date()
    )
    plan.add_argument("--max-authorities", type=_positive_int, default=1000)
    plan.add_argument("--output", type=Path, required=True)

    apply = subparsers.add_parser(
        "retention-apply", help="revalidate and delete one reviewed exact-VersionId plan"
    )
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--plan-hash", required=True)
    apply.add_argument("--confirm-delete-expired-s3", action="store_true")
    apply.add_argument("--evidence-dir", type=Path, required=True)

    authority = subparsers.add_parser(
        "normalize-authority",
        help="normalize Snowflake JSON rows into the reviewed authority JSONL contract",
    )
    authority.add_argument("--snowflake-json", type=Path, required=True)
    authority.add_argument("--output", type=Path, required=True)
    return parser


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _previous_month(value: date) -> date:
    first = _month_start(value)
    return (first - timedelta(days=1)).replace(day=1)


def _service_costs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    periods: list[dict[str, Any]] = []
    for period in payload.get("ResultsByTime") or []:
        costs: dict[str, float] = {}
        for group in period.get("Groups") or []:
            keys = group.get("Keys") or []
            if not keys:
                continue
            amount = group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", "0")
            costs[str(keys[0])] = float(amount)
        periods.append(
            {
                "start": period.get("TimePeriod", {}).get("Start"),
                "end": period.get("TimePeriod", {}).get("End"),
                "estimated": bool(period.get("Estimated")),
                "services": costs,
            }
        )
    return periods


def _grouped_cost_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for period in payload.get("ResultsByTime") or []:
        for group in period.get("Groups") or []:
            keys = [str(key) for key in group.get("Keys") or []]
            amount = group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", "0")
            rows.append(
                {
                    "keys": keys,
                    "cost_usd": float(amount),
                    "period_start": period.get("TimePeriod", {}).get("Start"),
                    "period_end": period.get("TimePeriod", {}).get("End"),
                }
            )
    rows.sort(key=lambda row: float(row["cost_usd"]), reverse=True)
    return rows


def _optional(
    errors: list[dict[str, str]],
    label: str,
    call: Any,
) -> dict[str, Any]:
    try:
        return call()
    except RuntimeError as exc:
        errors.append({"source": label, "evidence_status": "insufficient_evidence", "detail": str(exc)})
        return {}


def require_account(cli: AwsCli, expected_account_id: str) -> dict[str, Any]:
    if not expected_account_id.isdigit() or len(expected_account_id) != 12:
        raise ValueError("expected_account_id must be exactly 12 digits")
    identity = cli.read("sts", "get-caller-identity")
    actual_account = str(identity.get("Account") or "")
    if actual_account != expected_account_id:
        raise RuntimeError(
            f"AWS account mismatch: expected {expected_account_id}, "
            f"resolved {actual_account or '<missing>'}"
        )
    return identity


def collect_audit(
    cli: AwsCli,
    *,
    expected_account_id: str,
    resource_prefix: str,
    policy: CostPolicy,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    identity = require_account(cli, expected_account_id)
    actual_account = str(identity["Account"])

    current_month = _month_start(today)
    previous = _previous_month(current_month)
    two_back = _previous_month(previous)
    cost_payload = cli.read(
        "ce",
        "get-cost-and-usage",
        "--time-period",
        f"Start={two_back.isoformat()},End={current_month.isoformat()}",
        "--granularity",
        "MONTHLY",
        "--metrics",
        "UnblendedCost",
        "--group-by",
        "Type=DIMENSION,Key=SERVICE",
    )
    periods = _service_costs(cost_payload)
    if len(periods) != 2:
        raise RuntimeError(f"required Cost Explorer query returned {len(periods)} closed months, expected 2")

    findings = build_cost_findings(
        previous_month=periods[0]["services"],
        latest_month=periods[1]["services"],
        policy=policy,
    )
    latest_start = str(periods[1]["start"])
    latest_end = str(periods[1]["end"])
    s3_breakdown = _grouped_cost_rows(
        cli.read(
            "ce",
            "get-cost-and-usage",
            "--time-period",
            f"Start={latest_start},End={latest_end}",
            "--granularity",
            "MONTHLY",
            "--metrics",
            "UnblendedCost",
            "--filter",
            json.dumps(
                {"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Simple Storage Service"]}},
                separators=(",", ":"),
            ),
            "--group-by",
            "Type=DIMENSION,Key=OPERATION",
        )
    )
    ecs_breakdown = _grouped_cost_rows(
        cli.read(
            "ce",
            "get-cost-and-usage",
            "--time-period",
            f"Start={latest_start},End={latest_end}",
            "--granularity",
            "MONTHLY",
            "--metrics",
            "UnblendedCost",
            "--filter",
            json.dumps(
                {"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Elastic Container Service"]}},
                separators=(",", ":"),
            ),
            "--group-by",
            "Type=DIMENSION,Key=USAGE_TYPE",
        )
    )
    errors: list[dict[str, str]] = []
    configuration_findings: list[dict[str, Any]] = []
    inventory: dict[str, Any] = {}

    buckets = _optional(errors, "s3:list-buckets", lambda: cli.read("s3api", "list-buckets"))
    bucket_rows: list[dict[str, Any]] = []
    for bucket in buckets.get("Buckets") or []:
        name = str(bucket.get("Name") or "")
        if not name.startswith(resource_prefix):
            continue
        row: dict[str, Any] = {"name": name, "created": bucket.get("CreationDate")}
        row["versioning"] = _optional(
            errors,
            f"s3:{name}:versioning",
            lambda name=name: cli.read("s3api", "get-bucket-versioning", "--bucket", name),
        )
        try:
            row["lifecycle"] = cli.read(
                "s3api", "get-bucket-lifecycle-configuration", "--bucket", name
            )
        except RuntimeError as exc:
            if "NoSuchLifecycleConfiguration" not in str(exc):
                errors.append(
                    {
                        "source": f"s3:{name}:lifecycle",
                        "evidence_status": "insufficient_evidence",
                        "detail": str(exc),
                    }
                )
                row["lifecycle"] = {}
            else:
                row["lifecycle"] = {"status": "absent", "Rules": []}
                configuration_findings.append(
                    {
                        "service": "Amazon Simple Storage Service",
                        "kind": "missing_lifecycle",
                        "resource": name,
                        "evidence_status": "safety_drift",
                    }
                )
        bucket_rows.append(row)
    inventory["s3_buckets"] = bucket_rows

    families = _optional(
        errors,
        "ecs:task-definition-families",
        lambda: cli.read(
            "ecs",
            "list-task-definition-families",
            "--family-prefix",
            resource_prefix,
            "--status",
            "ACTIVE",
            "--max-results",
            "100",
        ),
    )
    task_profiles: list[dict[str, Any]] = []
    for family in families.get("families") or []:
        definition = _optional(
            errors,
            f"ecs:{family}",
            lambda family=family: cli.read(
                "ecs", "describe-task-definition", "--task-definition", str(family)
            ),
        ).get("taskDefinition") or {}
        if definition:
            task_profiles.append(
                {
                    "family": definition.get("family"),
                    "revision": definition.get("revision"),
                    "cpu": definition.get("cpu"),
                    "memory": definition.get("memory"),
                    "ephemeral_storage_gib": (definition.get("ephemeralStorage") or {}).get("sizeInGiB", 20),
                    "evidence_status": "insufficient_evidence",
                    "note": "profile inventory only; rightsizing requires task-bound validated-output evidence",
                }
            )
    inventory["fargate_task_profiles"] = task_profiles

    inventory["log_groups"] = _optional(
        errors,
        "logs:describe-log-groups",
        lambda: cli.read("logs", "describe-log-groups", "--log-group-name-prefix", "/aws/"),
    ).get("logGroups", [])
    for group in inventory["log_groups"]:
        name = str(group.get("logGroupName") or "")
        retention = group.get("retentionInDays")
        if resource_prefix in name and (retention is None or int(retention) > 7):
            configuration_findings.append(
                {
                    "service": "AmazonCloudWatch",
                    "kind": "log_retention_drift",
                    "resource": name,
                    "observed_retention_days": retention,
                    "expected_max_days": 7,
                    "evidence_status": "safety_drift",
                }
            )
    inventory["ecr_repositories"] = _optional(
        errors, "ecr:describe-repositories", lambda: cli.read("ecr", "describe-repositories")
    ).get("repositories", [])
    inventory["secrets"] = _optional(
        errors, "secretsmanager:list-secrets", lambda: cli.read("secretsmanager", "list-secrets")
    ).get("SecretList", [])
    never_accessed_secrets = [
        str(secret.get("Name"))
        for secret in inventory["secrets"]
        if str(secret.get("Name") or "").startswith(resource_prefix)
        and not secret.get("LastAccessedDate")
    ]
    secrets_cost = float(
        periods[1]["services"].get("AWS Secrets Manager", 0.0)
    )
    if inventory["secrets"] and never_accessed_secrets:
        projected = secrets_cost * len(never_accessed_secrets) / len(inventory["secrets"])
        if projected >= policy.minimum_monthly_savings_usd:
            configuration_findings.append(
                {
                    "service": "AWS Secrets Manager",
                    "kind": "never_accessed_secret_review",
                    "resources": sorted(never_accessed_secrets),
                    "projected_monthly_savings_usd": round(projected, 2),
                    "evidence_status": "optimization_candidate",
                    "false_positive_notes": (
                        "LastAccessedDate is regional/date-resolution metadata; confirm task, "
                        "deployment, recovery, and compatibility references before deletion."
                    ),
                }
            )
    inventory["nat_gateways"] = _optional(
        errors, "ec2:describe-nat-gateways", lambda: cli.read("ec2", "describe-nat-gateways")
    ).get("NatGateways", [])
    inventory["vpc_endpoints"] = _optional(
        errors, "ec2:describe-vpc-endpoints", lambda: cli.read("ec2", "describe-vpc-endpoints")
    ).get("VpcEndpoints", [])
    inventory["elastic_ips"] = _optional(
        errors, "ec2:describe-addresses", lambda: cli.read("ec2", "describe-addresses")
    ).get("Addresses", [])
    inventory["kms_keys"] = _optional(
        errors, "kms:list-keys", lambda: cli.read("kms", "list-keys", "--limit", "100")
    ).get("Keys", [])
    inventory["state_machines"] = _optional(
        errors,
        "stepfunctions:list-state-machines",
        lambda: cli.read("stepfunctions", "list-state-machines", "--max-results", "100"),
    ).get("stateMachines", [])

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "account_id": actual_account,
        "region": cli.region,
        "resource_prefix": resource_prefix,
        "policy": {
            "minimum_monthly_savings_usd": policy.minimum_monthly_savings_usd,
            "drift_percent": policy.drift_percent,
        },
        "closed_months": periods,
        "findings": [finding.__dict__ for finding in findings],
        "configuration_findings": configuration_findings,
        "cost_breakdown": {
            "s3_by_operation": s3_breakdown,
            "fargate_by_usage_type": ecs_breakdown,
        },
        "inventory": inventory,
        "collection_gaps": errors,
    }


def load_authorities(path: Path) -> list[AccessionAuthority]:
    authorities: list[AccessionAuthority] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            raw_keys = row["object_keys"]
            if isinstance(raw_keys, str):
                raw_keys = json.loads(raw_keys)
            keys = tuple(str(value) for value in raw_keys)
            raw_references = row.get("retention_references") or []
            if not isinstance(raw_references, list):
                raise TypeError("retention_references must be an array")
            references = tuple(
                RetentionReference(
                    accession_number=str(reference["accession_number"]),
                    form=str(reference["form"] or ""),
                    filing_date=str(reference["filing_date"] or "")[:10],
                    item_502=_bool_value(reference.get("item_502", False), "item_502"),
                    retain_current=_bool_value(
                        reference.get("retain_current", False), "retain_current"
                    ),
                )
                for reference in raw_references
            )
            authorities.append(
                AccessionAuthority(
                    accession_number=str(row["accession_number"]),
                    form=str(row["form"]),
                    filing_date=date.fromisoformat(str(row["filing_date"])),
                    item_502=_bool_value(row.get("item_502", False), "item_502"),
                    retain_current=_bool_value(
                        row.get("retain_current", False), "retain_current"
                    ),
                    complete=_bool_value(row.get("complete", False), "complete"),
                    object_keys=keys,
                    retention_references=references,
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid authority row {line_number}: {exc}") from exc
    return authorities


def _bool_value(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError(f"{field} must be a boolean")


def normalize_snowflake_authority(source: Path, destination: Path) -> int:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError("Snowflake authority output must be a JSON array")
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(payload, start=1):
        if not isinstance(row, dict):
            raise TypeError(f"Snowflake authority row {index} is not an object")
        lowered = {str(key).lower(): value for key, value in row.items()}
        raw_keys = lowered.get("object_keys")
        if isinstance(raw_keys, str):
            raw_keys = json.loads(raw_keys)
        if not isinstance(raw_keys, list):
            raise TypeError(f"Snowflake authority row {index} has invalid OBJECT_KEYS")
        raw_references = lowered.get("retention_references") or []
        if isinstance(raw_references, str):
            raw_references = json.loads(raw_references)
        if not isinstance(raw_references, list):
            raise TypeError(
                f"Snowflake authority row {index} has invalid RETENTION_REFERENCES"
            )
        references = [
            {
                "accession_number": reference.get("accession_number")
                or reference.get("ACCESSION_NUMBER"),
                "form": reference.get("form") or reference.get("FORM") or "",
                "filing_date": str(
                    reference.get("filing_date") or reference.get("FILING_DATE") or ""
                )[:10],
                "item_502": _bool_value(
                    reference.get("item_502", reference.get("ITEM_502", False)),
                    "ITEM_502",
                ),
                "retain_current": _bool_value(
                    reference.get(
                        "retain_current", reference.get("RETAIN_CURRENT", False)
                    ),
                    "RETAIN_CURRENT",
                ),
            }
            for reference in raw_references
        ]
        references.sort(key=lambda reference: str(reference["accession_number"]))
        normalized.append(
            {
                "accession_number": lowered.get("accession_number"),
                "form": lowered.get("form"),
                "filing_date": str(lowered.get("filing_date") or "")[:10],
                "item_502": _bool_value(lowered.get("item_502", False), "ITEM_502"),
                "retain_current": _bool_value(
                    lowered.get("retain_current", False), "RETAIN_CURRENT"
                ),
                "complete": _bool_value(lowered.get("complete", False), "COMPLETE"),
                "object_keys": sorted({str(key) for key in raw_keys if key}),
                "retention_references": references,
            }
        )
    normalized.sort(key=lambda row: str(row["accession_number"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in normalized),
        encoding="utf-8",
    )
    load_authorities(destination)
    return len(normalized)


def _bucket_for_key(key: str, *, account_id: str) -> str:
    if not key.startswith("warehouse/bronze/"):
        raise ValueError(f"retention authority key is outside warehouse/bronze: {key}")
    return f"edgartools-prod-bronze-{account_id}"


def _normalize_versions(
    payload: Mapping[str, Any], *, bucket: str, prefix: str
) -> list[ObjectVersion]:
    if payload.get("IsTruncated"):
        raise RuntimeError(f"version inventory truncated for s3://{bucket}/{prefix}")
    versions: list[ObjectVersion] = []
    for kind, field in (("version", "Versions"), ("delete_marker", "DeleteMarkers")):
        for row in payload.get(field) or []:
            key = str(row.get("Key") or "")
            if not key.startswith(prefix):
                continue
            versions.append(
                ObjectVersion(
                    bucket=bucket,
                    key=key,
                    version_id=str(row.get("VersionId") or ""),
                    etag=str(row.get("ETag") or ""),
                    size_bytes=int(row.get("Size") or 0),
                    is_latest=bool(row.get("IsLatest")),
                    kind=kind,
                    storage_class=(
                        str(row.get("StorageClass") or "STANDARD")
                        if kind == "version"
                        else "NOT_APPLICABLE"
                    ),
                )
            )
    return versions


def _accession_prefix(key: str, accession_number: str) -> str:
    marker = f"accession={accession_number}/"
    before, found, _after = key.partition(marker)
    if not found:
        raise ValueError(f"object key does not contain accession {accession_number}: {key}")
    return f"{before}{marker}"


def collect_versions(
    cli: AwsCli,
    authorities: Iterable[AccessionAuthority],
    *,
    account_id: str,
) -> list[ObjectVersion]:
    versions: list[ObjectVersion] = []
    seen: set[tuple[str, str]] = set()
    for authority in authorities:
        for key in authority.object_keys:
            bucket = _bucket_for_key(key, account_id=account_id)
            prefix = _accession_prefix(key, authority.accession_number)
            identity = (bucket, prefix)
            if identity in seen:
                continue
            seen.add(identity)
            payload = cli.read(
                "s3api",
                "list-object-versions",
                "--bucket",
                bucket,
                "--prefix",
                prefix,
                "--max-keys",
                "1000",
            )
            versions.extend(_normalize_versions(payload, bucket=bucket, prefix=prefix))
    return versions


def select_expired_authorities(
    authorities: Iterable[AccessionAuthority],
    *,
    as_of: date,
    limit: int,
) -> list[AccessionAuthority]:
    rows = list(authorities)
    accession_counts = Counter(row.accession_number for row in rows)
    selected = [
        authority
        for authority in rows
        if accession_counts[authority.accession_number] == 1
        and effective_retention_deadline(authority) is not None
        and as_of > effective_retention_deadline(authority)
    ]
    selected.sort(
        key=lambda authority: (
            effective_retention_deadline(authority),
            authority.accession_number,
        )
    )
    return selected[:limit]


def _version_identity(
    version: ObjectVersion,
) -> tuple[str, str, str, str, str, int, bool, str]:
    return (
        version.bucket,
        version.key,
        version.version_id,
        version.kind,
        version.etag,
        version.size_bytes,
        version.is_latest,
        version.storage_class,
    )


def apply_retention_plan(
    cli: AwsCli,
    *,
    plan: Mapping[str, Any],
    expected_hash: str,
    evidence_dir: Path,
) -> dict[str, Any]:
    verify_plan_hash(plan, expected_hash)
    if plan.get("plan_hash") != expected_hash:
        raise ValueError("reviewed --plan-hash does not match plan.plan_hash")
    account_id = str(plan.get("expected_account_id") or "")
    require_account(cli, account_id)

    planned = list(validate_s3_retention_plan_for_apply(plan))
    prefix_groups: dict[tuple[str, str], list[ObjectVersion]] = defaultdict(list)
    for bundle in plan.get("bundles") or []:
        accession_number = str(bundle.get("accession_number") or "")
        for row in bundle.get("versions") or []:
            version = ObjectVersion(**row)
            prefix = _accession_prefix(version.key, accession_number)
            prefix_groups[(version.bucket, prefix)].append(version)
    current: list[ObjectVersion] = []
    for bucket, prefix in sorted(prefix_groups):
        payload = cli.read(
            "s3api",
            "list-object-versions",
            "--bucket",
            bucket,
            "--prefix",
            prefix,
            "--max-keys",
            "1000",
        )
        current.extend(_normalize_versions(payload, bucket=bucket, prefix=prefix))
    if {_version_identity(item) for item in current} != {
        _version_identity(item) for item in planned
    }:
        raise RuntimeError("S3 version state changed since planning; refusing deletion")

    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "reviewed-plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    by_bucket: dict[str, list[ObjectVersion]] = defaultdict(list)
    for version in planned:
        by_bucket[version.bucket].append(version)
    responses: list[dict[str, Any]] = []
    batch_number = 0
    for bucket, versions in sorted(by_bucket.items()):
        for start in range(0, len(versions), 1000):
            batch_number += 1
            batch = versions[start : start + 1000]
            payload = {
                "Objects": [
                    {"Key": item.key, "VersionId": item.version_id} for item in batch
                ],
                "Quiet": False,
            }
            batch_file = evidence_dir / f"delete-batch-{batch_number:04d}.json"
            batch_file.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            response = cli.delete_versions(bucket=bucket, batch_file=batch_file)
            if response.get("Errors"):
                raise RuntimeError(f"S3 returned deletion errors: {response['Errors']}")
            responses.append({"bucket": bucket, "response": response})

    remaining: list[ObjectVersion] = []
    for bucket, prefix in sorted(prefix_groups):
        payload = cli.read(
            "s3api",
            "list-object-versions",
            "--bucket",
            bucket,
            "--prefix",
            prefix,
            "--max-keys",
            "1000",
        )
        remaining.extend(_normalize_versions(payload, bucket=bucket, prefix=prefix))
    planned_ids = {(item.bucket, item.key, item.version_id) for item in planned}
    not_deleted = [
        item for item in remaining if (item.bucket, item.key, item.version_id) in planned_ids
    ]
    concurrent_versions = [
        item for item in remaining if (item.bucket, item.key, item.version_id) not in planned_ids
    ]
    result = {
        "plan_hash": expected_hash,
        "deleted_versions": len(planned),
        "deleted_bytes": sum(item.size_bytes for item in planned),
        "complete": not not_deleted and not concurrent_versions,
        "remaining_planned_versions": [item.__dict__ for item in not_deleted],
        "concurrent_versions": [item.__dict__ for item in concurrent_versions],
        "responses": responses,
    }
    (evidence_dir / "post-delete-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not_deleted:
        raise RuntimeError("post-delete verification found planned VersionIds still present")
    if concurrent_versions:
        raise RuntimeError(
            "post-delete verification found concurrent unplanned versions; exact planned "
            "versions were deleted but the accession prefix is not empty"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "normalize-authority":
        rows = normalize_snowflake_authority(args.snowflake_json, args.output)
        print(json.dumps({"output": str(args.output), "rows": rows}, sort_keys=True))
        return 0
    cli = AwsCli(profile=args.profile, region=args.region)
    if args.command == "audit":
        report = collect_audit(
            cli,
            expected_account_id=args.expected_account_id,
            resource_prefix=args.resource_prefix,
            policy=CostPolicy(
                minimum_monthly_savings_usd=args.minimum_monthly_savings_usd,
                drift_percent=args.drift_percent,
            ),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "findings": len(report["findings"]), "gaps": len(report["collection_gaps"])}, sort_keys=True))
        return 0
    if args.command == "retention-plan":
        require_account(cli, args.expected_account_id)
        current_date = datetime.now(UTC).date()
        if args.as_of > current_date:
            raise ValueError("--as-of cannot be in the future")
        authorities = load_authorities(args.authority_jsonl)
        expired = select_expired_authorities(
            authorities,
            as_of=args.as_of,
            limit=args.max_authorities,
        )
        versions = collect_versions(
            cli,
            expired,
            account_id=args.expected_account_id,
        )
        plan = build_s3_retention_plan(
            expired,
            versions,
            as_of=args.as_of,
            expected_account_id=args.expected_account_id,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "plan_hash": plan.plan_hash, "bundles": len(plan.bundles), "versions": plan.total_versions, "bytes": plan.total_bytes, "projected_standard_storage_savings_usd_month": plan.projected_standard_storage_savings_usd_month, "unmatched": len(plan.unmatched)}, sort_keys=True))
        return 0
    if not args.confirm_delete_expired_s3:
        raise SystemExit("retention-apply requires --confirm-delete-expired-s3")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = apply_retention_plan(
        cli,
        plan=plan,
        expected_hash=args.plan_hash,
        evidence_dir=args.evidence_dir,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
