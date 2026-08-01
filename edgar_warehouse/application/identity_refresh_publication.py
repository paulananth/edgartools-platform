"""Immutable manifest contract for a run-scoped Daily Identity Refresh.

The Step Functions Map owns execution of the individual CIK batches.  This
module deliberately owns only the durable contract between those batches and
the single reducer: it never selects CIKs, fetches SEC data, or publishes the
canonical database.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import (
    PromotionConflictError,
    StorageLocation,
    read_bytes,
)
from edgar_warehouse.silver_protection import merge_candidate_into_canonical

_SHA256_LENGTH = 64
_RUN_PREFIX = "identity_refresh/runs"


@dataclass(frozen=True)
class IdentityRefreshInput:
    """The immutable identity of one refresh input."""

    batch_id: str
    cik_list: tuple[int, ...]
    delta_path: str
    sha256: str


def run_manifest_path(run_id: str) -> str:
    return f"{_RUN_PREFIX}/{run_id}/run_manifest.json"


def completed_manifest_path(run_id: str) -> str:
    return f"{_RUN_PREFIX}/{run_id}/completed_manifest.json"


def reference_snapshot_path(run_id: str) -> str:
    return f"{_RUN_PREFIX}/{run_id}/reference/reference_snapshot.duckdb"


def batch_delta_path(run_id: str, batch_id: str) -> str:
    return f"{_RUN_PREFIX}/{run_id}/batches/{batch_id}/delta.duckdb"


def batch_outcome_path(run_id: str, batch_id: str) -> str:
    return f"{_RUN_PREFIX}/{run_id}/batches/{batch_id}/outcome.json"


def batch_id_for_ciks(ciks: Iterable[int]) -> str:
    """Return the deterministic identifier for one ordered CIK batch."""
    normalized = tuple(int(cik) for cik in ciks)
    if not normalized:
        raise WarehouseRuntimeError("identity refresh batch must contain at least one CIK")
    if tuple(sorted(set(normalized))) != normalized:
        raise WarehouseRuntimeError("identity refresh batch CIKs must be sorted and unique")
    return hashlib.sha256(",".join(str(cik) for cik in normalized).encode("ascii")).hexdigest()[:24]


def persist_run_manifest(
    storage_root: StorageLocation,
    *,
    run_id: str,
    image_identity: str,
    reference_snapshot_file: Path,
    batches: Iterable[Iterable[int]],
) -> dict[str, Any]:
    """Persist the immutable run plan and its one reference snapshot.

    The plan intentionally records only declarations. Batch outcomes are
    separate immutable objects, so retrying a failed batch cannot rewrite a
    successful sibling or weaken the original selected universe.
    """
    if not image_identity:
        raise WarehouseRuntimeError("identity refresh requires an immutable warehouse image identity")
    if not reference_snapshot_file.exists():
        raise WarehouseRuntimeError(f"identity refresh reference snapshot is missing: {reference_snapshot_file}")
    declared_batches = [tuple(int(cik) for cik in batch) for batch in batches]
    snapshot_payload = reference_snapshot_file.read_bytes()
    snapshot_relative = reference_snapshot_path(run_id)
    storage_root.write_immutable_bytes(snapshot_relative, snapshot_payload)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "image_identity": image_identity,
        "reference_snapshot": {
            "path": snapshot_relative,
            "sha256": _sha256(snapshot_payload),
        },
        "batches": [
            {"batch_id": batch_id_for_ciks(ciks), "ciks": list(ciks), "outcome_path": batch_outcome_path(run_id, batch_id_for_ciks(ciks))}
            for ciks in declared_batches
        ],
    }
    storage_root.write_immutable_bytes(
        run_manifest_path(run_id), _json_bytes(manifest)
    )
    return manifest


def persist_batch_outcome(
    storage_root: StorageLocation,
    *,
    run_id: str,
    image_identity: str,
    ciks: Iterable[int],
    delta_file: Path,
) -> dict[str, Any]:
    """Persist a batch delta and its immutable success declaration."""
    normalized = tuple(int(cik) for cik in ciks)
    batch_id = batch_id_for_ciks(normalized)
    if not delta_file.exists():
        raise WarehouseRuntimeError(f"identity refresh batch delta is missing: {delta_file}")
    payload = delta_file.read_bytes()
    delta_relative = batch_delta_path(run_id, batch_id)
    storage_root.write_immutable_bytes(delta_relative, payload)
    outcome = {
        "schema_version": 1,
        "run_id": run_id,
        "image_identity": image_identity,
        "batch_id": batch_id,
        "ciks": list(normalized),
        "status": "succeeded",
        "delta_path": delta_relative,
        "sha256": _sha256(payload),
    }
    storage_root.write_immutable_bytes(batch_outcome_path(run_id, batch_id), _json_bytes(outcome))
    return outcome


def load_complete_run_manifest(
    storage_root: StorageLocation, *, run_id: str, image_identity: str
) -> dict[str, Any]:
    """Combine immutable plan and outcomes, rejecting anything incomplete."""
    manifest = _read_json(storage_root, run_manifest_path(run_id))
    if manifest.get("run_id") != run_id or manifest.get("image_identity") != image_identity:
        raise WarehouseRuntimeError("identity refresh run manifest does not bind this reducer identity")
    declared = manifest.get("batches")
    if not isinstance(declared, list):
        raise WarehouseRuntimeError("identity refresh run manifest batches must be a list")
    outcomes: list[dict[str, Any]] = []
    for expected in declared:
        if not isinstance(expected, Mapping):
            raise WarehouseRuntimeError("identity refresh declared batch must be an object")
        expected_id = str(expected.get("batch_id") or "")
        expected_ciks = tuple(int(cik) for cik in expected.get("ciks") or ())
        if expected_id != batch_id_for_ciks(expected_ciks):
            raise WarehouseRuntimeError("identity refresh declared batch has invalid CIK identity")
        outcome = _read_json(storage_root, str(expected.get("outcome_path") or ""))
        if outcome.get("run_id") != run_id or outcome.get("image_identity") != image_identity:
            raise WarehouseRuntimeError("identity refresh batch outcome is bound to a different run or image")
        if outcome.get("batch_id") != expected_id or tuple(int(c) for c in outcome.get("ciks") or ()) != expected_ciks:
            raise WarehouseRuntimeError("identity refresh batch outcome does not match the declared batch")
        outcomes.append(outcome)
    return {**manifest, "batches": outcomes}


def reduce_identity_refresh(
    storage_root: StorageLocation,
    *,
    run_id: str,
    image_identity: str,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Merge one verified run and perform exactly one promotion per attempt.

    Promotion conflicts repeat this reducer only. The immutable deltas are
    read and checksummed again on every attempt; no capture function is called
    from this module.
    """
    if max_attempts < 1:
        raise WarehouseRuntimeError("identity refresh reducer max_attempts must be positive")
    manifest = load_complete_run_manifest(storage_root, run_id=run_id, image_identity=image_identity)
    inputs = validate_complete_run_manifest(manifest, expected_run_id=run_id, expected_image_identity=image_identity)
    reference = manifest["reference_snapshot"]
    _read_verified(storage_root, str(reference["path"]), str(reference["sha256"]))
    for item in inputs:
        _read_verified(storage_root, item.delta_path, item.sha256)

    canonical_relative = "silver/sec/silver.duckdb"
    for attempt in range(1, max_attempts + 1):
        baseline = storage_root.read_object_version(canonical_relative)
        try:
            with tempfile.TemporaryDirectory(prefix="identity-refresh-reducer-") as tmp:
                tmp_path = Path(tmp)
                current = tmp_path / "canonical.duckdb"
                if baseline.exists:
                    current.write_bytes(read_bytes(storage_root.join(canonical_relative)))
                    candidates = [("reference", str(reference["path"]))] + [(item.batch_id, item.delta_path) for item in inputs]
                else:
                    current.write_bytes(_read_verified(storage_root, str(reference["path"]), str(reference["sha256"])))
                    candidates = [(item.batch_id, item.delta_path) for item in inputs]
                merge_order: list[str] = []
                tables_merged: list[str] = []
                for index, (label, relative) in enumerate(candidates):
                    candidate = tmp_path / f"candidate-{index}.duckdb"
                    expected_sha = str(reference["sha256"]) if label == "reference" else next(item.sha256 for item in inputs if item.batch_id == label)
                    candidate.write_bytes(_read_verified(storage_root, relative, expected_sha))
                    merged = tmp_path / f"merged-{index}.duckdb"
                    result = merge_candidate_into_canonical(candidate, current, merged)
                    current = merged
                    merge_order.append(label)
                    tables_merged.extend(result.tables_merged)
                payload = current.read_bytes()
            staged_relative = storage_root.write_staged_bytes(canonical_relative, payload)
            promotion = storage_root.promote_staged(staged_relative, canonical_relative, expected_etag=baseline.etag)
        except PromotionConflictError:
            if attempt == max_attempts:
                raise
            continue
        completed = {
            **manifest,
            "status": "succeeded",
            "reducer": {
                "attempt": attempt,
                "max_attempts": max_attempts,
                "canonical_promotion_count": 1,
                "baseline_etag": baseline.etag,
                "result_etag": promotion.new_version.etag,
                "merge_order": merge_order,
                "tables_merged": tables_merged,
                "staged_path": staged_relative,
            },
        }
        storage_root.write_immutable_bytes(completed_manifest_path(run_id), _json_bytes(completed))
        return completed
    raise AssertionError("unreachable")


