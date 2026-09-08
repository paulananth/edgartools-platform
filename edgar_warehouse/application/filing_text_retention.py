"""Pure evidence and policy contracts for derived filing-text retention."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from edgar_warehouse.application.aws_cost_optimizer import ObjectVersion
from edgar_warehouse.application.errors import WarehouseRuntimeError

KNOWN_TEXT_VERSIONS = frozenset({"generic_text_v1"})
SWEEP_MANIFEST_SCHEMA_VERSION = 1
RETENTION_PLAN_SCHEMA_VERSION = 1
MINIMUM_NOT_REQUIRED_DAYS = 30


def _canonical_bytes(value: Mapping[str, Any], *, omit: str | None = None) -> bytes:
    payload = dict(value)
    if omit is not None:
        payload.pop(omit, None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _identity(row: Mapping[str, Any]) -> tuple[str, str]:
    accession = str(row.get("accession_number") or "").strip()
    text_version = str(row.get("text_version") or "").strip()
    if not accession or not text_version:
        raise WarehouseRuntimeError(
            "filing-text retention identity requires accession_number and text_version"
        )
    return accession, text_version


def build_filing_text_sweep_manifest(
    *,
    run_id: str,
    observed_at: datetime,
    snowflake_query_id: str,
    required_rows: Sequence[Mapping[str, Any]],
    processed_rows: Sequence[Mapping[str, Any]],
    status: str,
    previous_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete, deterministic observation of derived-text necessity."""
    if not run_id.strip():
        raise WarehouseRuntimeError("filing-text retention manifest requires run_id")
    snowflake_query_id = snowflake_query_id.strip()
    if not snowflake_query_id:
        raise WarehouseRuntimeError(
            "filing-text retention manifest requires a Snowflake query ID"
        )
    if status not in {"succeeded", "incomplete"}:
        raise WarehouseRuntimeError("filing-text retention manifest has invalid status")

    required = [
        {"accession_number": accession, "text_version": text_version}
        for accession, text_version in sorted({_identity(row) for row in required_rows})
    ]
    processed_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for row in processed_rows:
        identity = _identity(row)
        if identity in processed_by_identity:
            raise WarehouseRuntimeError(
                f"duplicate filing-text retention identity {identity!r}"
            )
        processed_by_identity[identity] = {
            "accession_number": identity[0],
            "text_version": identity[1],
            "text_storage_path": str(row.get("text_storage_path") or ""),
            "text_sha256": str(row.get("text_sha256") or ""),
        }
    processed = [processed_by_identity[key] for key in sorted(processed_by_identity)]
    required_identities = {
        (row["accession_number"], row["text_version"]) for row in required
    }
    not_required_base = [
        row
        for row in processed
        if (row["accession_number"], row["text_version"]) not in required_identities
        and row["text_version"] in KNOWN_TEXT_VERSIONS
    ]
    unclassified = [
        row for row in processed if row["text_version"] not in KNOWN_TEXT_VERSIONS
    ]
    observed_at_utc = (
        observed_at.replace(tzinfo=UTC)
        if observed_at.tzinfo is None
        else observed_at.astimezone(UTC)
    )
    previous_manifest_hash: str | None = None
    previous_run_id: str | None = None
    previous_not_required: dict[tuple[str, str], Mapping[str, Any]] = {}
    if previous_manifest is not None:
        previous_at = _validate_filing_text_sweep_manifest(
            previous_manifest, require_succeeded=False
        )
        if previous_at >= observed_at_utc:
            raise WarehouseRuntimeError(
                "filing-text retention predecessor must be older than this observation"
            )
        previous_manifest_hash = str(previous_manifest["manifest_hash"])
        previous_run_id = str(previous_manifest["run_id"])
        if previous_manifest.get("status") == "succeeded":
            previous_not_required = {
                _identity(row): row for row in previous_manifest["not_required"]
            }
    not_required: list[dict[str, Any]] = []
    for row in not_required_base:
        predecessor = previous_not_required.get(_identity(row))
        unchanged = predecessor is not None and all(
            predecessor.get(field) == row.get(field)
            for field in ("text_storage_path", "text_sha256")
        )
        not_required_since = (
            predecessor["not_required_since"]
            if unchanged and predecessor is not None
            else observed_at_utc.isoformat().replace("+00:00", "Z")
        )
        not_required.append(
            {
                **row,
                "not_required_since": not_required_since,
            }
        )
    sets = {
        "required": required,
        "processed": processed,
        "not_required": not_required,
        "unclassified": unclassified,
    }
    set_hashes = {name: _sha256(rows) for name, rows in sets.items()}
    snapshot_hash = _sha256(
        {"required": required, "processed": processed}
    )
    set_hashes["snowflake_snapshot"] = snapshot_hash
    publication_identity = {
        "query_id": snowflake_query_id,
        "snapshot_hash": snapshot_hash,
    }
    manifest: dict[str, Any] = {
        "schema_version": SWEEP_MANIFEST_SCHEMA_VERSION,
        "kind": "filing_text_sweep",
        "run_id": run_id,
        "observed_at": observed_at_utc.isoformat().replace("+00:00", "Z"),
        "status": status,
        "previous_manifest_hash": previous_manifest_hash,
        "previous_run_id": previous_run_id,
        "snowflake_publication_identity": publication_identity,
        **sets,
        "counts": {name: len(rows) for name, rows in sets.items()},
        "set_hashes": set_hashes,
    }
    manifest["manifest_hash"] = hashlib.sha256(
        _canonical_bytes(manifest)
    ).hexdigest()
    return manifest


