"""ECR Rollback Cohort Registry (ops-cost-control ticket 05).

Pure logic for the durable deployment-cohort registry that anchors "current
production plus two verified rollbacks" for ECR image retention. Mirrors
``release_evidence.py``'s convention: this module never performs network I/O,
never queries AWS, and never reads the wall clock — every timestamp is
supplied by the caller. Loading/writing the registry to its durable S3
location, and gathering the AWS-side facts a cohort records, live in
``edgar_warehouse.scripts.ecr_rollback_cli``.

Adapted from the researched contract
(``.scratch/ops-cost-control/research/safe-ecr-rollback-protection.md``) to
this platform's *current* topology: one shared ECR repository
(``edgartools-<env>-images``) with role encoded in the tag prefix
(``warehouse-*``/``mdm-*``), not the two-repository split the original
research assumed (see ticket 04's correction note). A cohort is still a
warehouse/mdm *pair* — the two roles are never selected independently.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

SCHEMA_VERSION = 1

ROLE_NAMES = ("warehouse", "mdm")
SLOT_ORDER = ("current", "rollback-1", "rollback-2")

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ACCOUNT_ID_RE = re.compile(r"^\d{12}$")
_TASK_DEFINITION_ARN_RE = re.compile(
    r"^arn:aws:ecs:[a-z0-9-]+:\d{12}:task-definition/[A-Za-z0-9_-]+:\d+$"
)
_ROLE_TAG_PREFIX_RE = {
    "warehouse": re.compile(r"^warehouse-sha-[0-9a-f]{12}$"),
    "mdm": re.compile(r"^mdm-sha-[0-9a-f]{12}$"),
}


class RegistryError(Exception):
    """Base class for cohort-registry rejections."""


class InvalidCohortEntryError(RegistryError):
    """A role's cohort entry (digest, tag, or task-definition ARNs) is malformed."""


class NonMonotonicAdvanceError(RegistryError):
    """A new cohort's verified_at is not after the current cohort's."""


class AccountRegionMismatchError(RegistryError):
    """A new cohort targets a different account/region than the registry's own."""