def validate_complete_run_manifest(
    manifest: Mapping[str, Any], *, expected_run_id: str, expected_image_identity: str | None = None
) -> tuple[IdentityRefreshInput, ...]:
    """Validate a completed run before the reducer may read any delta.

    The manifest is intentionally strict: a missing or failed batch is not a
    recoverable reducer condition.  Batch repair must happen before this
    function is called, under the same immutable run identity.
    """
    if manifest.get("run_id") != expected_run_id:
        raise WarehouseRuntimeError("identity refresh manifest run_id does not match reducer run_id")
    image_identity = str(manifest.get("image_identity") or "")
    if not image_identity:
        raise WarehouseRuntimeError("identity refresh manifest has no image_identity")
    if expected_image_identity is not None and image_identity != expected_image_identity:
        raise WarehouseRuntimeError("identity refresh manifest image_identity does not match reducer image")
    reference = manifest.get("reference_snapshot")
    if not isinstance(reference, Mapping) or not _valid_sha256(reference.get("sha256")):
        raise WarehouseRuntimeError("identity refresh manifest has no valid reference snapshot")
    if not str(reference.get("path") or ""):
        raise WarehouseRuntimeError("identity refresh reference snapshot has no path")
    batches = manifest.get("batches")
    if not isinstance(batches, list):
        raise WarehouseRuntimeError("identity refresh manifest batches must be a list")

    inputs: list[IdentityRefreshInput] = []
    seen_batch_ids: set[str] = set()
    seen_ciks: set[int] = set()
    for batch in batches:
        if not isinstance(batch, Mapping):
            raise WarehouseRuntimeError("identity refresh manifest batch must be an object")
        if batch.get("status") != "succeeded":
            raise WarehouseRuntimeError("identity refresh manifest is incomplete or contains a failed batch")
        ciks = tuple(int(cik) for cik in batch.get("ciks") or ())
        batch_id = str(batch.get("batch_id") or "")
        if batch_id != batch_id_for_ciks(ciks):
            raise WarehouseRuntimeError("identity refresh batch_id does not match its CIK list")
        if batch_id in seen_batch_ids or seen_ciks.intersection(ciks):
            raise WarehouseRuntimeError("identity refresh manifest contains duplicate batch or CIK input")
        if not _valid_sha256(batch.get("sha256")) or not str(batch.get("delta_path") or ""):
            raise WarehouseRuntimeError("identity refresh batch lacks immutable delta identity")
        seen_batch_ids.add(batch_id)
        seen_ciks.update(ciks)
        inputs.append(IdentityRefreshInput(batch_id, ciks, str(batch["delta_path"]), str(batch["sha256"])))
    return tuple(inputs)


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_LENGTH and all(ch in "0123456789abcdef" for ch in value)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_verified(storage_root: StorageLocation, relative: str, expected_sha256: str) -> bytes:
    if not _valid_sha256(expected_sha256):
        raise WarehouseRuntimeError("identity refresh input has invalid checksum")
    payload = read_bytes(storage_root.join(relative))
    if _sha256(payload) != expected_sha256:
        raise WarehouseRuntimeError(f"identity refresh checksum mismatch for {relative}")
    return payload


def _read_json(storage_root: StorageLocation, relative: str) -> dict[str, Any]:
    if not relative:
        raise WarehouseRuntimeError("identity refresh immutable object path is missing")
    try:
        value = json.loads(read_bytes(storage_root.join(relative)).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WarehouseRuntimeError(f"identity refresh object is not valid JSON: {relative}") from exc
    if not isinstance(value, dict):
        raise WarehouseRuntimeError(f"identity refresh object is not a JSON object: {relative}")
    return value


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
