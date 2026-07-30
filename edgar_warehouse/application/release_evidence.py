"""Release Evidence Automation (release-readiness map, ticket 09).

Deterministically builds and maintains a Candidate Evidence Set manifest
(``release-evidence.json``) per ticket 01's Answer: one append-only manifest
per Release Candidate at
``docs/release-readiness/releases/rc-<YYYYMMDD>-<12-char-commit>/``, indexing
digest-bound sanitized gate evidence.

This module is pure: it never performs network I/O, never queries AWS/
Snowflake/MDM, and never reads the wall clock. Every timestamp is supplied by
the caller. ``validate_manifest`` reads local evidence files from a supplied
``repo_root`` to check they still exist and still hash to what the manifest
recorded — that is local, read-only filesystem I/O, not a live system query.

Deliberately out of scope, per ticket 09's scope decision: producing any
gate's own evidence, computing a Release Data Watermark from live systems,
and writing Gate Attestations, a final disposition, or a Release Seal. Those
remain human actions (or the job of other tickets) — this module refuses to
ever set them itself; see ``tests/architecture/test_release_evidence_no_auto_approval.py``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = 1

# Ticket 01's Answer: "Live production evidence must ... remain within the
# 24-hour Live-Evidence Window." A fixed invariant, not an operator-adjustable
# knob — add_gate takes no expiry-hours argument.
LIVE_EVIDENCE_WINDOW_HOURS = 24

_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DATE_STAMP_RE = re.compile(r"^\d{8}$")
_CANDIDATE_ID_RE = re.compile(r"^rc-\d{8}-[0-9a-f]{12}$")

_REQUIRED_TOP_LEVEL_FIELDS = (
    "schema_version",
    "candidate_id",
    "commit_sha",
    "source_branch",
    "lifecycle_status",
    "identity_freeze_timestamp",
    "warehouse_image_digest",
    "mdm_image_digest",
    "release_data_watermark",
    "gates",
    "attestations",
    "disposition",
    "release_owner_attestation",
    "release_seal",
    "addendum_references",
)

_REQUIRED_GATE_FIELDS = (
    "gate_name",
    "status",
    "evidence_path",
    "evidence_sha256",
    "media_type",
    "capture_tool",
    "capture_tool_version",
    "captured_at",
    "expires_at",
    "sanitization",
)

_REQUIRED_ATTESTATION_FIELDS = (
    "role",
    "approver_handle",
    "attested_at",
    "candidate_id",
    "watermark_digest",
    "evidence_digest",
)

# Nested "release_data_watermark" fields per ticket 01's Answer: "a composite
# Release Data Watermark spanning the bronze input-manifest digest and
# maximum eligible business date, bounded full-chain execution identity/
# scope, silver shard-manifest digest, Snowflake export run/business date/
# manifest digest, MDM publication watermark, and hosted-graph generation/
# publication identity."
_REQUIRED_WATERMARK_FIELDS = (
    "bronze_input_manifest_digest",
    "max_eligible_business_date",
    "full_chain_execution_id",
    "full_chain_execution_scope",
    "silver_shard_manifest_digest",
    "snowflake_export",
    "mdm_publication_watermark",
    "hosted_graph",
)
_REQUIRED_SNOWFLAKE_EXPORT_FIELDS = ("run_id", "business_date", "manifest_digest")
_REQUIRED_HOSTED_GRAPH_FIELDS = ("generation_id", "publication_id")

_VALID_GATE_STATUSES = frozenset({"pass", "fail"})
_VALID_DISPOSITIONS = frozenset({"go", "no_go", "superseded"})


class ReleaseEvidenceError(Exception):
    """Base class for all release-evidence rejections."""


class GateRejectedError(ReleaseEvidenceError):
    """A gate record is malformed or violates append-only semantics."""


class LineageError(ReleaseEvidenceError):
    """An evidence path does not belong to this candidate's own evidence dir."""


class SanitizationError(ReleaseEvidenceError):
    """Evidence content contains a forbidden secret-shaped pattern."""


class IdentityFrozenError(ReleaseEvidenceError):
    """The candidate already has a final disposition; it is immutable."""


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("aws_account_id", re.compile(rb"\b\d{12}\b")),
    ("aws_arn", re.compile(rb"\barn:aws:[a-z0-9-]+:")),
    (
        "ecr_registry_host",
        re.compile(rb"\b\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com\b"),
    ),
    ("postgres_dsn", re.compile(rb"\bpostgres(?:ql)?://", re.IGNORECASE)),
    ("snowflake_dsn", re.compile(rb"\bsnowflake://", re.IGNORECASE)),
    (
        "snowflake_account_locator",
        re.compile(rb"\b[A-Z]{6,}-[A-Z0-9]{6,}\b", re.IGNORECASE),
    ),
)