def _parse_utc_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise RegistryError(f"{label} must be an ISO8601 UTC timestamp string")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise RegistryError(f"{label} must be an ISO8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise RegistryError(f"{label} must include an explicit UTC offset")
    return parsed


def build_cohort_role_entry(
    *,
    role: str,
    repository: str,
    digest: str,
    immutable_tag: str,
    task_definition_arns: list[str],
) -> dict:
    """Build and validate one role's (warehouse or mdm) entry within a cohort.

    Fails closed on any malformed field rather than silently accepting a
    partial or ambiguous entry — an unresolved digest/tag/ARN here is exactly
    the class of gap the registry exists to prevent.
    """
    if role not in ROLE_NAMES:
        raise InvalidCohortEntryError(f"role must be one of {ROLE_NAMES}, got {role!r}")
    if not isinstance(repository, str) or not repository.strip():
        raise InvalidCohortEntryError("repository must be a non-empty string")
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise InvalidCohortEntryError(
            f"{role} digest must be a bare 'sha256:<64 hex>' digest, got {digest!r}"
        )
    if not isinstance(immutable_tag, str) or not _ROLE_TAG_PREFIX_RE[role].fullmatch(immutable_tag):
        raise InvalidCohortEntryError(
            f"{role} immutable_tag must match '{role}-sha-<12 hex>', got {immutable_tag!r}"
        )
    if not isinstance(task_definition_arns, list) or not task_definition_arns:
        raise InvalidCohortEntryError(f"{role} task_definition_arns must be a non-empty list")
    for arn in task_definition_arns:
        if not isinstance(arn, str) or not _TASK_DEFINITION_ARN_RE.fullmatch(arn):
            raise InvalidCohortEntryError(f"{role} task_definition_arns contains an invalid ARN: {arn!r}")
    return {
        "repository": repository,
        "digest": digest,
        "immutable_tag": immutable_tag,
        "task_definition_arns": list(task_definition_arns),
    }


def empty_registry(*, account_id: str, region: str) -> dict:
    """Return a freshly initialized registry with no cohorts yet."""
    if not _ACCOUNT_ID_RE.fullmatch(account_id):
        raise RegistryError(f"account_id must be a 12-digit string, got {account_id!r}")
    if not isinstance(region, str) or not region.strip():
        raise RegistryError("region must be a non-empty string")
    return {
        "schema_version": SCHEMA_VERSION,
        "account_id": account_id,
        "region": region,
        "updated_at": None,
        "cohorts": [],
    }


def advance_registry(
    registry: dict,
    *,
    candidate_id: str,
    verified_at: str,
    verification_evidence: str,
    warehouse: dict,
    mdm: dict,
    updated_at: str,
) -> dict:
    """Return a NEW registry with ``warehouse``/``mdm`` promoted to slot 'current'.

    Never mutates ``registry``. The previous 'current' becomes 'rollback-1',
    the previous 'rollback-1' becomes 'rollback-2', and anything older is
    dropped — the registry only ever remembers the three most recently
    verified cohorts. Fails closed if the new cohort is not verified strictly
    after the existing 'current' cohort (cohorts are ordered by verification
    time, never by push time) or targets a different account/region.
    """
    if not isinstance(registry, dict):
        raise RegistryError("registry must be a JSON object")
    for label, value in (
        ("candidate_id", candidate_id),
        ("verification_evidence", verification_evidence),
    ):
        if not isinstance(value, str) or not value.strip():
            raise RegistryError(f"{label} must be a non-empty string")

    verified_dt = _parse_utc_timestamp(verified_at, "verified_at")
    _parse_utc_timestamp(updated_at, "updated_at")

    account_id = registry.get("account_id")
    region = registry.get("region")
    if not _ACCOUNT_ID_RE.fullmatch(str(account_id)):
        raise RegistryError("registry.account_id must already be a valid 12-digit account id")
    if not isinstance(region, str) or not region.strip():
        raise RegistryError("registry.region must already be set")

    existing_cohorts = registry.get("cohorts")
    if not isinstance(existing_cohorts, list):
        raise RegistryError("registry.cohorts must be a list")

    current = next((c for c in existing_cohorts if c.get("slot") == "current"), None)
    if current is not None:
        current_verified_dt = _parse_utc_timestamp(current.get("verified_at"), "current cohort verified_at")
        if verified_dt <= current_verified_dt:
            raise NonMonotonicAdvanceError(
                f"new cohort verified_at {verified_at!r} is not after the current "
                f"cohort's verified_at {current.get('verified_at')!r} — cohorts must "
                "advance in verification order, not push order"
            )

    new_cohort = {
        "slot": "current",
        "candidate_id": candidate_id,
        "verified_at": verified_at,
        "verification_evidence": verification_evidence,
        "warehouse": build_cohort_role_entry(role="warehouse", **warehouse),
        "mdm": build_cohort_role_entry(role="mdm", **mdm),
    }

    ordered_existing = [c for c in existing_cohorts if c.get("slot") in SLOT_ORDER]
    ordered_existing.sort(key=lambda c: SLOT_ORDER.index(c["slot"]))
    shifted = []
    for cohort, new_slot in zip(ordered_existing, SLOT_ORDER[1:]):
        shifted_cohort = copy.deepcopy(cohort)
        shifted_cohort["slot"] = new_slot
        shifted.append(shifted_cohort)
    # Anything already at rollback-2 (or beyond) falls off entirely — only the
    # three most recently verified cohorts are ever retained.
    shifted = shifted[: len(SLOT_ORDER) - 1]

    return {
        "schema_version": SCHEMA_VERSION,
        "account_id": account_id,
        "region": region,
        "updated_at": updated_at,
        "cohorts": [new_cohort, *shifted],
    }


@dataclass(frozen=True)
class RegistryValidationFinding:
    code: str
    message: str


def validate_registry(registry: object) -> list[RegistryValidationFinding]:
    """Return validation findings; an empty list means the registry is valid."""
    findings: list[RegistryValidationFinding] = []
    if not isinstance(registry, dict):
        return [RegistryValidationFinding("invalid_type", "registry must be a JSON object")]

    if registry.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            RegistryValidationFinding(
                "invalid_schema_version",
                f"schema_version must be {SCHEMA_VERSION}, got {registry.get('schema_version')!r}",
            )
        )
    account_id = registry.get("account_id")
    if not isinstance(account_id, str) or not _ACCOUNT_ID_RE.fullmatch(account_id):
        findings.append(RegistryValidationFinding("invalid_account_id", "account_id must be a 12-digit string"))
    region = registry.get("region")
    if not isinstance(region, str) or not region.strip():
        findings.append(RegistryValidationFinding("invalid_region", "region must be a non-empty string"))

    cohorts = registry.get("cohorts")
    if not isinstance(cohorts, list):
        findings.append(RegistryValidationFinding("invalid_cohorts", "cohorts must be a list"))
        return findings

    seen_slots: set[str] = set()
    previous_verified_dt: datetime | None = None
    for cohort in cohorts:
        if not isinstance(cohort, dict):
            findings.append(RegistryValidationFinding("invalid_cohort", "each cohort must be a JSON object"))
            continue
        slot = cohort.get("slot")
        if slot not in SLOT_ORDER:
            findings.append(RegistryValidationFinding("invalid_slot", f"cohort slot must be one of {SLOT_ORDER}, got {slot!r}"))
        elif slot in seen_slots:
            findings.append(RegistryValidationFinding("duplicate_slot", f"slot {slot!r} appears more than once"))
        else:
            seen_slots.add(slot)

        for label in ("candidate_id", "verification_evidence"):
            if not isinstance(cohort.get(label), str) or not cohort[label].strip():
                findings.append(RegistryValidationFinding("invalid_cohort_field", f"cohort.{label} must be a non-empty string"))

        try:
            verified_dt = _parse_utc_timestamp(cohort.get("verified_at"), "cohort.verified_at")
            if previous_verified_dt is not None and verified_dt >= previous_verified_dt:
                findings.append(
                    RegistryValidationFinding(
                        "non_monotonic_cohort_order",
                        "cohorts must be strictly decreasing in verified_at from current to rollback-2",
                    )
                )
            previous_verified_dt = verified_dt
        except RegistryError as exc:
            findings.append(RegistryValidationFinding("invalid_timestamp", str(exc)))

        for role in ROLE_NAMES:
            role_entry = cohort.get(role)
            if not isinstance(role_entry, dict):
                findings.append(RegistryValidationFinding("missing_role_entry", f"cohort is missing a {role} entry"))
                continue
            try:
                build_cohort_role_entry(role=role, **role_entry)
            except (InvalidCohortEntryError, TypeError) as exc:
                findings.append(RegistryValidationFinding("invalid_role_entry", f"cohort.{role}: {exc}"))

    if len(cohorts) < len(SLOT_ORDER):
        findings.append(
            RegistryValidationFinding(
                "insufficient_history",
                f"fewer than {len(SLOT_ORDER)} verified cohorts exist "
                "(retain-all applies; see ecr_rollback_audit's fail-closed handling)",
            )
        )

    return findings


