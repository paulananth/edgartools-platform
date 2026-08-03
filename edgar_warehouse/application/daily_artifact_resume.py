"""Durable, run-scoped recovery contract for recurring filing artifacts.

The manifest is intentionally small and immutable.  Successful candidates get
one immutable terminal marker; a retry reuses that exact manifest and therefore
does not refetch them.  Immutable-content conflicts get a distinct terminal
repair marker and remain fail-closed until an operator supplies a matching
repair attestation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application.relationship_bulk_load import (
    sanitize_accession_for_path,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes

_PREFIX = "daily_artifact/runs"


def manifest_path(run_id: str) -> str:
    return f"{_PREFIX}/{run_id}/run_manifest.json"


def _outcome_path(run_id: str, accession: str, status: str) -> str:
    return f"{_PREFIX}/{run_id}/outcomes/{sanitize_accession_for_path(accession)}/{status}.json"


def repair_attestation_path(run_id: str, accession: str) -> str:
    return f"{_PREFIX}/{run_id}/repairs/{sanitize_accession_for_path(accession)}.json"


def prepare_resume(
    storage: StorageLocation,
    *,
    run_id: str,
    image_identity: str,
    daily_index_accessions: Iterable[str],
    selected_accessions: Iterable[str],
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Persist/validate the original manifest and return candidates still runnable.

    A terminal repair marker is deliberately not runnable until a separately
    immutable attestation binds the same run, accession and conflict evidence.
    """
    selected = sorted({str(value) for value in selected_accessions})
    index = sorted({str(value) for value in daily_index_accessions})
    if not image_identity:
        raise WarehouseRuntimeError("daily artifact resume requires WAREHOUSE_IMAGE_REF")
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "image_identity": image_identity,
        "daily_index_accessions": index,
        "daily_index_accession_digest": _digest(index),
        "selected_accessions": selected,
        "selected_accession_digest": _digest(selected),
    }
    try:
        storage.write_immutable_bytes(manifest_path(run_id), _json_bytes(manifest))
    except WarehouseRuntimeError as exc:
        if "already exists with different content" not in str(exc):
            raise
        raise WarehouseRuntimeError("daily artifact run manifest identity drift") from exc
    persisted = _read_json(storage, manifest_path(run_id))
    if persisted != manifest:
        raise WarehouseRuntimeError("daily artifact run manifest identity drift")

    outcome_statuses = _list_outcome_statuses(storage, run_id)
    pending: list[str] = []
    repair_required: list[str] = []
    for accession in selected:
        statuses = outcome_statuses.get(sanitize_accession_for_path(accession), frozenset())
        if "succeeded" in statuses:
            continue
        if "terminal_repair_required" in statuses and not _valid_repair_attestation(storage, run_id, accession, manifest):
            repair_required.append(accession)
            continue
        pending.append(accession)
    return pending, repair_required, manifest


def record_succeeded(storage: StorageLocation, *, run_id: str, accession: str, manifest: Mapping[str, Any]) -> None:
    _write_outcome(storage, run_id=run_id, accession=accession, status="succeeded", manifest=manifest)


def record_terminal_repair(
    storage: StorageLocation, *, run_id: str, accession: str, manifest: Mapping[str, Any], error_type: str, error: str
) -> None:
    _write_outcome(
        storage, run_id=run_id, accession=accession, status="terminal_repair_required", manifest=manifest,
        extra={"error_type": error_type, "error_fingerprint": hashlib.sha256(error.encode("utf-8")).hexdigest()},
    )


def record_repair_attestation(
    storage: StorageLocation, *, run_id: str, accession: str, manifest: Mapping[str, Any],
    operator_identity: str, repair_action: str, conflict_evidence: Mapping[str, Any],
) -> None:
    """Persist the explicit operator authorization required before replay."""
    if not operator_identity or not repair_action or not conflict_evidence:
        raise WarehouseRuntimeError("daily artifact repair attestation is incomplete")
    payload = {
        "schema_version": 1, "run_id": run_id, "accession_number": accession,
        "manifest_digest": _digest(manifest["selected_accessions"]),
        "operator_identity": operator_identity, "repair_action": repair_action,
        "conflict_evidence": dict(conflict_evidence),
    }
    storage.write_immutable_bytes(repair_attestation_path(run_id, accession), _json_bytes(payload))


def _write_outcome(storage: StorageLocation, *, run_id: str, accession: str, status: str, manifest: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> None:
    payload = {"schema_version": 1, "run_id": run_id, "accession_number": accession, "status": status,
               "manifest_digest": _digest(manifest["selected_accessions"]), **dict(extra or {})}
    storage.write_immutable_bytes(_outcome_path(run_id, accession, status), _json_bytes(payload))


def _valid_repair_attestation(storage: StorageLocation, run_id: str, accession: str, manifest: Mapping[str, Any]) -> bool:
    try:
        payload = _read_json(storage, repair_attestation_path(run_id, accession))
    except WarehouseRuntimeError:
        return False
    return (payload.get("run_id") == run_id and payload.get("accession_number") == accession
            and payload.get("manifest_digest") == _digest(manifest["selected_accessions"])
            and bool(payload.get("operator_identity")) and bool(payload.get("repair_action"))
            and bool(payload.get("conflict_evidence")))


def _list_outcome_statuses(storage: StorageLocation, run_id: str) -> dict[str, set[str]]:
    """Batched existence check: one storage listing instead of two GetObjects per candidate.

    Only the outcome path shape (accession segment, status filename) is needed
    to answer "does this outcome exist" -- content is never read here.
    """
    matches = storage.find_existing(f"{_PREFIX}/{run_id}/outcomes/*/*.json")
    statuses_by_accession: dict[str, set[str]] = {}
    for match in matches:
        parts = match.replace("\\", "/").rstrip("/").split("/")
        status = parts[-1].removesuffix(".json")
        accession_segment = parts[-2]
        statuses_by_accession.setdefault(accession_segment, set()).add(status)
    return statuses_by_accession


def _read_json(storage: StorageLocation, relative: str) -> dict[str, Any]:
    try:
        value = json.loads(read_bytes(storage.join(relative)).decode("utf-8"))
    except Exception as exc:  # provider-specific not-found errors are intentionally normalized.
        raise WarehouseRuntimeError(f"daily artifact ledger object unavailable: {relative}") from exc
    if not isinstance(value, dict):
        raise WarehouseRuntimeError(f"daily artifact ledger object is not JSON: {relative}")
    return value


def _digest(values: Iterable[str]) -> str:
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