def scan_for_secrets(content: bytes) -> list[str]:
    """Return the sorted list of secret-pattern names found in ``content``.

    Empty list means clean. This is a fail-closed heuristic scan, not a
    guarantee of completeness — see ticket 09's Answer for the concrete
    pattern list this repo is known to need.
    """
    findings = {name for name, pattern in _SECRET_PATTERNS if pattern.search(content)}
    return sorted(findings)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def watermark_digest_for(watermark: dict[str, Any]) -> str:
    """Return the canonical digest used to bind attestations to a watermark."""
    canonical = json.dumps(
        watermark,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{sha256_hex(canonical)}"


def _parse_utc_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be an ISO8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an ISO8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must include an explicit UTC offset")
    return parsed


# ---------------------------------------------------------------------------
# Candidate identity
# ---------------------------------------------------------------------------


def candidate_id_for(commit_sha: str, date_stamp: str) -> str:
    """Build ``rc-<YYYYMMDD>-<12-char-commit>`` per ticket 01's Answer."""
    if not _COMMIT_SHA_RE.fullmatch(commit_sha):
        raise ValueError("commit_sha must be the full 40-character lowercase hex SHA")
    if not _DATE_STAMP_RE.fullmatch(date_stamp):
        raise ValueError("date_stamp must use YYYYMMDD")
    return f"rc-{date_stamp}-{commit_sha[:12]}"


def _candidate_evidence_prefix(candidate_id: str) -> str:
    return f"docs/release-readiness/releases/{candidate_id}/evidence/"


# ---------------------------------------------------------------------------
# Manifest construction
# ---------------------------------------------------------------------------


def build_manifest(
    *,
    commit_sha: str,
    source_branch: str,
    warehouse_image_digest: str,
    mdm_image_digest: str,
    release_data_watermark: dict[str, Any],
    identity_freeze_timestamp: str,
) -> dict[str, Any]:
    """Build a fresh Candidate Evidence Set manifest.

    Deterministic: identical inputs always produce an identical manifest.
    ``identity_freeze_timestamp`` is supplied by the caller, never read from
    the wall clock here.
    """
    for label, digest in (
        ("warehouse_image_digest", warehouse_image_digest),
        ("mdm_image_digest", mdm_image_digest),
    ):
        if not _IMAGE_DIGEST_RE.match(digest):
            raise ValueError(
                f"{label} must be a bare 'sha256:<64 hex>' digest with no "
                f"registry or account identifier, got {digest!r}"
            )

    date_stamp = identity_freeze_timestamp[:10].replace("-", "")
    candidate_id = candidate_id_for(commit_sha, date_stamp)

    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "commit_sha": commit_sha,
        "source_branch": source_branch,
        "lifecycle_status": "frozen",
        "identity_freeze_timestamp": identity_freeze_timestamp,
        "warehouse_image_digest": warehouse_image_digest,
        "mdm_image_digest": mdm_image_digest,
        "release_data_watermark": copy.deepcopy(release_data_watermark),
        "gates": [],
        "attestations": [],
        "disposition": None,
        "release_owner_attestation": None,
        "release_seal": None,
        "addendum_references": [],
    }


# ---------------------------------------------------------------------------
# Gate append
# ---------------------------------------------------------------------------