def filing_text_sweep_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def filing_text_sweep_manifest_path(*, run_id: str, observed_at: datetime) -> str:
    observed_at_utc = (
        observed_at.replace(tzinfo=UTC)
        if observed_at.tzinfo is None
        else observed_at.astimezone(UTC)
    )
    return (
        "artifacts/filing_text_retention/"
        f"observed_date={observed_at_utc.date().isoformat()}/"
        f"run_id={run_id}/manifest.json"
    )


def _parse_observed_at(value: Any) -> datetime:
    raw = str(value or "")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise WarehouseRuntimeError(
            "filing-text retention manifest has invalid observed_at"
        ) from exc
    if parsed.tzinfo is None:
        raise WarehouseRuntimeError(
            "filing-text retention manifest observed_at must include a timezone"
        )
    return parsed.astimezone(UTC)


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_filing_text_sweep_manifest(
    manifest: Mapping[str, Any], *, require_succeeded: bool
) -> datetime:
    """Validate complete immutable evidence, optionally allowing incomplete runs."""
    if manifest.get("schema_version") != SWEEP_MANIFEST_SCHEMA_VERSION:
        raise WarehouseRuntimeError(
            "unsupported filing-text retention manifest schema_version"
        )
    if manifest.get("kind") != "filing_text_sweep":
        raise WarehouseRuntimeError("not a filing-text sweep manifest")
    if manifest.get("status") not in {"succeeded", "incomplete"}:
        raise WarehouseRuntimeError("filing-text retention manifest has invalid status")
    if require_succeeded and manifest.get("status") != "succeeded":
        raise WarehouseRuntimeError(
            "filing-text retention manifest is failed or incomplete"
        )
    if not str(manifest.get("run_id") or "").strip():
        raise WarehouseRuntimeError("filing-text retention manifest has no run_id")
    observed_at = _parse_observed_at(manifest.get("observed_at"))
    previous_hash = manifest.get("previous_manifest_hash")
    previous_run_id = manifest.get("previous_run_id")
    if (previous_hash is None) != (previous_run_id is None):
        raise WarehouseRuntimeError(
            "filing-text retention manifest has incomplete predecessor identity"
        )
    if previous_hash is not None and (
        not _valid_sha256(previous_hash) or not str(previous_run_id).strip()
    ):
        raise WarehouseRuntimeError(
            "filing-text retention manifest has invalid predecessor identity"
        )
    expected_manifest_hash = hashlib.sha256(
        _canonical_bytes(manifest, omit="manifest_hash")
    ).hexdigest()
    if manifest.get("manifest_hash") != expected_manifest_hash:
        raise WarehouseRuntimeError("filing-text retention manifest hash mismatch")

    sets: dict[str, list[Mapping[str, Any]]] = {}
    for name in ("required", "processed", "not_required", "unclassified"):
        rows = manifest.get(name)
        if not isinstance(rows, list) or not all(
            isinstance(row, Mapping) for row in rows
        ):
            raise WarehouseRuntimeError(
                f"filing-text retention manifest {name} must be a complete list"
            )
        sets[name] = rows
        if manifest.get("counts", {}).get(name) != len(rows):
            raise WarehouseRuntimeError(
                f"filing-text retention manifest {name} count mismatch"
            )
        if manifest.get("set_hashes", {}).get(name) != _sha256(rows):
            raise WarehouseRuntimeError(
                f"filing-text retention manifest {name} hash mismatch"
            )

    required_identities = {_identity(row) for row in sets["required"]}
    processed_by_identity: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in sets["processed"]:
        identity = _identity(row)
        if identity in processed_by_identity:
            raise WarehouseRuntimeError(
                f"duplicate filing-text retention identity {identity!r}"
            )
        if not str(row.get("text_storage_path") or "") or not _valid_sha256(
            row.get("text_sha256")
        ):
            raise WarehouseRuntimeError(
                f"filing-text retention identity {identity!r} lacks object evidence"
            )
        processed_by_identity[identity] = row
    expected_not_required_identities = [
        identity
        for identity in sorted(processed_by_identity)
        if identity not in required_identities and identity[1] in KNOWN_TEXT_VERSIONS
    ]
    expected_unclassified = [
        processed_by_identity[identity]
        for identity in sorted(processed_by_identity)
        if identity[1] not in KNOWN_TEXT_VERSIONS
    ]
    actual_not_required: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in sets["not_required"]:
        identity = _identity(row)
        if identity in actual_not_required:
            raise WarehouseRuntimeError(
                f"duplicate filing-text not-required identity {identity!r}"
            )
        since = _parse_observed_at(row.get("not_required_since"))
        if since > observed_at:
            raise WarehouseRuntimeError(
                f"filing-text retention identity {identity!r} has future continuity"
            )
        actual_not_required[identity] = row
    if sorted(actual_not_required) != expected_not_required_identities or any(
        {
            key: value
            for key, value in actual_not_required[identity].items()
            if key != "not_required_since"
        }
        != dict(processed_by_identity[identity])
        for identity in expected_not_required_identities
    ):
        raise WarehouseRuntimeError(
            "filing-text retention manifest not_required set is incomplete"
        )
    if sets["unclassified"] != expected_unclassified:
        raise WarehouseRuntimeError(
            "filing-text retention manifest unclassified set is incomplete"
        )
    expected_snapshot_hash = _sha256(
        {"required": sets["required"], "processed": sets["processed"]}
    )
    publication = manifest.get("snowflake_publication_identity")
    if (
        not isinstance(publication, Mapping)
        or set(publication) != {"query_id", "snapshot_hash"}
        or not str(publication.get("query_id") or "").strip()
        or publication.get("snapshot_hash") != expected_snapshot_hash
        or manifest.get("set_hashes", {}).get("snowflake_snapshot")
        != expected_snapshot_hash
    ):
        raise WarehouseRuntimeError(
            "filing-text retention Snowflake publication identity mismatch"
        )
    return observed_at