def protected_digests_from_registry(registry: dict) -> dict[str, list[str]]:
    """Return ``{digest: [provenance, ...]}`` for every role/slot in ``registry``.

    Distinct cohorts may legitimately share a digest for one role (e.g. a
    deploy that only rebuilt the other role's image) — provenance lists every
    slot/role that protects a shared digest rather than collapsing them.
    """
    protected: dict[str, list[str]] = {}
    for cohort in registry.get("cohorts", []):
        slot = cohort.get("slot")
        for role in ROLE_NAMES:
            role_entry = cohort.get(role)
            if not isinstance(role_entry, dict):
                continue
            digest = role_entry.get("digest")
            if not isinstance(digest, str):
                continue
            protected.setdefault(digest, []).append(f"{role}:{slot}")
    return protected


def mirror_tag_for(role: str, slot: str) -> str:
    """The moveable ECR tag that mirrors a registry slot, e.g. 'retain-warehouse-current'."""
    if role not in ROLE_NAMES:
        raise RegistryError(f"role must be one of {ROLE_NAMES}, got {role!r}")
    if slot not in SLOT_ORDER:
        raise RegistryError(f"slot must be one of {SLOT_ORDER}, got {slot!r}")
    return f"retain-{role}-{slot}"


def expected_mirror_tags(registry: dict) -> dict[str, str]:
    """Return ``{mirror_tag: digest}`` for every cohort/role currently in the registry."""
    expected: dict[str, str] = {}
    for cohort in registry.get("cohorts", []):
        slot = cohort.get("slot")
        if slot not in SLOT_ORDER:
            continue
        for role in ROLE_NAMES:
            role_entry = cohort.get(role)
            if isinstance(role_entry, dict) and isinstance(role_entry.get("digest"), str):
                expected[mirror_tag_for(role, slot)] = role_entry["digest"]
    return expected