def add_gate(
    manifest: dict[str, Any],
    *,
    gate_name: str,
    status: str,
    evidence_relpath: str,
    evidence_bytes: bytes,
    media_type: str,
    capture_tool: str,
    capture_tool_version: str,
    captured_at: str,
) -> dict[str, Any]:
    """Return a new manifest with one sanitized gate record appended.

    Never mutates ``manifest`` in place. Fails closed: a duplicate gate name,
    an out-of-lineage evidence path, an invalid status, or any secret-shaped
    content in the evidence itself all raise rather than silently proceeding.
    """
    if not isinstance(manifest, dict):
        raise GateRejectedError("manifest must be a JSON object")

    if manifest.get("disposition") is not None:
        raise IdentityFrozenError(
            "candidate already has a final disposition; no further gates may be added"
        )

    if not isinstance(status, str) or status not in _VALID_GATE_STATUSES:
        raise GateRejectedError(
            f"status must be one of {sorted(_VALID_GATE_STATUSES)}, got {status!r}"
        )

    for label, value in (
        ("gate_name", gate_name),
        ("media_type", media_type),
        ("capture_tool", capture_tool),
        ("capture_tool_version", capture_tool_version),
    ):
        if not isinstance(value, str) or not value.strip():
            raise GateRejectedError(f"{label} must be a non-empty string")

    gates = manifest.get("gates")
    if not isinstance(gates, list) or any(not isinstance(gate, dict) for gate in gates):
        raise GateRejectedError("manifest gates must be an array of JSON objects")

    if any(gate.get("gate_name") == gate_name for gate in gates):
        raise GateRejectedError(
            f"gate {gate_name!r} already recorded; the manifest is append-only "
            "and gate names must be distinct"
        )

    candidate_id = manifest.get("candidate_id")
    if not isinstance(candidate_id, str) or not _CANDIDATE_ID_RE.fullmatch(
        candidate_id
    ):
        raise GateRejectedError("manifest candidate_id has an invalid format")

    if (
        not isinstance(evidence_relpath, str)
        or not evidence_relpath
        or "\x00" in evidence_relpath
    ):
        raise LineageError("evidence path must be a non-empty path string")

    expected_prefix = _candidate_evidence_prefix(candidate_id)
    evidence_path = PurePosixPath(evidence_relpath)
    expected_parts = PurePosixPath(expected_prefix).parts
    if (
        evidence_path.is_absolute()
        or ".." in evidence_path.parts
        or evidence_path.parts[: len(expected_parts)] != expected_parts
        or len(evidence_path.parts) <= len(expected_parts)
    ):
        raise LineageError(
            f"evidence path {evidence_relpath!r} is not under this candidate's "
            f"own evidence directory ({expected_prefix!r})"
        )

    findings = scan_for_secrets(evidence_bytes)
    if findings:
        raise SanitizationError(
            f"evidence for gate {gate_name!r} contains forbidden content: {findings}"
        )

    try:
        captured_dt = _parse_utc_timestamp(captured_at, "captured_at")
    except (TypeError, ValueError) as exc:
        raise GateRejectedError(str(exc)) from exc
    try:
        identity_freeze = _parse_utc_timestamp(
            manifest.get("identity_freeze_timestamp"),
            "identity_freeze_timestamp",
        )
    except (TypeError, ValueError) as exc:
        raise GateRejectedError(str(exc)) from exc
    if captured_dt < identity_freeze:
        raise GateRejectedError(
            "captured_at cannot be before identity_freeze_timestamp"
        )
    expires_dt = captured_dt + timedelta(hours=LIVE_EVIDENCE_WINDOW_HOURS)

    gate_record = {
        "gate_name": gate_name,
        "status": status,
        "evidence_path": evidence_relpath,
        "evidence_sha256": sha256_hex(evidence_bytes),
        "media_type": media_type,
        "capture_tool": capture_tool,
        "capture_tool_version": capture_tool_version,
        "captured_at": captured_at,
        "expires_at": expires_dt.isoformat(),
        "sanitization": {"scanned": True, "findings": []},
    }

    updated = copy.deepcopy(manifest)
    updated["gates"].append(gate_record)
    return updated


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationFinding:
    code: str
    message: str
    gate_name: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    findings: list[ValidationFinding]


