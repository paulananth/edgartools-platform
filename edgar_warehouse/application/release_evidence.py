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
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# Ticket 01's Answer: "Live production evidence must ... remain within the
# 24-hour Live-Evidence Window." A fixed invariant, not an operator-adjustable
# knob — add_gate takes no expiry-hours argument.
LIVE_EVIDENCE_WINDOW_HOURS = 24

_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

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
    ("ecr_registry_host", re.compile(rb"\b\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com\b")),
    ("postgres_dsn", re.compile(rb"\bpostgres(?:ql)?://")),
    (
        "snowflake_account_locator",
        re.compile(rb"\b[A-Z]{6,}-[A-Z0-9]{6,}\b"),
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


# ---------------------------------------------------------------------------
# Candidate identity
# ---------------------------------------------------------------------------


def candidate_id_for(commit_sha: str, date_stamp: str) -> str:
    """Build ``rc-<YYYYMMDD>-<12-char-commit>`` per ticket 01's Answer."""
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
    if manifest.get("disposition") is not None:
        raise IdentityFrozenError(
            "candidate already has a final disposition; no further gates "
            "may be added"
        )

    if status not in _VALID_GATE_STATUSES:
        raise GateRejectedError(
            f"status must be one of {sorted(_VALID_GATE_STATUSES)}, got {status!r}"
        )

    if any(gate["gate_name"] == gate_name for gate in manifest["gates"]):
        raise GateRejectedError(
            f"gate {gate_name!r} already recorded; the manifest is append-only "
            "and gate names must be distinct"
        )

    expected_prefix = _candidate_evidence_prefix(manifest["candidate_id"])
    if not evidence_relpath.startswith(expected_prefix):
        raise LineageError(
            f"evidence path {evidence_relpath!r} is not under this candidate's "
            f"own evidence directory ({expected_prefix!r})"
        )

    findings = scan_for_secrets(evidence_bytes)
    if findings:
        raise SanitizationError(
            f"evidence for gate {gate_name!r} contains forbidden content: {findings}"
        )

    captured_dt = datetime.fromisoformat(captured_at)
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

    for field in _REQUIRED_TOP_LEVEL_FIELDS:
        if field not in manifest:
            findings.append(
                ValidationFinding(
                    code="missing_field",
                    message=f"manifest is missing required field {field!r}",
                )
            )

    candidate_id = manifest.get("candidate_id")
    commit_sha = manifest.get("commit_sha")
    if candidate_id and commit_sha:
        expected_tail = commit_sha[:12]
        actual_tail = candidate_id.rsplit("-", 1)[-1]
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

    for label in ("warehouse_image_digest", "mdm_image_digest"):
        digest = manifest.get(label)
        if digest and not _IMAGE_DIGEST_RE.match(digest):
            findings.append(
                ValidationFinding(
                    code="invalid_image_digest",
                    message=f"{label} {digest!r} is not a bare sha256 digest",
                )
            )

    disposition = manifest.get("disposition")
    if disposition is not None and disposition not in _VALID_DISPOSITIONS:
        findings.append(
            ValidationFinding(
                code="invalid_disposition",
                message=(
                    f"disposition must be one of {sorted(_VALID_DISPOSITIONS)} or "
                    f"null, got {disposition!r}"
                ),
            )
        )

    for attestation in manifest.get("attestations", []):
        findings.extend(_validate_attestation(attestation))

    watermark = manifest.get("release_data_watermark")
    if watermark is not None:
        findings.extend(_validate_watermark(watermark))

    for gate in manifest.get("gates", []):
        findings.extend(_validate_gate(gate, candidate_id, repo_root, as_of))

    return ValidationReport(ok=(len(findings) == 0), findings=findings)


def _validate_attestation(attestation: dict[str, Any]) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for field in _REQUIRED_ATTESTATION_FIELDS:
        if field not in attestation:
            findings.append(
                ValidationFinding(
                    code="incomplete_attestation",
                    message=(
                        f"attestation is missing required field {field!r}: "
                        f"{attestation!r}"
                    ),
                )
            )
    return findings


def _validate_watermark(watermark: dict[str, Any]) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for field in _REQUIRED_WATERMARK_FIELDS:
        if field not in watermark:
            findings.append(
                ValidationFinding(
                    code="incomplete_watermark",
                    message=f"release_data_watermark is missing required field {field!r}",
                )
            )

    snowflake_export = watermark.get("snowflake_export")
    if isinstance(snowflake_export, dict):
        for field in _REQUIRED_SNOWFLAKE_EXPORT_FIELDS:
            if field not in snowflake_export:
                findings.append(
                    ValidationFinding(
                        code="incomplete_watermark",
                        message=(
                            f"release_data_watermark.snowflake_export is missing "
                            f"required field {field!r}"
                        ),
                    )
                )

    hosted_graph = watermark.get("hosted_graph")
    if isinstance(hosted_graph, dict):
        for field in _REQUIRED_HOSTED_GRAPH_FIELDS:
            if field not in hosted_graph:
                findings.append(
                    ValidationFinding(
                        code="incomplete_watermark",
                        message=(
                            f"release_data_watermark.hosted_graph is missing "
                            f"required field {field!r}"
                        ),
                    )
                )

    return findings


def _validate_gate(
    gate: dict[str, Any],
    candidate_id: str | None,
    repo_root: Path,
    as_of: datetime,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    gate_name = gate.get("gate_name")

    for field in _REQUIRED_GATE_FIELDS:
        if field not in gate:
            findings.append(
                ValidationFinding(
                    code="incomplete_gate",
                    message=f"gate is missing required field {field!r}",
                    gate_name=gate_name,
                )
            )

    evidence_path = gate.get("evidence_path")
    if evidence_path is None:
        return findings

    if candidate_id is not None and not evidence_path.startswith(
        _candidate_evidence_prefix(candidate_id)
    ):
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

    full_path = repo_root / evidence_path
    if not full_path.exists():
        findings.append(
            ValidationFinding(
                code="evidence_file_missing",
                message=f"evidence file {evidence_path!r} does not exist on disk",
                gate_name=gate_name,
            )
        )
        return findings

    on_disk_bytes = full_path.read_bytes()
    recorded_digest = gate.get("evidence_sha256")
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

    expires_at = gate.get("expires_at")
    if expires_at is not None:
        expires_dt = datetime.fromisoformat(expires_at)
        if as_of > expires_dt:
            findings.append(
                ValidationFinding(
                    code="evidence_stale",
                    message=(
                        f"evidence for gate {gate_name!r} expired at "
                        f"{expires_at!r}, which is before as_of {as_of.isoformat()!r}"
                    ),
                    gate_name=gate_name,
                )
            )

    return findings
