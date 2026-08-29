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
    expected_protected_tags,
    protected_digests_from_registry,
    validate_registry,
)

SCHEMA_VERSION = 2
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


def _repository_from_digest_ref(image_ref: object) -> str | None:
    value = str(image_ref)
    if "@" not in value:
        return None
    return value.rsplit("@", 1)[0].rsplit("/", 1)[-1]


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
    registry_sha256: str
    audit_started_at: str
    images: tuple[ImageDisposition, ...]
    stale_task_definition_arns: tuple[str, ...]
    candidate_digests: tuple[str, ...]
    estimated_reclaimed_bytes: int
    pagination_counts: dict
    reference_drift: tuple[str, ...]
    errors: tuple[str, ...]
    fail_closed_reasons: tuple[str, ...]
    plan_sha256: str = field(default="")

    def to_dict(self) -> dict:
        body = {
            "schema_version": self.schema_version,
            "account_id": self.account_id,
            "region": self.region,
            "repository": self.repository,
            "registry_sha256": self.registry_sha256,
            "audit_started_at": self.audit_started_at,
            "images": [image.to_dict() for image in self.images],
            "stale_task_definition_arns": list(self.stale_task_definition_arns),
            "candidate_digests": list(self.candidate_digests),
            "estimated_reclaimed_bytes": self.estimated_reclaimed_bytes,
            "pagination_counts": dict(self.pagination_counts),
            "reference_drift": list(self.reference_drift),
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


def post_deregistration_findings(
    reviewed_plan: Plan,
    current_plan: Plan,
    *,
    expected_remaining_stale_task_definition_arns: tuple[str, ...] = (),
) -> list[str]:
    """Validate the second read-only audit before any ECR image deletion.

    Deregistering the reviewed stale task definitions intentionally changes
    AWS state, so the original plan hash cannot remain identical. The safe
    invariant is narrower: identity is unchanged, the repeated audit is
    appliable, only the not-yet-processed stale batch remains, and every digest
    approved in the reviewed plan is still independently eligible for deletion.
    """
    findings: list[str] = []
    for field_name in ("account_id", "region", "repository", "registry_sha256"):
        reviewed_value = getattr(reviewed_plan, field_name)
        current_value = getattr(current_plan, field_name)
        if current_value != reviewed_value:
            findings.append(
                f"post-deregistration {field_name} changed from {reviewed_value!r} to {current_value!r}"
            )

    if not is_appliable(current_plan):
        findings.extend(
            f"post-deregistration audit is not appliable: {reason}"
            for reason in (*current_plan.errors, *current_plan.fail_closed_reasons)
        )

    expected_remaining = tuple(sorted(expected_remaining_stale_task_definition_arns))
    actual_remaining = tuple(sorted(current_plan.stale_task_definition_arns))
    if actual_remaining != expected_remaining:
        if not expected_remaining:
            findings.append(
                "post-deregistration audit still reports stale task definitions: "
                + ", ".join(actual_remaining)
            )
        else:
            findings.append(
                "post-deregistration stale task-definition set changed: expected "
                f"{list(expected_remaining)!r}, found {list(actual_remaining)!r}"
            )

    current_candidates = set(current_plan.candidate_digests)
    for digest in reviewed_plan.candidate_digests:
        if digest not in current_candidates:
            findings.append(
                f"reviewed deletion candidate {digest!r} is no longer eligible after task-definition retirement"
            )
    return findings


def compute_plan(
    *,
    registry: dict,
    account_id: str,
    region: str,
    repository: str,
    ecr_images: list[dict],
    protected_tag_digests: dict[str, str | None],
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
    reference_drift: list[str] = []

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

    for cohort in cohorts:
        if not isinstance(cohort, dict):
            continue
        for role in ROLE_NAMES:
            role_entry = cohort.get(role)
            if isinstance(role_entry, dict) and role_entry.get("repository") != repository:
                fail_closed_reasons.append(
                    f"registry {cohort.get('slot')!r} {role!r} cohort repository "
                    f"{role_entry.get('repository')!r} does not match audited repository {repository!r}"
                )

    expected_tags = expected_protected_tags(registry) if not registry_findings else {}
    for tag, expected_digest in expected_tags.items():
        resolved = protected_tag_digests.get(tag)
        if resolved != expected_digest:
            tag_kind = "mirror" if tag.startswith("retain-") else "immutable cohort"
            fail_closed_reasons.append(
                f"{tag_kind} tag {tag!r} resolves to {resolved!r}, "
                f"expected {expected_digest!r} per registry"
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
    registry_task_definition_arns: set[str] = set()
    for cohort in registry.get("cohorts", []) if isinstance(registry.get("cohorts"), list) else []:
        for role in ROLE_NAMES:
            role_entry = cohort.get(role)
            if isinstance(role_entry, dict):
                for arn in role_entry.get("task_definition_arns") or []:
                    if isinstance(arn, str):
                        referenced_task_definition_arns.add(arn)
                        registry_task_definition_arns.add(arn)

    registry_expected_task_definitions: list[tuple[str, str, str, str]] = []
    current_release_task_definitions: dict[str, tuple[str, str]] = {}
    current_cohort = next(
        (cohort for cohort in cohorts if isinstance(cohort, dict) and cohort.get("slot") == "current"),
        None,
    )
    if not registry_findings:
        for cohort in cohorts:
            if not isinstance(cohort, dict):
                continue
            slot = cohort.get("slot")
            for role in ROLE_NAMES:
                role_entry = cohort.get(role)
                if not isinstance(role_entry, dict):
                    continue
                cohort_digest = role_entry.get("digest")
                for arn in role_entry.get("task_definition_arns") or []:
                    if (
                        isinstance(slot, str)
                        and isinstance(arn, str)
                        and isinstance(cohort_digest, str)
                    ):
                        registry_expected_task_definitions.append(
                            (arn, slot, role, cohort_digest)
                        )
                        if slot == "current":
                            current_release_task_definitions[arn] = (
                                role,
                                cohort_digest,
                            )

    task_definitions_by_arn: dict[str, dict] = {}
    for task_def in task_definitions:
        arn = task_def.get("arn")
        if not isinstance(arn, str):
            reference_drift.append(f"active task-definition inventory contains an invalid ARN: {arn!r}")
            continue
        if arn in task_definitions_by_arn:
            reference_drift.append(f"active task-definition inventory contains duplicate ARN {arn!r}")
            continue
        task_definitions_by_arn[arn] = task_def

    for arn, slot, role, expected_digest in registry_expected_task_definitions:
        registry_task_def = task_definitions_by_arn.get(arn)
        if registry_task_def is None:
            reference_drift.append(
                f"registry {slot} task definition {arn!r} for role {role!r} is not ACTIVE"
            )
            continue
        actual_digests = {
            match.group(1)
            for image_ref in registry_task_def.get("images", [])
            if _repository_from_digest_ref(image_ref) == repository
            and (match := _DIGEST_REF_RE.search(str(image_ref)))
        }
        if actual_digests != {expected_digest}:
            digest_label = "release digest" if slot == "current" else "cohort digest"
            reference_drift.append(
                f"registry {slot} task definition {arn!r} for role {role!r} resolves to "
                f"{sorted(actual_digests)!r}, expected {digest_label} {expected_digest!r}"
            )

    for state_machine, arns in workflow_task_definition_arns.items():
        for arn in arns:
            referenced_task_definition_arns.add(arn)
            if arn not in task_definitions_by_arn:
                reference_drift.append(
                    f"state machine {state_machine!r} references {arn!r}, which cannot be resolved "
                    "in the ACTIVE task-definition inventory"
                )
            elif current_release_task_definitions and arn not in current_release_task_definitions:
                reference_drift.append(
                    f"state machine {state_machine!r} references {arn!r}, which is outside the "
                    "registry current release cohort"
                )

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
            if task_def_arn not in task_definitions_by_arn:
                reference_drift.append(
                    f"live task {task_arn!r} references task definition {task_def_arn!r}, "
                    "which cannot be resolved in the ACTIVE task-definition inventory"
                )
        else:
            reference_drift.append(
                f"live task {task_arn!r} has no resolvable task-definition ARN"
            )

    for arn in sorted(registry_task_definition_arns):
        if arn not in task_definitions_by_arn:
            reference_drift.append(
                f"rollback registry references task definition {arn!r}, which is not ACTIVE"
            )

    # Only protected references must resolve to the audited runtime repository.
    # An unreferenced definition is an exact-ARN retirement candidate; legacy
    # definitions may legitimately point at the pre-consolidation repository
    # and must not block their own reviewed deregistration.
    for arn in sorted(referenced_task_definition_arns):
        referenced_task_def = task_definitions_by_arn.get(arn)
        if referenced_task_def is None:
            continue
        image_refs = referenced_task_def.get("images", [])
        if not isinstance(image_refs, list) or not image_refs:
            reference_drift.append(
                f"protected task definition {arn!r} has no resolvable container image reference"
            )
            continue
        for image_ref in image_refs:
            match = _DIGEST_REF_RE.search(str(image_ref))
            if not match:
                fail_closed_reasons.append(
                    f"task definition {arn!r} references a tag-pinned (not digest-pinned) "
                    f"image {image_ref!r} — cannot resolve unambiguously"
                )
                continue
            if _repository_from_digest_ref(image_ref) != repository:
                fail_closed_reasons.append(
                    f"task definition {arn!r} references an image outside the expected "
                    f"repository {repository!r}: {image_ref!r}"
                )
                continue
            _protect(match.group(1), f"protected_task_definition:{arn}")

    reference_drift = sorted(set(reference_drift))
    fail_closed_reasons.extend(f"reference drift: {finding}" for finding in reference_drift)

    audit_started_dt = _parse_utc(audit_started_at, "audit_started_at")
    if audit_started_dt is None:
        fail_closed_reasons.append(f"audit_started_at {audit_started_at!r} is not a valid UTC timestamp")
    current_verified_dt = (
        _parse_utc(current_cohort.get("verified_at"), "current cohort verified_at")
        if current_cohort is not None
        else None
    )

    dispositions: list[ImageDisposition] = []
    candidate_digests: list[str] = []
    estimated_reclaimed_bytes = 0

    for image in ecr_images:
        raw_digest = image.get("digest")
        if not isinstance(raw_digest, str) or not _DIGEST_RE.fullmatch(raw_digest):
            fail_closed_reasons.append(
                f"ECR inventory contains an invalid image digest: {raw_digest!r}"
            )
            continue
        digest = raw_digest
        raw_tags = image.get("tags") or []
        tags = tuple(sorted(tag for tag in raw_tags if isinstance(tag, str)))
        if len(tags) != len(raw_tags):
            fail_closed_reasons.append(
                f"ECR image {digest!r} contains a non-string tag"
            )
        raw_pushed_at = image.get("pushed_at", "")
        pushed_at = raw_pushed_at if isinstance(raw_pushed_at, str) else ""
        size_bytes = int(image.get("size_bytes") or 0)

        if digest in protected:
            dispositions.append(
                ImageDisposition(
                    digest,
                    tags,
                    pushed_at,
                    size_bytes,
                    "protected",
                    tuple(sorted(set(protected[digest]))),
                )
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
        if current_verified_dt is not None and pushed_dt is not None and pushed_dt > current_verified_dt:
            dispositions.append(
                ImageDisposition(
                    digest,
                    tags,
                    pushed_at,
                    size_bytes,
                    "protected",
                    ("pushed_after_current_verified_cohort",),
                )
            )
            continue

        dispositions.append(ImageDisposition(digest, tags, pushed_at, size_bytes, "candidate", ()))
        candidate_digests.append(digest)
        estimated_reclaimed_bytes += size_bytes

    dispositions.sort(
        key=lambda disposition: (
            disposition.digest,
            disposition.tags,
            disposition.disposition,
            disposition.provenance,
        )
    )
    errors = sorted(set(errors))
    fail_closed_reasons = sorted(set(fail_closed_reasons))

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

    registry_sha256 = _canonical_hash(registry)
    body = {
        "schema_version": SCHEMA_VERSION,
        "account_id": account_id,
        "region": region,
        "repository": repository,
        "registry_sha256": registry_sha256,
        "audit_started_at": audit_started_at,
        "images": [d.to_dict() for d in dispositions],
        "stale_task_definition_arns": list(stale_task_definition_arns),
        "candidate_digests": sorted(candidate_digests),
        "estimated_reclaimed_bytes": estimated_reclaimed_bytes,
        "pagination_counts": dict(pagination_counts),
        "reference_drift": list(reference_drift),
        "errors": list(errors),
        "fail_closed_reasons": list(fail_closed_reasons),
    }
    # The reviewed plan hash binds AWS state and decisions, not the wall-clock
    # instant at which the same state was observed. ``apply`` deliberately
    # re-runs the audit; including audit_started_at made every recomputation
    # produce a different hash even when nothing in AWS changed.
    hash_body = {key: value for key, value in body.items() if key != "audit_started_at"}
    plan_sha256 = _canonical_hash(hash_body)

    return Plan(
        schema_version=SCHEMA_VERSION,
        account_id=account_id,
        region=region,
        repository=repository,
        registry_sha256=registry_sha256,
        audit_started_at=audit_started_at,
        images=tuple(dispositions),
        stale_task_definition_arns=stale_task_definition_arns,
        candidate_digests=tuple(sorted(candidate_digests)),
        estimated_reclaimed_bytes=estimated_reclaimed_bytes,
        pagination_counts=dict(pagination_counts),
        reference_drift=tuple(reference_drift),
        errors=tuple(errors),
        fail_closed_reasons=tuple(fail_closed_reasons),
        plan_sha256=plan_sha256,
    )