def validate_manifest(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
    as_of: datetime,
) -> ValidationReport:
    """Validate schema, lineage, digest-matches-file, freshness, and secrets.

    Read-only: never mutates ``manifest`` and never writes anything. ``as_of``
    is the caller-supplied "current time" for the 24-hour freshness check —
    this function never reads the wall clock itself.
    """
    findings: list[ValidationFinding] = []

    if not isinstance(manifest, dict):
        return ValidationReport(
            ok=False,
            findings=[
                ValidationFinding(
                    code="invalid_type",
                    message="manifest must be a JSON object",
                )
            ],
        )

    try:
        as_of_utc = _parse_utc_timestamp(as_of.isoformat(), "as_of")
    except (AttributeError, ValueError):
        as_of_utc = None
        findings.append(
            ValidationFinding(
                code="invalid_timestamp",
                message="as_of must be a timezone-aware UTC datetime",
            )
        )

    for field in _REQUIRED_TOP_LEVEL_FIELDS:
        if field not in manifest:
            findings.append(
                ValidationFinding(
                    code="missing_field",
                    message=f"manifest is missing required field {field!r}",
                )
            )

    if manifest.get("schema_version") != SCHEMA_VERSION:
        findings.append(
            ValidationFinding(
                code="invalid_schema_version",
                message=(
                    f"schema_version must be {SCHEMA_VERSION}, got "
                    f"{manifest.get('schema_version')!r}"
                ),
            )
        )

    if manifest.get("lifecycle_status") != "frozen":
        findings.append(
            ValidationFinding(
                code="invalid_lifecycle_status",
                message=(
                    "lifecycle_status must remain 'frozen', got "
                    f"{manifest.get('lifecycle_status')!r}"
                ),
            )
        )

    freeze_timestamp = manifest.get("identity_freeze_timestamp")
    freeze_dt: datetime | None = None
    try:
        freeze_dt = _parse_utc_timestamp(freeze_timestamp, "identity_freeze_timestamp")
        if as_of_utc is not None and freeze_dt > as_of_utc:
            findings.append(
                ValidationFinding(
                    code="identity_freeze_from_future",
                    message="identity_freeze_timestamp is after as_of",
                )
            )
    except (TypeError, ValueError) as exc:
        findings.append(ValidationFinding(code="invalid_timestamp", message=str(exc)))

    candidate_id = manifest.get("candidate_id")
    commit_sha = manifest.get("commit_sha")
    if not isinstance(candidate_id, str) or not _CANDIDATE_ID_RE.fullmatch(
        candidate_id
    ):
        findings.append(
            ValidationFinding(
                code="invalid_candidate_id",
                message=f"candidate_id has invalid format: {candidate_id!r}",
            )
        )
        candidate_id = None

    if not isinstance(commit_sha, str) or not _COMMIT_SHA_RE.fullmatch(commit_sha):
        findings.append(
            ValidationFinding(
                code="invalid_commit_sha",
                message=f"commit_sha must be a full lowercase hex SHA, got {commit_sha!r}",
            )
        )
        commit_sha = None

    if candidate_id is not None and commit_sha is not None:
        expected_tail = commit_sha[:12]
        _, candidate_date, actual_tail = candidate_id.split("-")
        if actual_tail != expected_tail:
            findings.append(
                ValidationFinding(
                    code="candidate_id_commit_mismatch",
                    message=(
                        f"candidate_id {candidate_id!r} does not match commit_sha "
                        f"{commit_sha!r} (expected tail {expected_tail!r}, got "
                        f"{actual_tail!r})"
                    ),
                )
            )
        if freeze_dt is not None and candidate_date != freeze_dt.strftime("%Y%m%d"):
            findings.append(
                ValidationFinding(
                    code="candidate_id_date_mismatch",
                    message=(
                        f"candidate_id date {candidate_date!r} does not match "
                        "identity_freeze_timestamp"
                    ),
                )
            )

    source_branch = manifest.get("source_branch")
    if not isinstance(source_branch, str) or not source_branch.strip():
        findings.append(
            ValidationFinding(
                code="invalid_source_branch",
                message="source_branch must be a non-empty string",
            )
        )

    for label in ("warehouse_image_digest", "mdm_image_digest"):
        digest = manifest.get(label)
        if not isinstance(digest, str) or not _IMAGE_DIGEST_RE.fullmatch(digest):
            findings.append(
                ValidationFinding(
                    code="invalid_image_digest",
                    message=f"{label} {digest!r} is not a bare sha256 digest",
                )
            )

    disposition = manifest.get("disposition")
    if disposition is not None and (
        not isinstance(disposition, str) or disposition not in _VALID_DISPOSITIONS
    ):
        findings.append(
            ValidationFinding(
                code="invalid_disposition",
                message=(
                    f"disposition must be one of {sorted(_VALID_DISPOSITIONS)} or "
                    f"null, got {disposition!r}"
                ),
            )
        )

    watermark = manifest.get("release_data_watermark")
    expected_watermark_digest: str | None = None
    if not isinstance(watermark, dict):
        findings.append(
            ValidationFinding(
                code="invalid_type",
                message="release_data_watermark must be a JSON object",
            )
        )
    else:
        findings.extend(_validate_watermark(watermark))
        expected_watermark_digest = watermark_digest_for(watermark)

    attestations = manifest.get("attestations")
    if not isinstance(attestations, list):
        findings.append(
            ValidationFinding(
                code="invalid_type",
                message="attestations must be a JSON array",
            )
        )
    else:
        for attestation in attestations:
            findings.extend(
                _validate_attestation(
                    attestation,
                    candidate_id=candidate_id,
                    watermark_digest=expected_watermark_digest,
                    evidence_digests=_gate_attestation_digests(manifest.get("gates")),
                    as_of=as_of_utc,
                    identity_freeze=freeze_dt,
                )
            )

    gates = manifest.get("gates")
    if not isinstance(gates, list):
        findings.append(
            ValidationFinding(
                code="invalid_type",
                message="gates must be a JSON array",
            )
        )
    else:
        gate_names: set[str] = set()
        for gate in gates:
            if isinstance(gate, dict) and isinstance(gate.get("gate_name"), str):
                gate_name = gate["gate_name"]
                if gate_name in gate_names:
                    findings.append(
                        ValidationFinding(
                            code="duplicate_gate_name",
                            message=f"gate name {gate_name!r} appears more than once",
                            gate_name=gate_name,
                        )
                    )
                gate_names.add(gate_name)
            findings.extend(
                _validate_gate(
                    gate,
                    candidate_id,
                    repo_root,
                    as_of_utc,
                    freeze_dt,
                )
            )

    if not isinstance(manifest.get("addendum_references"), list):
        findings.append(
            ValidationFinding(
                code="invalid_type",
                message="addendum_references must be a JSON array",
            )
        )

    for path, secret_names in _manifest_secret_findings(manifest):
        findings.append(
            ValidationFinding(
                code="manifest_secret_found",
                message=(
                    f"manifest field {path} contains forbidden content: {secret_names}"
                ),
            )
        )

    findings.extend(
        _validate_final_disposition(
            manifest,
            candidate_id=candidate_id,
            watermark_digest=expected_watermark_digest,
            gates=gates if isinstance(gates, list) else [],
            attestations=attestations if isinstance(attestations, list) else [],
            as_of=as_of_utc,
            identity_freeze=freeze_dt,
        )
    )

    return ValidationReport(ok=(len(findings) == 0), findings=findings)