def validate_filing_text_sweep_manifest(
    manifest: Mapping[str, Any],
) -> datetime:
    """Reject sampled, mutable, malformed, or incomplete sweep evidence."""
    return _validate_filing_text_sweep_manifest(
        manifest, require_succeeded=True
    )


def filing_text_storage_identity(
    row: Mapping[str, Any], *, expected_account_id: str
) -> tuple[str, str]:
    accession, text_version = _identity(row)
    parsed = urlsplit(str(row.get("text_storage_path") or ""))
    expected_bucket = f"edgartools-prod-warehouse-{expected_account_id}"
    key = parsed.path.lstrip("/")
    expected_suffix = f"/accession={accession}/{text_version}.txt"
    if (
        parsed.scheme != "s3"
        or parsed.netloc != expected_bucket
        or not key.startswith("warehouse/text/sec/cik=")
        or not key.endswith(expected_suffix)
    ):
        raise WarehouseRuntimeError(
            f"filing-text retention identity {(accession, text_version)!r} "
            "targets an unauthorized derived-text object"
        )
    return parsed.netloc, key


def _version_payload(version: ObjectVersion) -> dict[str, Any]:
    return {
        "bucket": version.bucket,
        "key": version.key,
        "version_id": version.version_id,
        "etag": version.etag,
        "size_bytes": version.size_bytes,
        "is_latest": version.is_latest,
        "kind": version.kind,
        "storage_class": version.storage_class,
    }


