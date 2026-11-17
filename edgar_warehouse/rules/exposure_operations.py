"""Bounded, credential-free operations for exposure publication and parity."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from edgar_warehouse.rules.exposure_manifest import validate_manifest
from edgar_warehouse.rules.exposure_parity import check_parity

MAX_MANIFEST_AGE_S = 24 * 60 * 60
PRODUCTION_POLICY = {
    "target": "EDGARTOOLS_PROD",
    "role": "EDGARTOOLS_PROD_READER",
    "scope": ["EDGARTOOLS_GOLD", "EDGARTOOLS_SILVER"],
    "approval_gate": "operator-approved production run",
}


class ExposureRunError(RuntimeError):
    """A bounded exposure run failed before uncontrolled publication."""


def production_policy() -> dict[str, Any]:
    """Return the non-secret production target and approval contract."""
    return {**PRODUCTION_POLICY, "scope": list(PRODUCTION_POLICY["scope"])}


def run_exposure_cycle(
    manifest: dict[str, Any],
    *,
    manifest_created_at: datetime,
    now: datetime | None = None,
    ingest: Callable[[dict[str, Any]], dict[str, Any]],
    publish: Callable[[dict[str, Any]], dict[str, Any]],
    snapshots: Callable[[dict[str, Any]], dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Run ingestion, publication, and parity as one bounded fail-closed cycle."""
    validate_manifest(manifest)
    current = now or datetime.now(timezone.utc)
    created = manifest_created_at.astimezone(timezone.utc)
    age = (current - created).total_seconds()
    if age < 0 or age > MAX_MANIFEST_AGE_S:
        raise ExposureRunError("manifest is stale or has a future timestamp; regenerate before running")

    try:
        ingestion = ingest(manifest)
        publication = publish(manifest)
        captured = snapshots(manifest)
        parity = check_parity(manifest, **captured)
    except Exception as error:
        raise ExposureRunError("exposure cycle failed; no success receipt was produced") from error
    if not parity["ok"]:
        raise ExposureRunError("exposure parity failed; do not promote or schedule this manifest")
    return {
        "ok": True,
        "manifest_digest": manifest["digest"],
        "manifest_age_seconds": age,
        "ingestion": {"ok": bool(ingestion.get("ok", True))},
        "publication": {"ok": bool(publication.get("ok", True))},
        "parity": {"ok": True, "mismatch_count": 0},
        "target": production_policy(),
    }