_SECRET_SCAN_EXCLUDED_KEYS = frozenset(
    {
        "candidate_id",
        "commit_sha",
        "warehouse_image_digest",
        "mdm_image_digest",
        "evidence_path",
        "evidence_sha256",
        "watermark_digest",
        "evidence_digest",
    }
)


def _manifest_secret_findings(
    value: Any,
    *,
    path: str = "$",
    key: str | None = None,
) -> list[tuple[str, list[str]]]:
    if isinstance(value, dict):
        findings: list[tuple[str, list[str]]] = []
        for child_key, child_value in value.items():
            findings.extend(
                _manifest_secret_findings(
                    child_value,
                    path=f"{path}.{child_key}",
                    key=child_key,
                )
            )
        return findings
    if isinstance(value, list):
        findings = []
        for index, child_value in enumerate(value):
            findings.extend(
                _manifest_secret_findings(
                    child_value,
                    path=f"{path}[{index}]",
                    key=key,
                )
            )
        return findings
    if isinstance(value, str) and key not in _SECRET_SCAN_EXCLUDED_KEYS:
        secret_names = scan_for_secrets(value.encode("utf-8"))
        if secret_names:
            return [(path, secret_names)]
    return []


def _gate_attestation_digests(gates: Any) -> set[str]:
    if not isinstance(gates, list):
        return set()
    return {
        f"sha256:{digest}"
        for gate in gates
        if isinstance(gate, dict)
        and isinstance((digest := gate.get("evidence_sha256")), str)
        and _EVIDENCE_DIGEST_RE.fullmatch(digest)
    }


def _validate_attestation(
    attestation: Any,
    *,
    candidate_id: str | None,
    watermark_digest: str | None,
    evidence_digests: set[str],
    as_of: datetime | None,
    identity_freeze: datetime | None,
) -> list[ValidationFinding]:
    if not isinstance(attestation, dict):
        return [
            ValidationFinding(
                code="invalid_type",
                message="each attestation must be a JSON object",
            )
        ]
    findings: list[ValidationFinding] = []
    for field in _REQUIRED_ATTESTATION_FIELDS:
        if field not in attestation or attestation[field] is None:
            findings.append(
                ValidationFinding(
                    code="incomplete_attestation",
                    message=(
                        f"attestation is missing required field {field!r}: "
                        f"{attestation!r}"
                    ),
                )
            )

    if candidate_id is not None and attestation.get("candidate_id") != candidate_id:
        findings.append(
            ValidationFinding(
                code="attestation_candidate_mismatch",
                message="attestation candidate_id does not match the manifest",
            )
        )

    recorded_watermark_digest = attestation.get("watermark_digest")
    if not isinstance(recorded_watermark_digest, str) or not _IMAGE_DIGEST_RE.fullmatch(
        recorded_watermark_digest
    ):
        findings.append(
            ValidationFinding(
                code="invalid_attestation_digest",
                message="attestation watermark_digest must be a sha256 digest",
            )
        )
    elif watermark_digest is not None and recorded_watermark_digest != watermark_digest:
        findings.append(
            ValidationFinding(
                code="attestation_watermark_mismatch",
                message="attestation watermark_digest does not match the manifest",
            )
        )

    recorded_evidence_digest = attestation.get("evidence_digest")
    if not isinstance(recorded_evidence_digest, str) or not _IMAGE_DIGEST_RE.fullmatch(
        recorded_evidence_digest
    ):
        findings.append(
            ValidationFinding(
                code="invalid_attestation_digest",
                message="attestation evidence_digest must be a sha256 digest",
            )
        )
    elif recorded_evidence_digest not in evidence_digests:
        findings.append(
            ValidationFinding(
                code="attestation_evidence_mismatch",
                message="attestation evidence_digest does not match a recorded gate",
            )
        )

    for label in ("role", "approver_handle"):
        if (
            not isinstance(attestation.get(label), str)
            or not attestation[label].strip()
        ):
            findings.append(
                ValidationFinding(
                    code="invalid_attestation",
                    message=f"attestation {label} must be a non-empty string",
                )
            )

    try:
        attested_at = _parse_utc_timestamp(
            attestation.get("attested_at"), "attestation.attested_at"
        )
        if as_of is not None and attested_at > as_of:
            findings.append(
                ValidationFinding(
                    code="attestation_from_future",
                    message="attestation timestamp is after as_of",
                )
            )
        if identity_freeze is not None and attested_at < identity_freeze:
            findings.append(
                ValidationFinding(
                    code="attestation_before_identity_freeze",
                    message="attestation timestamp is before identity_freeze_timestamp",
                )
            )
    except (TypeError, ValueError) as exc:
        findings.append(ValidationFinding(code="invalid_timestamp", message=str(exc)))
    return findings