def build_filing_text_retention_plan(
    *,
    prior_manifest: Mapping[str, Any],
    current_manifest: Mapping[str, Any],
    versions: Sequence[ObjectVersion],
    expected_account_id: str,
) -> dict[str, Any]:
    """Select exact derived-text versions observed not required for 30 days."""
    if not expected_account_id.isdigit() or len(expected_account_id) != 12:
        raise WarehouseRuntimeError("expected_account_id must be exactly 12 digits")
    prior_at = validate_filing_text_sweep_manifest(prior_manifest)
    current_at = validate_filing_text_sweep_manifest(current_manifest)
    if current_at <= prior_at:
        raise WarehouseRuntimeError(
            "filing-text retention observations are out of order"
        )
    observation_span = current_at - prior_at
    if prior_manifest.get("run_id") == current_manifest.get("run_id"):
        raise WarehouseRuntimeError(
            "filing-text retention observations must come from distinct runs"
        )
    if (
        current_manifest.get("previous_manifest_hash")
        != prior_manifest.get("manifest_hash")
        or current_manifest.get("previous_run_id") != prior_manifest.get("run_id")
    ):
        raise WarehouseRuntimeError(
            "filing-text retention observations are not consecutive"
        )

    prior_rows = {_identity(row): row for row in prior_manifest["not_required"]}
    current_rows = {_identity(row): row for row in current_manifest["not_required"]}
    eligible = sorted(set(prior_rows).intersection(current_rows))
    versions_by_object: dict[tuple[str, str], list[ObjectVersion]] = {}
    for version in versions:
        versions_by_object.setdefault((version.bucket, version.key), []).append(
            version
        )

    targets: list[dict[str, Any]] = []
    blocked: list[str] = [
        f"{identity[0]}|{identity[1]}: unknown text version"
        for identity in sorted(
            {_identity(row) for row in current_manifest["unclassified"]}
        )
    ]
    blocked.extend(
        f"{identity[0]}|{identity[1]}: not observed as not required in both successful sweeps"
        for identity in sorted(set(current_rows) - set(prior_rows))
    )
    used_objects: set[tuple[str, str]] = set()
    for identity in eligible:
        prior_row = prior_rows[identity]
        current_row = current_rows[identity]
        if (
            prior_row.get("text_storage_path")
            != current_row.get("text_storage_path")
            or prior_row.get("text_sha256") != current_row.get("text_sha256")
        ):
            blocked.append(f"{identity[0]}|{identity[1]}: derived object drifted")
            continue
        prior_since = _parse_observed_at(prior_row.get("not_required_since"))
        current_since = _parse_observed_at(current_row.get("not_required_since"))
        if current_since != prior_since:
            blocked.append(
                f"{identity[0]}|{identity[1]}: not-required continuity reset"
            )
            continue
        continuous_span = current_at - current_since
        if continuous_span < timedelta(days=MINIMUM_NOT_REQUIRED_DAYS):
            blocked.append(
                f"{identity[0]}|{identity[1]}: continuously not required for fewer than 30 days"
            )
            continue
        try:
            bucket, key = filing_text_storage_identity(
                current_row, expected_account_id=expected_account_id
            )
        except WarehouseRuntimeError as exc:
            blocked.append(str(exc))
            continue
        selected = versions_by_object.get((bucket, key), [])
        if not selected:
            blocked.append(f"{identity[0]}|{identity[1]}: no exact version inventory")
            continue
        malformed = next(
            (
                version
                for version in selected
                if not version.version_id
                or version.kind not in {"version", "delete_marker"}
                or version.size_bytes < 0
            ),
            None,
        )
        if malformed is not None:
            blocked.append(f"{identity[0]}|{identity[1]}: malformed version inventory")
            continue
        selected.sort(
            key=lambda version: (
                version.bucket,
                version.key,
                version.version_id,
                version.kind,
            )
        )
        used_objects.add((bucket, key))
        targets.append(
            {
                "accession_number": identity[0],
                "text_version": identity[1],
                "text_storage_path": current_row["text_storage_path"],
                "text_sha256": current_row["text_sha256"],
                "not_required_since": current_row["not_required_since"],
                "continuous_days": continuous_span.days,
                "business_key": f"{identity[0]}|{identity[1]}",
                "versions": [_version_payload(version) for version in selected],
            }
        )
    for bucket, key in sorted(set(versions_by_object) - used_objects):
        blocked.append(f"s3://{bucket}/{key}: unbound version inventory")

    total_versions = sum(len(target["versions"]) for target in targets)
    total_bytes = sum(
        int(version["size_bytes"])
        for target in targets
        for version in target["versions"]
    )
    plan: dict[str, Any] = {
        "schema_version": RETENTION_PLAN_SCHEMA_VERSION,
        "kind": "filing_text_retention",
        "expected_account_id": expected_account_id,
        "prior_manifest_hash": prior_manifest["manifest_hash"],
        "current_manifest_hash": current_manifest["manifest_hash"],
        "prior_run_id": prior_manifest["run_id"],
        "current_run_id": current_manifest["run_id"],
        "observed_from": prior_manifest["observed_at"],
        "observed_through": current_manifest["observed_at"],
        "observation_days": observation_span.days,
        "targets": targets,
        "blocked": sorted(blocked),
        "total_versions": total_versions,
        "total_bytes": total_bytes,
    }
    plan["plan_hash"] = hashlib.sha256(_canonical_bytes(plan)).hexdigest()
    return plan


