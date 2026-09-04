"""Pure policy engine for recurring AWS cost and S3 retention audits.

AWS collection and deletion live at the CLI boundary.  This module accepts
normalized evidence and produces deterministic findings or a hash-bound exact
VersionId plan; it never talks to AWS itself.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

S3_SERVICE = "Amazon Simple Storage Service"
ECS_SERVICE = "Amazon Elastic Container Service"

FORM_RETENTION_YEARS: dict[str, int] = {
    "13F-HR": 3,
    "13F-HR/A": 3,
    "DEF 14A": 5,
    "DEF 14A/A": 5,
    "DEFA14A": 5,
    "PRE 14A": 5,
    "3": 2,
    "3/A": 2,
    "4": 2,
    "4/A": 2,
    "5": 2,
    "5/A": 2,
    "ADV": 2,
    "ADV/A": 2,
}


@dataclass(frozen=True)
class CostPolicy:
    minimum_monthly_savings_usd: float = 1.0
    drift_percent: float = 20.0


@dataclass(frozen=True)
class CostFinding:
    service: str
    kind: str
    previous_month_usd: float
    latest_month_usd: float
    drift_percent: float
    evidence_status: str = "optimization_candidate"


@dataclass(frozen=True)
class RetentionReference:
    accession_number: str
    form: str
    filing_date: str
    item_502: bool = False
    retain_current: bool = False


@dataclass(frozen=True)
class AccessionAuthority:
    accession_number: str
    form: str
    filing_date: date
    object_keys: tuple[str, ...]
    item_502: bool = False
    retain_current: bool = False
    complete: bool = True
    retention_references: tuple[RetentionReference, ...] = ()


@dataclass(frozen=True)
class ObjectVersion:
    bucket: str
    key: str
    version_id: str
    etag: str
    size_bytes: int
    is_latest: bool
    kind: str


@dataclass(frozen=True)
class DeletionBundle:
    accession_number: str
    form: str
    filing_date: str
    retain_through: str
    retention_years: int
    item_502: bool
    retain_current: bool
    retention_references: tuple[RetentionReference, ...]
    versions: tuple[ObjectVersion, ...]


@dataclass(frozen=True)
class S3RetentionPlan:
    schema_version: int
    expected_account_id: str
    as_of: str
    bundles: tuple[DeletionBundle, ...]
    unmatched: tuple[str, ...]
    total_versions: int
    total_bytes: int
    plan_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _service_priority(service: str) -> tuple[int, str]:
    if service == S3_SERVICE:
        return (0, service)
    if service == ECS_SERVICE:
        return (1, service)
    return (2, service)


def build_cost_findings(
    *,
    previous_month: Mapping[str, float],
    latest_month: Mapping[str, float],
    policy: CostPolicy,
) -> tuple[CostFinding, ...]:
    """Return material closed-month drift findings, with S3/Fargate first."""
    findings: list[CostFinding] = []
    for service, latest in latest_month.items():
        previous = float(previous_month.get(service, 0.0))
        latest = float(latest)
        increase = latest - previous
        if increase <= 0:
            continue
        drift = 100.0 if previous <= 0 else increase / previous * 100.0
        if drift <= policy.drift_percent:
            continue
        findings.append(
            CostFinding(
                service=service,
                kind="spend_drift",
                previous_month_usd=previous,
                latest_month_usd=latest,
                drift_percent=drift,
            )
        )
    findings.sort(key=lambda finding: _service_priority(finding.service))
    return tuple(findings)


def retention_years(authority: AccessionAuthority) -> int | None:
    form = authority.form.strip().upper()
    if form in {"8-K", "8-K/A"}:
        return 2 if authority.item_502 else None
    return FORM_RETENTION_YEARS.get(form)


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def retention_deadline(authority: AccessionAuthority) -> date | None:
    years = retention_years(authority)
    if years is None or authority.retain_current:
        return None
    return _add_years(authority.filing_date, years)


def effective_retention_deadline(authority: AccessionAuthority) -> date | None:
    """Return the latest cutoff across the owner and every shared-object user."""
    deadline = retention_deadline(authority)
    if deadline is None:
        return None
    for reference in authority.retention_references:
        try:
            reference_date = date.fromisoformat(reference.filing_date)
        except ValueError:
            return None
        referenced = AccessionAuthority(
            accession_number=reference.accession_number,
            form=reference.form,
            filing_date=reference_date,
            object_keys=(),
            item_502=reference.item_502,
            retain_current=reference.retain_current,
        )
        reference_deadline = retention_deadline(referenced)
        if reference_deadline is None:
            return None
        deadline = max(deadline, reference_deadline)
    return deadline


def _canonical_payload(value: Mapping[str, Any]) -> bytes:
    payload = dict(value)
    payload.pop("plan_hash", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_plan_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_payload(value)).hexdigest()


def verify_plan_hash(value: Mapping[str, Any], expected_hash: str) -> None:
    actual = compute_plan_hash(value)
    if actual != expected_hash:
        raise ValueError(f"plan hash mismatch: expected {expected_hash}, computed {actual}")


def _validated_versions(
    authority: AccessionAuthority,
    versions_by_key: Mapping[str, list[ObjectVersion]],
    *,
    expected_account_id: str,
) -> tuple[tuple[ObjectVersion, ...] | None, str | None]:
    if not authority.complete:
        return None, f"{authority.accession_number}: authority marks bundle incomplete"
    if not authority.object_keys:
        return None, f"{authority.accession_number}: authority has no expected objects"
    if len(set(authority.object_keys)) != len(authority.object_keys):
        return None, f"{authority.accession_number}: authority has duplicate object keys"

    expected_fragment = f"/accession={authority.accession_number}/"
    expected_keys = set(authority.object_keys)
    observed_bundle_keys = {
        key for key in versions_by_key if expected_fragment in f"/{key}"
    }
    unexpected = sorted(observed_bundle_keys - expected_keys)
    if unexpected:
        return (
            None,
            f"{authority.accession_number}: version inventory contains {len(unexpected)} unclassified object(s)",
        )
    missing: list[str] = []
    selected: list[ObjectVersion] = []
    for key in authority.object_keys:
        if expected_fragment not in f"/{key}":
            return None, f"{authority.accession_number}: object key is outside its accession bundle"
        key_versions = versions_by_key.get(key) or []
        if not key_versions:
            missing.append(key)
            continue
        for version in key_versions:
            if not version.bucket.endswith(f"-{expected_account_id}"):
                return None, f"{authority.accession_number}: bucket account does not match expected account"
            if version.key != key or not version.version_id:
                return None, f"{authority.accession_number}: malformed version inventory"
            if version.kind not in {"version", "delete_marker"}:
                return None, f"{authority.accession_number}: unknown version kind {version.kind!r}"
            if version.size_bytes < 0:
                return None, f"{authority.accession_number}: negative object size"
            selected.append(version)
    if missing:
        return (
            None,
            f"{authority.accession_number}: missing version inventory for {len(missing)} expected object(s)",
        )
    selected.sort(key=lambda item: (item.bucket, item.key, item.version_id, item.kind))
    return tuple(selected), None


def build_s3_retention_plan(
    authorities: Sequence[AccessionAuthority],
    versions: Sequence[ObjectVersion],
    *,
    as_of: date,
    expected_account_id: str,
    current_date: date | None = None,
) -> S3RetentionPlan:
    """Select complete, expired accession bundles and every exact VersionId."""
    if not expected_account_id.isdigit() or len(expected_account_id) != 12:
        raise ValueError("expected_account_id must be exactly 12 digits")
    current_date = current_date or datetime.now(UTC).date()
    if as_of > current_date:
        raise ValueError("as_of cannot be in the future")
    versions_by_key: dict[str, list[ObjectVersion]] = {}
    for version in versions:
        versions_by_key.setdefault(version.key, []).append(version)

    bundles: list[DeletionBundle] = []
    unmatched: list[str] = []
    accession_counts = Counter(item.accession_number for item in authorities)
    reported_duplicates: set[str] = set()
    for authority in sorted(authorities, key=lambda item: item.accession_number):
        if accession_counts[authority.accession_number] > 1:
            if authority.accession_number not in reported_duplicates:
                unmatched.append(f"{authority.accession_number}: duplicate authority rows")
                reported_duplicates.add(authority.accession_number)
            continue
        years = retention_years(authority)
        if years is None:
            unmatched.append(
                f"{authority.accession_number}: form {authority.form} has no classified retention rule"
            )
            continue
        retain_through = effective_retention_deadline(authority)
        if retain_through is None:
            if authority.retention_references:
                unmatched.append(
                    f"{authority.accession_number}: shared object has an unclassified or current reference"
                )
            continue
        if as_of <= retain_through:
            continue
        selected, error = _validated_versions(
            authority,
            versions_by_key,
            expected_account_id=expected_account_id,
        )
        if error:
            unmatched.append(error)
            continue
        assert selected is not None
        bundles.append(
            DeletionBundle(
                accession_number=authority.accession_number,
                form=authority.form,
                filing_date=authority.filing_date.isoformat(),
                retain_through=retain_through.isoformat(),
                retention_years=years,
                item_502=authority.item_502,
                retain_current=authority.retain_current,
                retention_references=authority.retention_references,
                versions=selected,
            )
        )

    total_versions = sum(len(bundle.versions) for bundle in bundles)
    total_bytes = sum(
        version.size_bytes for bundle in bundles for version in bundle.versions
    )
    base: dict[str, Any] = {
        "schema_version": 1,
        "expected_account_id": expected_account_id,
        "as_of": as_of.isoformat(),
        "bundles": [asdict(bundle) for bundle in bundles],
        "unmatched": unmatched,
        "total_versions": total_versions,
        "total_bytes": total_bytes,
    }
    return S3RetentionPlan(
        schema_version=1,
        expected_account_id=expected_account_id,
        as_of=as_of.isoformat(),
        bundles=tuple(bundles),
        unmatched=tuple(unmatched),
        total_versions=total_versions,
        total_bytes=total_bytes,
        plan_hash=compute_plan_hash(base),
    )


def validate_s3_retention_plan_for_apply(
    plan: Mapping[str, Any],
    *,
    current_date: date | None = None,
) -> tuple[ObjectVersion, ...]:
    """Revalidate policy and destructive scope independently of plan creation."""
    if plan.get("schema_version") != 1:
        raise ValueError("unsupported S3 retention plan schema_version")
    account_id = str(plan.get("expected_account_id") or "")
    if not account_id.isdigit() or len(account_id) != 12:
        raise ValueError("plan expected_account_id must be exactly 12 digits")
    as_of = date.fromisoformat(str(plan.get("as_of") or ""))
    current_date = current_date or datetime.now(UTC).date()
    if as_of > current_date:
        raise ValueError("plan as_of cannot be in the future")
    versions: list[ObjectVersion] = []
    identities: set[tuple[str, str, str]] = set()
    accessions: set[str] = set()
    for bundle in plan.get("bundles") or []:
        accession = str(bundle.get("accession_number") or "")
        if accession in accessions:
            raise ValueError(f"plan contains duplicate accession bundle {accession}")
        accessions.add(accession)
        form = str(bundle.get("form") or "")
        filing_date = date.fromisoformat(str(bundle.get("filing_date") or ""))
        item_502 = bundle.get("item_502")
        retain_current = bundle.get("retain_current")
        if not isinstance(item_502, bool) or not isinstance(retain_current, bool):
            raise TypeError(f"plan bundle {accession} policy flags must be booleans")
        references: list[RetentionReference] = []
        for reference_row in bundle.get("retention_references") or []:
            reference = RetentionReference(**reference_row)
            if not isinstance(reference.item_502, bool) or not isinstance(
                reference.retain_current, bool
            ):
                raise TypeError(
                    f"plan bundle {accession} reference policy flags must be booleans"
                )
            references.append(reference)
        authority = AccessionAuthority(
            accession_number=accession,
            form=form,
            filing_date=filing_date,
            item_502=item_502,
            retain_current=retain_current,
            complete=True,
            object_keys=(),
            retention_references=tuple(references),
        )
        years = retention_years(authority)
        deadline = effective_retention_deadline(authority)
        if years is None or deadline is None:
            raise ValueError(f"plan bundle {accession} has no active deletion rule")
        if int(bundle.get("retention_years", -1)) != years:
            raise ValueError(f"plan bundle {accession} retention years do not match policy")
        if str(bundle.get("retain_through") or "") != deadline.isoformat():
            raise ValueError(f"plan bundle {accession} retain_through does not match policy")
        if as_of <= deadline:
            raise ValueError(f"plan bundle {accession} is not expired as of {as_of}")
        expected_bucket = f"edgartools-prod-bronze-{account_id}"
        accession_marker = f"/accession={accession}/"
        for row in bundle.get("versions") or []:
            version = ObjectVersion(**row)
            if version.bucket != expected_bucket:
                raise ValueError(f"plan bundle {accession} targets an unauthorized bucket")
            if not version.key.startswith(
                ("warehouse/bronze/filings/", "warehouse/bronze/text/")
            ) or accession_marker not in f"/{version.key}":
                raise ValueError(f"plan bundle {accession} targets an unauthorized key")
            if not version.version_id:
                raise ValueError(f"plan bundle {accession} has an empty VersionId")
            if version.kind not in {"version", "delete_marker"}:
                raise ValueError(f"plan bundle {accession} has an unknown version kind")
            if version.size_bytes < 0:
                raise ValueError(f"plan bundle {accession} has a negative object size")
            identity = (version.bucket, version.key, version.version_id)
            if identity in identities:
                raise ValueError(f"plan contains duplicate VersionId target {identity}")
            identities.add(identity)
            versions.append(version)
    if int(plan.get("total_versions", -1)) != len(versions):
        raise ValueError("plan total_versions does not match bundle contents")
    if int(plan.get("total_bytes", -1)) != sum(item.size_bytes for item in versions):
        raise ValueError("plan total_bytes does not match bundle contents")
    return tuple(versions)


class AwsOperationGuard:
    """Allowlist AWS CLI operations used by the audit and retention apply."""

    READ_ONLY = frozenset(
        {
            ("sts", "get-caller-identity"),
            ("ce", "get-cost-and-usage"),
            ("s3api", "list-buckets"),
            ("s3api", "get-bucket-location"),
            ("s3api", "get-bucket-versioning"),
            ("s3api", "get-bucket-lifecycle-configuration"),
            ("s3api", "get-public-access-block"),
            ("s3api", "get-bucket-encryption"),
            ("s3api", "list-object-versions"),
            ("s3api", "list-multipart-uploads"),
            ("ecs", "list-clusters"),
            ("ecs", "list-services"),
            ("ecs", "describe-services"),
            ("ecs", "list-tasks"),
            ("ecs", "describe-tasks"),
            ("ecs", "list-task-definition-families"),
            ("ecs", "describe-task-definition"),
            ("logs", "describe-log-groups"),
            ("ecr", "describe-repositories"),
            ("ecr", "describe-images"),
            ("ecr", "get-lifecycle-policy"),
            ("secretsmanager", "list-secrets"),
            ("ec2", "describe-nat-gateways"),
            ("ec2", "describe-vpc-endpoints"),
            ("ec2", "describe-addresses"),
            ("kms", "list-keys"),
            ("kms", "describe-key"),
            ("stepfunctions", "list-state-machines"),
        }
    )
    S3_DELETE = ("s3api", "delete-objects")

    def require_read(self, service: str, operation: str) -> None:
        if (service, operation) not in self.READ_ONLY:
            raise ValueError(
                f"{service} {operation} is not an allowed read-only AWS operation"
            )

    def require_s3_delete(self, service: str, operation: str) -> None:
        if (service, operation) != self.S3_DELETE:
            raise ValueError("retention apply permits only exact S3 version deletion")