def _validate_final_disposition(
    manifest: dict[str, Any],
    *,
    candidate_id: str | None,
    watermark_digest: str | None,
    gates: list[Any],
    attestations: list[Any],
    as_of: datetime | None,
    identity_freeze: datetime | None,
) -> list[ValidationFinding]:
    disposition = manifest.get("disposition")
    findings: list[ValidationFinding] = []
    owner_attestation = manifest.get("release_owner_attestation")
    release_seal = manifest.get("release_seal")

    if owner_attestation is not None and not isinstance(owner_attestation, dict):
        findings.append(
            ValidationFinding(
                code="invalid_final_state_field",
                message="release_owner_attestation must be null or a JSON object",
            )
        )
    if release_seal is not None and (
        not isinstance(release_seal, str) or not release_seal.strip()
    ):
        findings.append(
            ValidationFinding(
                code="invalid_final_state_field",
                message="release_seal must be null or a non-empty string",
            )
        )

    if isinstance(owner_attestation, dict):
        findings.extend(
            _validate_attestation(
                owner_attestation,
                candidate_id=candidate_id,
                watermark_digest=watermark_digest,
                evidence_digests=_gate_attestation_digests(gates),
                as_of=as_of,
                identity_freeze=identity_freeze,
            )
        )
        if owner_attestation.get("role") != "release_owner":
            findings.append(
                ValidationFinding(
                    code="incomplete_final_disposition",
                    message="release_owner_attestation must use role 'release_owner'",
                )
            )

    if (
        disposition is None
        or not isinstance(disposition, str)
        or disposition not in _VALID_DISPOSITIONS
    ):
        return findings

    if not isinstance(owner_attestation, dict):
        findings.append(
            ValidationFinding(
                code="incomplete_final_disposition",
                message="a final disposition requires a Release Owner attestation",
            )
        )
    if not isinstance(release_seal, str) or not release_seal.strip():
        findings.append(
            ValidationFinding(
                code="incomplete_final_disposition",
                message="a final disposition requires the expected Release Seal tag",
            )
        )

    if disposition != "go":
        return findings

    # Ticket 08 still owns the required-gate inventory, signer sequence, and
    # signed-tag verification. Until that contract exists, this pure module
    # cannot prove a final GO and must fail closed even when the human-reserved
    # fields are populated.
    findings.append(
        ValidationFinding(
            code="go_validation_not_implemented",
            message=(
                "final GO validation remains blocked on ticket 08's required "
                "gate inventory and verified signed Release Seal contract"
            ),
        )
    )

    valid_gates = [gate for gate in gates if isinstance(gate, dict)]
    if not valid_gates or any(gate.get("status") != "pass" for gate in valid_gates):
        findings.append(
            ValidationFinding(
                code="incomplete_final_disposition",
                message="GO requires at least one gate and every gate must pass",
            )
        )

    attested_evidence = {
        evidence_digest
        for attestation in attestations
        if isinstance(attestation, dict)
        and isinstance((evidence_digest := attestation.get("evidence_digest")), str)
    }
    missing_attestations = _gate_attestation_digests(valid_gates) - attested_evidence
    if missing_attestations:
        findings.append(
            ValidationFinding(
                code="incomplete_final_disposition",
                message="GO requires a bound human attestation for every gate",
            )
        )

    return findings


def _validate_watermark(watermark: dict[str, Any]) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for field in _REQUIRED_WATERMARK_FIELDS:
        if field not in watermark or watermark[field] is None:
            findings.append(
                ValidationFinding(
                    code="incomplete_watermark",
                    message=f"release_data_watermark is missing required field {field!r}",
                )
            )

    for field in (
        "bronze_input_manifest_digest",
        "silver_shard_manifest_digest",
    ):
        value = watermark.get(field)
        if not isinstance(value, str) or not _IMAGE_DIGEST_RE.fullmatch(value):
            findings.append(
                ValidationFinding(
                    code="invalid_watermark_field",
                    message=f"release_data_watermark.{field} must be a sha256 digest",
                )
            )

    _validate_watermark_date(
        findings,
        watermark.get("max_eligible_business_date"),
        "release_data_watermark.max_eligible_business_date",
    )
    for field in (
        "full_chain_execution_id",
        "full_chain_execution_scope",
        "mdm_publication_watermark",
    ):
        _validate_watermark_identifier(
            findings,
            watermark.get(field),
            f"release_data_watermark.{field}",
        )

    snowflake_export = watermark.get("snowflake_export")
    if not isinstance(snowflake_export, dict):
        findings.append(
            ValidationFinding(
                code="invalid_type",
                message="release_data_watermark.snowflake_export must be a JSON object",
            )
        )
    else:
        for field in _REQUIRED_SNOWFLAKE_EXPORT_FIELDS:
            if field not in snowflake_export or snowflake_export[field] is None:
                findings.append(
                    ValidationFinding(
                        code="incomplete_watermark",
                        message=(
                            f"release_data_watermark.snowflake_export is missing "
                            f"required field {field!r}"
                        ),
                    )
                )
        _validate_watermark_identifier(
            findings,
            snowflake_export.get("run_id"),
            "release_data_watermark.snowflake_export.run_id",
        )
        _validate_watermark_date(
            findings,
            snowflake_export.get("business_date"),
            "release_data_watermark.snowflake_export.business_date",
        )
        manifest_digest = snowflake_export.get("manifest_digest")
        if not isinstance(manifest_digest, str) or not _IMAGE_DIGEST_RE.fullmatch(
            manifest_digest
        ):
            findings.append(
                ValidationFinding(
                    code="invalid_watermark_field",
                    message=(
                        "release_data_watermark.snowflake_export.manifest_digest "
                        "must be a sha256 digest"
                    ),
                )
            )

    hosted_graph = watermark.get("hosted_graph")
    if not isinstance(hosted_graph, dict):
        findings.append(
            ValidationFinding(
                code="invalid_type",
                message="release_data_watermark.hosted_graph must be a JSON object",
            )
        )
    else:
        for field in _REQUIRED_HOSTED_GRAPH_FIELDS:
            if field not in hosted_graph or hosted_graph[field] is None:
                findings.append(
                    ValidationFinding(
                        code="incomplete_watermark",
                        message=(
                            f"release_data_watermark.hosted_graph is missing "
                            f"required field {field!r}"
                        ),
                    )
                )
        for field in _REQUIRED_HOSTED_GRAPH_FIELDS:
            _validate_watermark_identifier(
                findings,
                hosted_graph.get(field),
                f"release_data_watermark.hosted_graph.{field}",
            )

    return findings