def validate_filing_text_retention_plan_for_apply(
    plan: Mapping[str, Any],
) -> tuple[ObjectVersion, ...]:
    """Revalidate exact derived-only scope independently of plan creation."""
    if plan.get("schema_version") != RETENTION_PLAN_SCHEMA_VERSION:
        raise WarehouseRuntimeError(
            "unsupported filing-text retention plan schema_version"
        )
    if plan.get("kind") != "filing_text_retention":
        raise WarehouseRuntimeError("not a filing-text retention plan")
    expected_hash = hashlib.sha256(
        _canonical_bytes(plan, omit="plan_hash")
    ).hexdigest()
    if plan.get("plan_hash") != expected_hash:
        raise WarehouseRuntimeError("filing-text retention plan hash mismatch")
    account_id = str(plan.get("expected_account_id") or "")
    if not account_id.isdigit() or len(account_id) != 12:
        raise WarehouseRuntimeError(
            "filing-text retention plan has invalid account identity"
        )
    observed_from = _parse_observed_at(plan.get("observed_from"))
    observed_through = _parse_observed_at(plan.get("observed_through"))
    span = observed_through - observed_from
    if span <= timedelta(0):
        raise WarehouseRuntimeError(
            "filing-text retention plan observations are out of order"
        )
    if plan.get("observation_days") != span.days:
        raise WarehouseRuntimeError(
            "filing-text retention plan observation_days mismatch"
        )
    if not _valid_sha256(plan.get("prior_manifest_hash")) or not _valid_sha256(
        plan.get("current_manifest_hash")
    ):
        raise WarehouseRuntimeError(
            "filing-text retention plan lacks complete manifest hashes"
        )

    versions: list[ObjectVersion] = []
    business_keys: set[str] = set()
    version_ids: set[tuple[str, str, str]] = set()
    for target in plan.get("targets") or []:
        if not isinstance(target, Mapping):
            raise WarehouseRuntimeError(
                "filing-text retention target must be an object"
            )
        identity = _identity(target)
        if identity[1] not in KNOWN_TEXT_VERSIONS:
            raise WarehouseRuntimeError(
                f"filing-text retention target {identity!r} has unknown text version"
            )
        business_key = f"{identity[0]}|{identity[1]}"
        if target.get("business_key") != business_key or business_key in business_keys:
            raise WarehouseRuntimeError(
                f"filing-text retention target {identity!r} has invalid business key"
            )
        business_keys.add(business_key)
        if not _valid_sha256(target.get("text_sha256")):
            raise WarehouseRuntimeError(
                f"filing-text retention target {identity!r} has invalid content hash"
            )
        not_required_since = _parse_observed_at(target.get("not_required_since"))
        continuous_span = observed_through - not_required_since
        if (
            continuous_span < timedelta(days=MINIMUM_NOT_REQUIRED_DAYS)
            or target.get("continuous_days") != continuous_span.days
        ):
            raise WarehouseRuntimeError(
                f"filing-text retention target {identity!r} lacks continuous eligibility"
            )
        bucket, key = filing_text_storage_identity(
            target, expected_account_id=account_id
        )
        target_versions = target.get("versions")
        if not isinstance(target_versions, list) or not target_versions:
            raise WarehouseRuntimeError(
                f"filing-text retention target {identity!r} has no exact versions"
            )
        for row in target_versions:
            version = ObjectVersion(**row)
            if (
                version.bucket != bucket
                or version.key != key
                or not version.version_id
                or version.kind not in {"version", "delete_marker"}
                or version.size_bytes < 0
            ):
                raise WarehouseRuntimeError(
                    f"filing-text retention target {identity!r} has unauthorized version"
                )
            version_id = (version.bucket, version.key, version.version_id)
            if version_id in version_ids:
                raise WarehouseRuntimeError(
                    "filing-text retention plan contains duplicate VersionId target"
                )
            version_ids.add(version_id)
            versions.append(version)
    if plan.get("total_versions") != len(versions):
        raise WarehouseRuntimeError(
            "filing-text retention plan total_versions mismatch"
        )
    if plan.get("total_bytes") != sum(version.size_bytes for version in versions):
        raise WarehouseRuntimeError("filing-text retention plan total_bytes mismatch")
    return tuple(versions)
