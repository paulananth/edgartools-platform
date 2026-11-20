"""Bounded, credential-free operations for exposure publication and parity."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling exposure scripts

from datetime import datetime, timezone
from typing import Any, Callable

from exposure_manifest import validate_manifest
from exposure_parity import check_parity

MAX_MANIFEST_AGE_S = 24 * 60 * 60

class ExposureRunError(RuntimeError):
    """A bounded exposure run failed before uncontrolled publication."""


def run_exposure_cycle(
    manifest: dict[str, Any],
    *,
    manifest_created_at: datetime,
    target: dict[str, Any],
    now: datetime | None = None,
    ingest: Callable[[dict[str, Any]], dict[str, Any]],
    publish: Callable[[dict[str, Any]], dict[str, Any]],
    snapshots: Callable[[dict[str, Any]], dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Run ingestion, publication, and parity as one bounded fail-closed cycle. `target` is the non-secret target and approval
    contract the caller reads from configuration; the receipt repeats it."""
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
        "target": dict(target),
    }
