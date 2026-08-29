"""CLI for ops-cost-control ticket 05: bounded ECR retention with rollback safety.

A thin argparse + boto3 wrapper over the pure logic in
``edgar_warehouse.application.ecr_rollback_registry`` (the durable cohort
registry) and ``edgar_warehouse.application.ecr_rollback_audit`` (protected-
digest reconciliation and plan computation). All AWS I/O, the wall clock, and
S3-based registry storage/locking live here; the two imported modules stay
pure and unit-testable without touching AWS.

Implements the hybrid contract from
``.scratch/ops-cost-control/research/safe-ecr-rollback-protection.md``,
adapted to the platform's single shared-repository ECR topology (ticket 04's
correction note): durable cohort registry -> ECR mirror tags -> fail-closed
ECS/Step-Functions/live-task reconciliation -> stale task-definition
retirement -> hash-bound dry-run/apply.

Subcommands:

``plan``
    Gather every AWS fact the audit needs, compute a dry-run plan, and print
    it (default) or write it to a file. Never mutates AWS state.

``check``
    Run the same read-only reconciliation as ``plan`` but return a non-zero
    exit status when drift or any other fail-closed condition is present, so
    deployment gates and operator automation can use it directly.

``apply``
    Re-gather every fact from scratch (never trusts a stale ``plan``
    in-process), recompute the plan, and refuse to proceed unless its hash
    matches ``--plan-hash`` exactly and the plan has zero errors/fail-closed
    reasons. Acquires a durable S3 lock, deregisters stale task definitions,
    confirms they report ``INACTIVE``, then deletes exactly the candidate
    digests the plan named.

``record-cohort``
    Append a newly verified deployment as the registry's 'current' cohort,
    shifting the prior 'current' to 'rollback-1' and 'rollback-1' to
    'rollback-2'. Requires explicit verification evidence — this is a
    deliberate manual/operator step, not something a deploy wires up
    automatically (a deploy has not yet been verified at the moment it
    completes).

``acquire-lock`` / ``release-lock``
    Coordinate deployment and cohort recording with cleanup. A deployment
    holds the same durable lock while new task definitions are temporarily an
    unreferenced release candidate, preventing cleanup from classifying them
    as stale during the sequential Step Functions update.

Example::

    uv run python -m edgar_warehouse.scripts.ecr_rollback_cli plan \\
      --region us-east-1 --account-id 690839588395 \\
      --repository edgartools-prod-images \\
      --registry-bucket edgartools-prod-warehouse-690839588395
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edgar_warehouse.application.ecr_rollback_audit import (
    Plan,
    compute_plan,
    is_appliable,
    post_deregistration_findings,
)
from edgar_warehouse.application.ecr_rollback_registry import (
    advance_registry,
    empty_registry,
    expected_mirror_tags,
    expected_protected_tags,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes

DEFAULT_REGISTRY_RELATIVE_PATH = "warehouse/release/ecr_rollback_registry.json"
DEFAULT_LOCK_RELATIVE_PATH = "warehouse/release/ecr_rollback_cleanup.lock"
FAMILY_PREFIX_SUFFIX = ""  # family prefix is the caller's --name-prefix as-is


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _utc_iso(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return ""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _storage(bucket: str) -> StorageLocation:
    return StorageLocation(f"s3://{bucket}")


# ---------------------------------------------------------------------------
# Registry storage (ETag-guarded, reusing the repo's existing staged/promote
# pattern -- see object_storage.py's write_staged_bytes/promote_staged, the
# same mechanism silver publication uses).
# ---------------------------------------------------------------------------


def load_registry(storage: StorageLocation, relative_path: str, *, account_id: str, region: str) -> tuple[dict, str | None]:
    version = storage.read_object_version(relative_path)
    if not version.exists:
        return empty_registry(account_id=account_id, region=region), None
    raw = read_bytes(storage.join(relative_path))
    return json.loads(raw), version.etag


def save_registry(storage: StorageLocation, relative_path: str, registry: dict, *, expected_etag: str | None) -> None:
    payload = json.dumps(registry, indent=2, sort_keys=True).encode("utf-8")
    staged = storage.write_staged_bytes(relative_path, payload)
    storage.promote_staged(staged, relative_path, expected_etag=expected_etag)


def acquire_lock(storage: StorageLocation, relative_path: str, *, operator: str) -> str:
    """Best-effort exclusive lock via S3 conditional create (IfNoneMatch: '*').

    A stale lock from a crashed prior run must be cleared by an operator
    (``release-lock`` subcommand) — this deliberately does not auto-expire,
    since silently reclaiming a lock during a live delete would be worse
    than a manual unblock.
    """
    token = uuid.uuid4().hex
    payload = json.dumps({"operator": operator, "acquired_at": _now_iso(), "token": token}, sort_keys=True).encode("utf-8")
    try:
        storage.write_immutable_bytes(relative_path, payload)
    except Exception as exc:  # write_immutable_bytes raises WarehouseRuntimeError on content mismatch
        raise RuntimeError(
            f"could not acquire ECR cleanup lock at {relative_path!r} — another apply may be in "
            f"progress, or a stale lock needs manual release: {exc}"
        ) from exc
    return token


def release_lock(
    storage: StorageLocation,
    relative_path: str,
    *,
    expected_token: str | None = None,
    force: bool = False,
) -> None:
    version = storage.read_object_version(relative_path)
    if not version.exists:
        if force:
            return
        raise RuntimeError(f"cleanup lock at {relative_path!r} no longer exists")
    if not version.etag:
        raise RuntimeError(f"cleanup lock at {relative_path!r} has no ETag; refusing to delete it")

    if not force:
        if not expected_token:
            raise RuntimeError("lock owner token is required unless --force is used")
        try:
            lock = json.loads(read_bytes(storage.join(relative_path)))
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as exc:
            raise RuntimeError(f"cleanup lock at {relative_path!r} is unreadable; refusing to delete it") from exc
        if lock.get("token") != expected_token:
            raise RuntimeError(
                f"cleanup lock ownership changed at {relative_path!r}; refusing to release another owner's lock"
            )

    storage.delete_object(relative_path, expected_etag=version.etag)


# ---------------------------------------------------------------------------
# AWS fact gathering
# ---------------------------------------------------------------------------


def verify_identity(sts_client: Any, *, expected_account_id: str) -> list[str]:
    errors: list[str] = []
    identity = sts_client.get_caller_identity()
    actual_account = identity.get("Account")
    if actual_account != expected_account_id:
        errors.append(f"caller account {actual_account!r} does not match expected {expected_account_id!r}")
    return errors


def verify_mutation_identity(sts_client: Any, *, expected_account_id: str) -> bool:
    errors = verify_identity(sts_client, expected_account_id=expected_account_id)
    if errors:
        print(
            "ABORT: AWS identity does not match the requested rollback-cleanup account:\n"
            + json.dumps(errors, indent=2),
            file=sys.stderr,
        )
        return False
    return True


def gather_ecr_images(ecr_client: Any, repository: str) -> tuple[list[dict], dict[str, int]]:
    images: list[dict] = []
    pages = 0
    paginator = ecr_client.get_paginator("describe_images")
    for page in paginator.paginate(repositoryName=repository):
        pages += 1
        for detail in page.get("imageDetails", []):
            images.append(
                {
                    "digest": detail.get("imageDigest"),
                    "tags": detail.get("imageTags") or [],
                    "pushed_at": _utc_iso(detail.get("imagePushedAt")),
                    "size_bytes": detail.get("imageSizeInBytes") or 0,
                }
            )
    return images, {"ecr_describe_images_pages": pages}


def resolve_tag_digests(ecr_client: Any, repository: str, tags: list[str]) -> dict[str, str | None]:
    resolved: dict[str, str | None] = {}
    for tag in tags:
        try:
            response = ecr_client.describe_images(repositoryName=repository, imageIds=[{"imageTag": tag}])
        except ecr_client.exceptions.ImageNotFoundException:
            resolved[tag] = None
            continue
        details = response.get("imageDetails") or []
        resolved[tag] = details[0]["imageDigest"] if details else None
    return resolved


def gather_task_definitions(ecs_client: Any, family_prefix: str) -> tuple[list[dict], dict[str, int]]:
    families: list[str] = []
    family_pages = 0
    family_paginator = ecs_client.get_paginator("list_task_definition_families")
    for page in family_paginator.paginate(familyPrefix=family_prefix, status="ACTIVE"):
        family_pages += 1
        families.extend(
            family
            for family in page.get("families", [])
            if family == family_prefix or family.startswith(f"{family_prefix}-")
        )

    arns: list[str] = []
    pages = 0
    paginator = ecs_client.get_paginator("list_task_definitions")
    for family in sorted(set(families)):
        for page in paginator.paginate(familyPrefix=family, status="ACTIVE"):
            pages += 1
            arns.extend(
                arn
                for arn in page.get("taskDefinitionArns", [])
                if arn.rsplit("/", 1)[-1].rsplit(":", 1)[0] == family
            )

    definitions: list[dict] = []
    for arn in arns:
        described = ecs_client.describe_task_definition(taskDefinition=arn)["taskDefinition"]
        images = [
            c["image"]
            for c in described.get("containerDefinitions", [])
            if isinstance(c.get("image"), str)
        ]
        definitions.append({"arn": described["taskDefinitionArn"], "images": images})
    return definitions, {
        "ecs_list_task_definition_families_pages": family_pages,
        "task_definition_families_matched": len(set(families)),
        "ecs_list_task_definitions_pages": pages,
        "task_definitions_described": len(arns),
    }


def _walk_task_definition_arns(
    node: Any,
    found: set[str],
    unresolved: set[str] | None = None,
) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("TaskDefinition", "TaskDefinition.$"):
                if isinstance(value, str) and value.startswith("arn:aws:ecs:"):
                    found.add(value)
                elif unresolved is not None:
                    unresolved.add(str(value))
            else:
                _walk_task_definition_arns(value, found, unresolved)
    elif isinstance(node, list):
        for item in node:
            _walk_task_definition_arns(item, found, unresolved)


def gather_workflow_task_definition_arns(
    sfn_client: Any,
    name_prefix: str,
) -> tuple[dict[str, list[str]], list[str], dict[str, int]]:
    machines: list[dict] = []
    pages = 0
    paginator = sfn_client.get_paginator("list_state_machines")
    for page in paginator.paginate():
        pages += 1
        machines.extend(m for m in page.get("stateMachines", []) if m.get("name", "").startswith(name_prefix))

    result: dict[str, list[str]] = {}
    errors: list[str] = []
    for machine in machines:
        described = sfn_client.describe_state_machine(stateMachineArn=machine["stateMachineArn"])
        definition = json.loads(described["definition"])
        found: set[str] = set()
        unresolved: set[str] = set()
        _walk_task_definition_arns(definition, found, unresolved)
        result[machine["name"]] = sorted(found)
        errors.extend(
            f"state machine {machine['name']!r} has unresolved TaskDefinition reference {json.dumps(value)}"
            for value in sorted(unresolved)
        )
    return (
        result,
        errors,
        {"sfn_list_state_machines_pages": pages, "state_machines_described": len(machines)},
    )


def gather_ecs_clusters_tasks(
    ecs_client: Any,
    cluster_name: str,
    repository: str,
) -> tuple[list[dict], list[dict], list[str], dict[str, int]]:
    discovered_cluster_arns: list[str] = []
    cluster_pages = 0
    for page in ecs_client.get_paginator("list_clusters").paginate():
        cluster_pages += 1
        discovered_cluster_arns.extend(page.get("clusterArns", []))

    expected_cluster_arns = [
        arn for arn in discovered_cluster_arns if arn.rsplit("/", 1)[-1] == cluster_name
    ]
    errors: list[str] = []
    if len(expected_cluster_arns) != 1:
        errors.append(
            f"expected exactly one ECS cluster named {cluster_name!r}, found {len(expected_cluster_arns)}"
        )

    cluster_arns = discovered_cluster_arns if len(expected_cluster_arns) == 1 else []
    name_prefix = cluster_name.removesuffix("-warehouse")

    live_tasks: list[dict] = []
    services: list[dict] = []
    task_pages = 0
    service_pages = 0
    described_batches = 0
    describe_failures = 0

    for cluster_arn in cluster_arns:
        for service_page in ecs_client.get_paginator("list_services").paginate(cluster=cluster_arn):
            service_pages += 1
            for service_arn in service_page.get("serviceArns", []):
                services.append({"cluster": cluster_arn, "service_arn": service_arn})

        task_arns: set[str] = set()
        for desired_status in ("RUNNING", "STOPPED"):
            for task_page in ecs_client.get_paginator("list_tasks").paginate(
                cluster=cluster_arn, desiredStatus=desired_status
            ):
                task_pages += 1
                task_arns.update(task_page.get("taskArns", []))

        task_arn_list = sorted(task_arns)
        for i in range(0, len(task_arn_list), 100):
            batch = task_arn_list[i : i + 100]
            if not batch:
                continue
            described_batches += 1
            described = ecs_client.describe_tasks(cluster=cluster_arn, tasks=batch)
            for failure in described.get("failures") or []:
                describe_failures += 1
                errors.append(
                    "ECS DescribeTasks failure for "
                    f"{failure.get('arn')!r}: {failure.get('reason', 'unknown reason')}"
                )
            for task in described.get("tasks", []):
                if task.get("lastStatus") in ("STOPPED", "DELETED"):
                    continue
                containers = []
                for container in task.get("containers", []):
                    image = container.get("image", "")
                    image_name = image.split("@", 1)[0].rsplit("/", 1)[-1]
                    image_repository = image_name.split(":", 1)[0] if image_name else None
                    containers.append(
                        {
                            "repository": image_repository,
                            "image_digest": container.get("imageDigest"),
                        }
                    )
                task_definition_family = str(task.get("taskDefinitionArn", "")).rsplit("/", 1)[-1].rsplit(":", 1)[0]
                is_platform_task = (
                    task_definition_family == name_prefix
                    or task_definition_family.startswith(f"{name_prefix}-")
                    or any(image["repository"] == repository for image in containers)
                )
                if not is_platform_task:
                    continue
                live_tasks.append(
                    {
                        "task_arn": task.get("taskArn"),
                        "task_definition_arn": task.get("taskDefinitionArn"),
                        "images": containers,
                    }
                )

    return (
        live_tasks,
        services,
        errors,
        {
            "ecs_list_clusters_pages": cluster_pages,
            "ecs_clusters_matched": len(expected_cluster_arns),
            "ecs_clusters_scanned": len(cluster_arns),
            "ecs_list_tasks_pages": task_pages,
            "ecs_list_services_pages": service_pages,
            "ecs_describe_tasks_batches": described_batches,
            "ecs_describe_tasks_failures": describe_failures,
        },
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_plan(
    *,
    ecr_client: Any,
    ecs_client: Any,
    sfn_client: Any,
    sts_client: Any,
    account_id: str,
    region: str,
    repository: str,
    name_prefix: str,
    registry: dict,
) -> Plan:
    audit_started_at = _now_iso()
    errors = list(verify_identity(sts_client, expected_account_id=account_id))

    ecr_images, ecr_counts = gather_ecr_images(ecr_client, repository)
    protected_tag_digests = resolve_tag_digests(
        ecr_client,
        repository,
        list(expected_protected_tags(registry).keys()),
    )
    task_definitions, td_counts = gather_task_definitions(ecs_client, name_prefix)
    workflow_arns, workflow_errors, sfn_counts = gather_workflow_task_definition_arns(
        sfn_client, name_prefix
    )
    errors.extend(workflow_errors)
    live_tasks, services, ecs_errors, ecs_counts = gather_ecs_clusters_tasks(
        ecs_client, f"{name_prefix}-warehouse", repository
    )
    errors.extend(ecs_errors)

    pagination_counts = {**ecr_counts, **td_counts, **sfn_counts, **ecs_counts}

    return compute_plan(
        registry=registry,
        account_id=account_id,
        region=region,
        repository=repository,
        ecr_images=ecr_images,
        protected_tag_digests=protected_tag_digests,
        task_definitions=task_definitions,
        workflow_task_definition_arns=workflow_arns,
        ecs_services=services,
        live_tasks=live_tasks,
        audit_started_at=audit_started_at,
        pagination_counts=pagination_counts,
        errors=errors,
    )


def _clients(region: str) -> tuple[Any, Any, Any, Any]:
    import boto3

    return (
        boto3.client("ecr", region_name=region),
        boto3.client("ecs", region_name=region),
        boto3.client("stepfunctions", region_name=region),
        boto3.client("sts", region_name=region),
    )


def _plan_from_args(args: argparse.Namespace) -> Plan:
    ecr_client, ecs_client, sfn_client, sts_client = _clients(args.region)
    storage = _storage(args.registry_bucket)
    registry, _etag = load_registry(
        storage, args.registry_path, account_id=args.account_id, region=args.region
    )
    return build_plan(
        ecr_client=ecr_client,
        ecs_client=ecs_client,
        sfn_client=sfn_client,
        sts_client=sts_client,
        account_id=args.account_id,
        region=args.region,
        repository=args.repository,
        name_prefix=args.name_prefix,
        registry=registry,
    )


def _emit_plan(plan: Plan, *, output_file: str | None) -> None:
    output = json.dumps(plan.to_dict(), indent=2, sort_keys=True)
    if output_file:
        Path(output_file).write_text(output + "\n", encoding="utf-8")
    print(output)
    print(f"\n==> plan_sha256={plan.plan_sha256}", file=sys.stderr)
    print(f"==> appliable={is_appliable(plan)}", file=sys.stderr)
    print(f"==> candidates={len(plan.candidate_digests)} estimated_reclaimed_bytes={plan.estimated_reclaimed_bytes}", file=sys.stderr)


def cmd_plan(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    _emit_plan(plan, output_file=args.output_file)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    plan = _plan_from_args(args)
    _emit_plan(plan, output_file=args.output_file)
    return 0 if is_appliable(plan) else 2


def cmd_apply(args: argparse.Namespace) -> int:
    ecr_client, ecs_client, sfn_client, sts_client = _clients(args.region)
    if not verify_mutation_identity(sts_client, expected_account_id=args.account_id):
        return 2
    storage = _storage(args.registry_bucket)

    lock_token = acquire_lock(storage, args.lock_path, operator=args.operator)
    try:
        registry, _etag = load_registry(
            storage, args.registry_path, account_id=args.account_id, region=args.region
        )
        plan = build_plan(
            ecr_client=ecr_client,
            ecs_client=ecs_client,
            sfn_client=sfn_client,
            sts_client=sts_client,
            account_id=args.account_id,
            region=args.region,
            repository=args.repository,
            name_prefix=args.name_prefix,
            registry=registry,
        )
        if plan.plan_sha256 != args.plan_hash:
            print(
                f"ABORT: recomputed plan hash {plan.plan_sha256!r} does not match "
                f"--plan-hash {args.plan_hash!r} — AWS state changed since the dry run "
                "was reviewed; re-run 'plan' and review again before retrying apply",
                file=sys.stderr,
            )
            return 2
        if not is_appliable(plan):
            print(
                "ABORT: plan has errors or fail-closed reasons; nothing will be deleted:\n"
                + json.dumps({"errors": plan.errors, "fail_closed_reasons": plan.fail_closed_reasons}, indent=2),
                file=sys.stderr,
            )
            return 2

        stale_arns = list(plan.stale_task_definition_arns)
        remaining_stale_arns = set(stale_arns)
        batch_size = args.task_definition_batch_size
        retirement_batches = [
            stale_arns[offset : offset + batch_size]
            for offset in range(0, len(stale_arns), batch_size)
        ] or [[]]
        for batch in retirement_batches:
            for arn in batch:
                ecs_client.deregister_task_definition(taskDefinition=arn)
            for arn in batch:
                described = ecs_client.describe_task_definition(taskDefinition=arn)["taskDefinition"]
                if described.get("status") != "INACTIVE":
                    print(
                        f"ABORT: task definition {arn!r} did not report INACTIVE after deregistration",
                        file=sys.stderr,
                    )
                    return 2
            remaining_stale_arns.difference_update(batch)

            post_deregistration_plan = build_plan(
                ecr_client=ecr_client,
                ecs_client=ecs_client,
                sfn_client=sfn_client,
                sts_client=sts_client,
                account_id=args.account_id,
                region=args.region,
                repository=args.repository,
                name_prefix=args.name_prefix,
                registry=registry,
            )
            post_findings = post_deregistration_findings(
                plan,
                post_deregistration_plan,
                expected_remaining_stale_task_definition_arns=tuple(remaining_stale_arns),
            )
            if post_findings:
                print(
                    "ABORT: repeated audit after task-definition retirement did not preserve "
                    "the reviewed deletion contract:\n" + json.dumps(post_findings, indent=2),
                    file=sys.stderr,
                )
                return 2

        deleted = 0
        candidates = list(plan.candidate_digests)
        for i in range(0, len(candidates), 100):
            batch = candidates[i : i + 100]
            response = ecr_client.batch_delete_image(
                repositoryName=args.repository,
                imageIds=[{"imageDigest": digest} for digest in batch],
            )
            successful = response.get("imageIds") or []
            deleted += len(successful)
            failures = response.get("failures") or []
            if failures:
                print(
                    f"ABORT: batch delete reported failures after {deleted} images deleted: {failures}",
                    file=sys.stderr,
                )
                return 2
            if len(successful) != len(batch):
                print(
                    "ABORT: batch delete did not account for every requested image: "
                    f"requested={len(batch)} deleted={len(successful)}",
                    file=sys.stderr,
                )
                return 2

        print(f"==> Deregistered {len(plan.stale_task_definition_arns)} stale task definition(s)")
        print(f"==> Deleted {deleted} image(s)")
        return 0
    finally:
        release_lock(storage, args.lock_path, expected_token=lock_token)


def cmd_record_cohort(args: argparse.Namespace) -> int:
    ecr_client, _ecs_client, _sfn_client, sts_client = _clients(args.region)
    if not verify_mutation_identity(sts_client, expected_account_id=args.account_id):
        return 2

    storage = _storage(args.registry_bucket)
    lock_token = acquire_lock(storage, args.lock_path, operator=args.operator)
    try:
        registry, etag = load_registry(
            storage, args.registry_path, account_id=args.account_id, region=args.region
        )
        updated = advance_registry(
            registry,
            candidate_id=args.candidate_id,
            verified_at=args.verified_at,
            verification_evidence=args.verification_evidence,
            warehouse={
                "repository": args.repository,
                "digest": args.warehouse_digest,
                "immutable_tag": args.warehouse_tag,
                "task_definition_arns": args.warehouse_task_definition_arns,
            },
            mdm={
                "repository": args.repository,
                "digest": args.mdm_digest,
                "immutable_tag": args.mdm_tag,
                "task_definition_arns": args.mdm_task_definition_arns,
            },
            updated_at=_now_iso(),
        )

        source_tags = {
            args.warehouse_tag: args.warehouse_digest,
            args.mdm_tag: args.mdm_digest,
        }
        resolved_source_tags = resolve_tag_digests(
            ecr_client,
            args.repository,
            list(source_tags),
        )
        source_tag_mismatches = [
            f"immutable source tag {tag!r} resolves to {resolved_source_tags.get(tag)!r}, "
            f"expected {digest!r}"
            for tag, digest in source_tags.items()
            if resolved_source_tags.get(tag) != digest
        ]
        if source_tag_mismatches:
            print(
                "ABORT: cohort source tags are missing or resolve to the wrong digest:\n"
                + json.dumps(source_tag_mismatches, indent=2),
                file=sys.stderr,
            )
            return 2

        for tag, digest in expected_mirror_tags(updated).items():
            response = ecr_client.batch_get_image(
                repositoryName=args.repository, imageIds=[{"imageDigest": digest}]
            )
            failures = response.get("failures") or []
            images = response.get("images") or []
            if failures or len(images) != 1 or not images[0].get("imageManifest"):
                raise RuntimeError(
                    f"could not resolve exactly one manifest for mirror tag {tag!r} "
                    f"and digest {digest!r}: failures={failures!r}, images={len(images)}"
                )
            image_manifest = images[0]["imageManifest"]
            ecr_client.put_image(
                repositoryName=args.repository,
                imageTag=tag,
                imageManifest=image_manifest,
            )

        # The registry is authoritative, so publish every fallible mirror tag
        # first and commit the ETag-guarded registry last. If a mirror update or
        # the final registry promotion fails, the next audit retains everything;
        # rerunning this command can safely converge from the old registry.
        save_registry(storage, args.registry_path, updated, expected_etag=etag)

        print(json.dumps(updated, indent=2, sort_keys=True))
        return 0
    finally:
        release_lock(storage, args.lock_path, expected_token=lock_token)


def cmd_acquire_lock(args: argparse.Namespace) -> int:
    _ecr_client, _ecs_client, _sfn_client, sts_client = _clients(args.region)
    if not verify_mutation_identity(sts_client, expected_account_id=args.account_id):
        return 2
    storage = _storage(args.registry_bucket)
    token = acquire_lock(storage, args.lock_path, operator=args.operator)
    print(token)
    return 0


def cmd_release_lock(args: argparse.Namespace) -> int:
    _ecr_client, _ecs_client, _sfn_client, sts_client = _clients(args.region)
    if not verify_mutation_identity(sts_client, expected_account_id=args.account_id):
        return 2
    storage = _storage(args.registry_bucket)
    release_lock(storage, args.lock_path, expected_token=args.token, force=args.force)
    print(f"==> Released lock at {args.lock_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ECR rollback cohort registry and bounded-retention cleanup")
    parser.add_argument("--region", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--name-prefix", required=True, help="ECS/Step Functions resource family prefix, e.g. edgartools-prod")
    parser.add_argument("--registry-bucket", required=True)
    parser.add_argument("--registry-path", default=DEFAULT_REGISTRY_RELATIVE_PATH)
    parser.add_argument("--lock-path", default=DEFAULT_LOCK_RELATIVE_PATH)

    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Compute and print a dry-run plan")
    plan_parser.add_argument("--output-file")
    plan_parser.set_defaults(handler=cmd_plan)

    check_parser = subparsers.add_parser(
        "check",
        help="Read-only drift gate; exits non-zero on any fail-closed condition",
    )
    check_parser.add_argument("--output-file")
    check_parser.set_defaults(handler=cmd_check)

    apply_parser = subparsers.add_parser("apply", help="Re-audit and apply a previously reviewed plan")
    apply_parser.add_argument("--plan-hash", required=True)
    apply_parser.add_argument("--operator", required=True)
    apply_parser.add_argument(
        "--task-definition-batch-size",
        type=_positive_int,
        default=100,
        help="Exact-ARN retirement batch size; a full audit runs after every batch (default: 100)",
    )
    apply_parser.set_defaults(handler=cmd_apply)

    record_parser = subparsers.add_parser("record-cohort", help="Advance the registry with a newly verified deployment")
    record_parser.add_argument("--operator", required=True)
    record_parser.add_argument("--candidate-id", required=True)
    record_parser.add_argument("--verified-at", required=True)
    record_parser.add_argument("--verification-evidence", required=True)
    record_parser.add_argument("--warehouse-digest", required=True)
    record_parser.add_argument("--warehouse-tag", required=True)
    record_parser.add_argument("--warehouse-task-definition-arns", required=True, nargs="+")
    record_parser.add_argument("--mdm-digest", required=True)
    record_parser.add_argument("--mdm-tag", required=True)
    record_parser.add_argument("--mdm-task-definition-arns", required=True, nargs="+")
    record_parser.set_defaults(handler=cmd_record_cohort)

    acquire_lock_parser = subparsers.add_parser(
        "acquire-lock",
        help="Acquire the durable deployment/cleanup coordination lock",
    )
    acquire_lock_parser.add_argument("--operator", required=True)
    acquire_lock_parser.set_defaults(handler=cmd_acquire_lock)

    release_lock_parser = subparsers.add_parser("release-lock", help="Release an owned lock, or manually clear a confirmed stale lock")
    release_mode = release_lock_parser.add_mutually_exclusive_group(required=True)
    release_mode.add_argument("--token", help="Owner token printed by acquire-lock")
    release_mode.add_argument(
        "--force",
        action="store_true",
        help="Clear a confirmed stale lock without its owner token",
    )
    release_lock_parser.set_defaults(handler=cmd_release_lock)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
