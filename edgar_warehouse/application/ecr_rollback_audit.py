"""ECR Rollback Cleanup Audit (ops-cost-control ticket 05).

Pure reconciliation logic: given already-fetched AWS facts (ECR image
inventory, resolved mirror tags, active task definitions, Step Functions
task-definition references, live ECS tasks, ECS services) plus the durable
cohort registry (``ecr_rollback_registry``), compute which tagged final
images are safe to delete and which task-definition revisions are stale.

Like ``ecr_rollback_registry`` and ``release_evidence``, this module performs
no network I/O and reads no clock — every fact is supplied by the caller.
All AWS calls live in ``edgar_warehouse.scripts.ecr_rollback_cli``, which
gathers the raw facts, calls ``compute_plan``, and (for ``apply``) re-runs
the whole gather-and-compute cycle before trusting a plan hash.

This is deliberately conservative: any ambiguity is a reason to retain, not
delete. A hard-fail (``fail_closed_reasons`` non-empty) forces
``candidate_digests`` to empty regardless of what individual images looked
like, so a caller can never "partially" apply a plan that has any open
question.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from edgar_warehouse.application.ecr_rollback_registry import (
    ROLE_NAMES,
    SLOT_ORDER,
    expected_mirror_tags,
    protected_digests_from_registry,
    validate_registry,
)

SCHEMA_VERSION = 1
MINIMUM_VERIFIED_COHORTS = len(SLOT_ORDER)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ROLE_SHA_TAG_RE = re.compile(r"^(warehouse|mdm)-sha-[0-9a-f]{12}$")
_MOVING_POINTER_TAG_RE = re.compile(r"^(warehouse|mdm)-(dev|prod)$")
_DEPS_TAG_RE = re.compile(r"^(warehouse|mdm)-deps-")
_DIGEST_REF_RE = re.compile(r"@(sha256:[0-9a-f]{64})$")


def _parse_utc(value: object, label: str) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed


@dataclass(frozen=True)
class ImageDisposition:
    digest: str
    tags: tuple[str, ...]
    pushed_at: str
    size_bytes: int
    disposition: str  # "protected" | "candidate" | "lifecycle_managed" | "deps_out_of_scope"
    provenance: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "digest": self.digest,
            "tags": list(self.tags),
            "pushed_at": self.pushed_at,
            "size_bytes": self.size_bytes,
            "disposition": self.disposition,
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True)
class Plan:
    schema_version: int
    account_id: str
    region: str
    repository: str
    audit_started_at: str
    images: tuple[ImageDisposition, ...]
    stale_task_definition_arns: tuple[str, ...]
    candidate_digests: tuple[str, ...]
    estimated_reclaimed_bytes: int
    pagination_counts: dict
    errors: tuple[str, ...]
    fail_closed_reasons: tuple[str, ...]
    plan_sha256: str = field(default="")

    def to_dict(self) -> dict:
        body = {
            "schema_version": self.schema_version,
            "account_id": self.account_id,
            "region": self.region,
            "repository": self.repository,
            "audit_started_at": self.audit_started_at,
            "images": [image.to_dict() for image in self.images],
            "stale_task_definition_arns": list(self.stale_task_definition_arns),
            "candidate_digests": list(self.candidate_digests),
            "estimated_reclaimed_bytes": self.estimated_reclaimed_bytes,
            "pagination_counts": dict(self.pagination_counts),
            "errors": list(self.errors),
            "fail_closed_reasons": list(self.fail_closed_reasons),
        }
        return {**body, "plan_sha256": self.plan_sha256}


def _canonical_hash(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def is_appliable(plan: Plan) -> bool:
    """A plan may only be applied when it found zero errors and zero fail-closed reasons."""
    return not plan.errors and not plan.fail_closed_reasons


def compute_plan(
    *,
    registry: dict,
    account_id: str,
    region: str,
    repository: str,
    ecr_images: list[dict],
    mirror_tag_digests: dict[str, str | None],
    task_definitions: list[dict],
    workflow_task_definition_arns: dict[str, list[str]],
    ecs_services: list[dict],
    live_tasks: list[dict],
    audit_started_at: str,
    pagination_counts: dict,
    errors: list[str],
) -> Plan:
    """Compute a dry-run (or apply-verification) plan from already-fetched AWS facts.

    ``task_definitions`` must be every ``ACTIVE`` revision with the platform's
    family prefix, not only the latest per family — a stale-but-still-active
    older revision is exactly what must be caught before it can protect (or
    fail to protect) a digest incorrectly.
    """
    errors = list(errors)
    fail_closed_reasons: list[str] = list(errors)

    registry_findings = validate_registry(registry)
    fail_closed_reasons.extend(f"registry: {finding.message}" for finding in registry_findings)

    if registry.get("account_id") != account_id or registry.get("region") != region:
        fail_closed_reasons.append(
            f"registry identity ({registry.get('account_id')}/{registry.get('region')}) "
            f"does not match audit identity ({account_id}/{region})"
        )

    cohorts = registry.get("cohorts", []) if isinstance(registry.get("cohorts"), list) else []
    if len(cohorts) < MINIMUM_VERIFIED_COHORTS:
        fail_closed_reasons.append(
            f"only {len(cohorts)} verified cohort(s) exist (need {MINIMUM_VERIFIED_COHORTS}) — "
            "retain-all applies; no tagged image may be deleted until full rollback history exists"
        )

    expected_mirrors = expected_mirror_tags(registry) if not registry_findings else {}
    for tag, expected_digest in expected_mirrors.items():
        resolved = mirror_tag_digests.get(tag)
        if resolved != expected_digest:
            fail_closed_reasons.append(
                f"mirror tag {tag!r} resolves to {resolved!r}, expected {expected_digest!r} per registry"
            )

    if ecs_services:
        fail_closed_reasons.append(
            f"{len(ecs_services)} ECS service(s) found — this contract assumes none exist; "
            "audit does not know how to reconcile services/deployments/task sets"
        )

    protected_from_registry = protected_digests_from_registry(registry) if not registry_findings else {}
    protected: dict[str, list[str]] = {digest: list(provenance) for digest, provenance in protected_from_registry.items()}

    def _protect(digest: str | None, reason: str) -> None:
        if not digest:
            return
        protected.setdefault(digest, []).append(reason)

    # Seeded from the registry's own recorded task-definition ARNs -- these are
    # the rollback anchors and must never be treated as stale, even if nothing
    # else (a live task, a workflow definition) currently references them.
    # Deliberately NOT seeded from task_definitions' own ARNs: that list is the
    # universe of candidates to check for staleness, not a source of
    # protection -- every active task definition would trivially "reference
    # itself" otherwise, and staleness detection would never fire.
    referenced_task_definition_arns: set[str] = set()
    for cohort in registry.get("cohorts", []) if isinstance(registry.get("cohorts"), list) else []:
        for role in ROLE_NAMES:
            role_entry = cohort.get(role)
            if isinstance(role_entry, dict):
                for arn in role_entry.get("task_definition_arns") or []:
                    if isinstance(arn, str):
                        referenced_task_definition_arns.add(arn)

    for task_def in task_definitions:
        arn = task_def.get("arn")
        for image_ref in task_def.get("images", []):
            match = _DIGEST_REF_RE.search(str(image_ref))
            if not match:
                fail_closed_reasons.append(
                    f"task definition {arn!r} references a tag-pinned (not digest-pinned) "
                    f"image {image_ref!r} — cannot resolve unambiguously"
                )
                continue
            if repository not in str(image_ref):
                fail_closed_reasons.append(
                    f"task definition {arn!r} references an image outside the expected "
                    f"repository {repository!r}: {image_ref!r}"
                )
                continue
            _protect(match.group(1), f"active_task_definition:{arn}")

    for state_machine, arns in workflow_task_definition_arns.items():
        for arn in arns:
            referenced_task_definition_arns.add(arn)

    for task in live_tasks:
        task_arn = task.get("task_arn")
        for container in task.get("images", []):
            digest = container.get("image_digest")
            repo = container.get("repository")
            if not digest or not _DIGEST_RE.fullmatch(str(digest)):
                fail_closed_reasons.append(
                    f"live task {task_arn!r} has a container with no resolvable imageDigest"
                )
                continue
            if repo != repository:
                fail_closed_reasons.append(
                    f"live task {task_arn!r} references digest {digest!r} outside the "
                    f"expected repository {repository!r} (found in {repo!r})"
                )
                continue
            _protect(digest, f"live_task:{task_arn}")
        task_def_arn = task.get("task_definition_arn")
        if isinstance(task_def_arn, str):
            referenced_task_definition_arns.add(task_def_arn)

    audit_started_dt = _parse_utc(audit_started_at, "audit_started_at")
    if audit_started_dt is None:
        fail_closed_reasons.append(f"audit_started_at {audit_started_at!r} is not a valid UTC timestamp")

    dispositions: list[ImageDisposition] = []
    candidate_digests: list[str] = []
    estimated_reclaimed_bytes = 0

    for image in ecr_images:
        digest = image.get("digest")
        tags = tuple(image.get("tags") or [])
        pushed_at = image.get("pushed_at", "")
        size_bytes = int(image.get("size_bytes") or 0)

        if digest in protected:
            dispositions.append(
                ImageDisposition(digest, tags, pushed_at, size_bytes, "protected", tuple(protected[digest]))
            )
            continue
        if any(_MOVING_POINTER_TAG_RE.fullmatch(tag) for tag in tags):
            dispositions.append(
                ImageDisposition(digest, tags, pushed_at, size_bytes, "protected", ("moving_pointer_tag",))
            )
            continue
        if not tags:
            dispositions.append(ImageDisposition(digest, tags, pushed_at, size_bytes, "lifecycle_managed", ()))
            continue
        if any(_DEPS_TAG_RE.match(tag) for tag in tags):
            dispositions.append(ImageDisposition(digest, tags, pushed_at, size_bytes, "deps_out_of_scope", ()))
            continue
        if not all(_ROLE_SHA_TAG_RE.fullmatch(tag) for tag in tags):
            # Any tag shape this audit doesn't recognize is retained, not guessed at.
            dispositions.append(ImageDisposition(digest, tags, pushed_at, size_bytes, "protected", ("unrecognized_tag_shape",)))
            continue

        pushed_dt = _parse_utc(pushed_at, "pushed_at")
        if audit_started_dt is not None and (pushed_dt is None or pushed_dt > audit_started_dt):
            dispositions.append(ImageDisposition(digest, tags, pushed_at, size_bytes, "protected", ("pushed_after_audit_start",)))
            continue

        dispositions.append(ImageDisposition(digest, tags, pushed_at, size_bytes, "candidate", ()))
        candidate_digests.append(digest)
        estimated_reclaimed_bytes += size_bytes

    stale_task_definition_arns = tuple(
        sorted(
            arn
            for td in task_definitions
            if isinstance((arn := td.get("arn")), str) and arn not in referenced_task_definition_arns
        )
    )

    if fail_closed_reasons:
        candidate_digests = []
        estimated_reclaimed_bytes = 0

    body = {
        "schema_version": SCHEMA_VERSION,
        "account_id": account_id,
        "region": region,
        "repository": repository,
        "audit_started_at": audit_started_at,
        "images": [d.to_dict() for d in dispositions],
        "stale_task_definition_arns": list(stale_task_definition_arns),
        "candidate_digests": sorted(candidate_digests),
        "estimated_reclaimed_bytes": estimated_reclaimed_bytes,
        "pagination_counts": dict(pagination_counts),
        "errors": list(errors),
        "fail_closed_reasons": list(fail_closed_reasons),
    }
    plan_sha256 = _canonical_hash(body)

    return Plan(
        schema_version=SCHEMA_VERSION,
        account_id=account_id,
        region=region,
        repository=repository,
        audit_started_at=audit_started_at,
        images=tuple(dispositions),
        stale_task_definition_arns=stale_task_definition_arns,
        candidate_digests=tuple(sorted(candidate_digests)),
        estimated_reclaimed_bytes=estimated_reclaimed_bytes,
        pagination_counts=dict(pagination_counts),
        errors=tuple(errors),
        fail_closed_reasons=tuple(fail_closed_reasons),
        plan_sha256=plan_sha256,
    )