def _validate_watermark_identifier(
    findings: list[ValidationFinding],
    value: Any,
    path: str,
) -> None:
    if not isinstance(value, str) or not value.strip():
        findings.append(
            ValidationFinding(
                code="invalid_watermark_field",
                message=f"{path} must be a non-empty string",
            )
        )


def _validate_watermark_date(
    findings: list[ValidationFinding],
    value: Any,
    path: str,
) -> None:
    if not isinstance(value, str):
        valid = False
    else:
        try:
            date.fromisoformat(value)
            valid = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
        except ValueError:
            valid = False
    if not valid:
        findings.append(
            ValidationFinding(
                code="invalid_watermark_field",
                message=f"{path} must be a valid YYYY-MM-DD date",
            )
        )


def _validate_gate(
    gate: Any,
    candidate_id: str | None,
    repo_root: Path,
    as_of: datetime | None,
    identity_freeze: datetime | None,
) -> list[ValidationFinding]:
    if not isinstance(gate, dict):
        return [
            ValidationFinding(
                code="invalid_type",
                message="each gate must be a JSON object",
            )
        ]
    findings: list[ValidationFinding] = []
    raw_gate_name = gate.get("gate_name")
    gate_name = raw_gate_name if isinstance(raw_gate_name, str) else None

    for field in _REQUIRED_GATE_FIELDS:
        if field not in gate or gate[field] is None:
            findings.append(
                ValidationFinding(
                    code="incomplete_gate",
                    message=f"gate is missing required field {field!r}",
                    gate_name=gate_name,
                )
            )

    status = gate.get("status")
    if not isinstance(status, str) or status not in _VALID_GATE_STATUSES:
        findings.append(
            ValidationFinding(
                code="invalid_gate_status",
                message=f"gate status must be one of {sorted(_VALID_GATE_STATUSES)}",
                gate_name=gate_name,
            )
        )

    for field in (
        "gate_name",
        "media_type",
        "capture_tool",
        "capture_tool_version",
    ):
        value = gate.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(
                ValidationFinding(
                    code="invalid_gate_metadata",
                    message=f"gate {field} must be a non-empty string",
                    gate_name=gate_name,
                )
            )

    recorded_digest = gate.get("evidence_sha256")
    if not isinstance(recorded_digest, str) or not _EVIDENCE_DIGEST_RE.fullmatch(
        recorded_digest
    ):
        findings.append(
            ValidationFinding(
                code="invalid_evidence_digest",
                message="gate evidence_sha256 must be 64 lowercase hex characters",
                gate_name=gate_name,
            )
        )

    if gate.get("sanitization") != {"scanned": True, "findings": []}:
        findings.append(
            ValidationFinding(
                code="invalid_sanitization",
                message="gate sanitization must record a clean completed scan",
                gate_name=gate_name,
            )
        )

    evidence_path = gate.get("evidence_path")
    if (
        not isinstance(evidence_path, str)
        or not evidence_path
        or "\x00" in evidence_path
    ):
        findings.append(
            ValidationFinding(
                code="invalid_evidence_path",
                message="gate evidence_path must be a non-empty path string",
                gate_name=gate_name,
            )
        )
        return findings

    evidence_relpath = PurePosixPath(evidence_path)
    expected_prefix = (
        PurePosixPath(_candidate_evidence_prefix(candidate_id))
        if candidate_id is not None
        else None
    )
    lexical_lineage_ok = (
        expected_prefix is not None
        and not evidence_relpath.is_absolute()
        and ".." not in evidence_relpath.parts
        and evidence_relpath.parts[: len(expected_prefix.parts)]
        == expected_prefix.parts
        and len(evidence_relpath.parts) > len(expected_prefix.parts)
    )
    candidate_root_path = (
        repo_root / expected_prefix if expected_prefix is not None else None
    )
    try:
        candidate_root = (
            candidate_root_path.resolve() if candidate_root_path is not None else None
        )
        full_path = (repo_root / evidence_path).resolve()
        resolved_lineage_ok = (
            candidate_root is not None
            and full_path.is_relative_to(candidate_root)
            and candidate_root_path is not None
            and not _path_contains_symlink(repo_root, candidate_root_path)
            and not _path_contains_symlink(repo_root, repo_root / evidence_path)
        )
    except (OSError, RuntimeError, ValueError):
        resolved_lineage_ok = False
        full_path = repo_root / evidence_path
    if not lexical_lineage_ok or not resolved_lineage_ok:
        findings.append(
            ValidationFinding(
                code="gate_evidence_path_lineage_violation",
                message=(
                    f"evidence path {evidence_path!r} is not under candidate "
                    f"{candidate_id!r}'s own evidence directory"
                ),
                gate_name=gate_name,
            )
        )
        return findings
    if not full_path.exists():
        findings.append(
            ValidationFinding(
                code="evidence_file_missing",
                message=f"evidence file {evidence_path!r} does not exist on disk",
                gate_name=gate_name,
            )
        )
        return findings

    try:
        on_disk_bytes = full_path.read_bytes()
    except OSError as exc:
        findings.append(
            ValidationFinding(
                code="evidence_file_unreadable",
                message=f"evidence file {evidence_path!r} could not be read: {exc}",
                gate_name=gate_name,
            )
        )
        return findings
    on_disk_digest = sha256_hex(on_disk_bytes)
    if recorded_digest is not None and on_disk_digest != recorded_digest:
        findings.append(
            ValidationFinding(
                code="evidence_digest_mismatch",
                message=(
                    f"evidence file {evidence_path!r} has drifted: recorded "
                    f"sha256 {recorded_digest!r}, on-disk sha256 {on_disk_digest!r}"
                ),
                gate_name=gate_name,
            )
        )

    # Defense in depth: re-scan on-disk content regardless of digest match —
    # catches a secret introduced by a mutation that also changed the hash,
    # not just drift that happens to keep the file secret-free.
    secret_findings = scan_for_secrets(on_disk_bytes)
    if secret_findings:
        findings.append(
            ValidationFinding(
                code="secret_found",
                message=(
                    f"evidence file {evidence_path!r} contains forbidden "
                    f"content: {secret_findings}"
                ),
                gate_name=gate_name,
            )
        )

    captured_dt: datetime | None = None
    expires_dt: datetime | None = None
    try:
        captured_dt = _parse_utc_timestamp(gate.get("captured_at"), "captured_at")
    except (TypeError, ValueError) as exc:
        findings.append(
            ValidationFinding(
                code="invalid_timestamp",
                message=str(exc),
                gate_name=gate_name,
            )
        )
    try:
        expires_dt = _parse_utc_timestamp(gate.get("expires_at"), "expires_at")
    except (TypeError, ValueError) as exc:
        findings.append(
            ValidationFinding(
                code="invalid_timestamp",
                message=str(exc),
                gate_name=gate_name,
            )
        )

    if captured_dt is not None and expires_dt is not None:
        expected_expiry = captured_dt + timedelta(hours=LIVE_EVIDENCE_WINDOW_HOURS)
        if expires_dt != expected_expiry:
            findings.append(
                ValidationFinding(
                    code="invalid_evidence_window",
                    message="expires_at must be exactly 24 hours after captured_at",
                    gate_name=gate_name,
                )
            )
        if as_of is not None and captured_dt > as_of:
            findings.append(
                ValidationFinding(
                    code="evidence_from_future",
                    message="captured_at is after as_of",
                    gate_name=gate_name,
                )
            )
        if identity_freeze is not None and captured_dt < identity_freeze:
            findings.append(
                ValidationFinding(
                    code="evidence_before_identity_freeze",
                    message="captured_at is before identity_freeze_timestamp",
                    gate_name=gate_name,
                )
            )
        if as_of is not None and as_of > expires_dt:
            findings.append(
                ValidationFinding(
                    code="evidence_stale",
                    message=(
                        f"evidence for gate {gate_name!r} expired at "
                        f"{gate.get('expires_at')!r}, which is before as_of "
                        f"{as_of.isoformat()!r}"
                    ),
                    gate_name=gate_name,
                )
            )

    return findings


def _path_contains_symlink(repo_root: Path, target: Path) -> bool:
    try:
        relative = target.absolute().relative_to(repo_root.absolute())
    except ValueError:
        return True
    current = repo_root.absolute()
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return True
    return False
