"""Immutable manifest contract for a run-scoped Daily Identity Refresh.

The Step Functions Map owns execution of the individual CIK batches.  This
module deliberately owns only the durable contract between those batches and
the single reducer: it never selects CIKs, fetches SEC data, or publishes the
canonical database.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes

_SHA256_LENGTH = 64
_RUN_PREFIX = "identity_refresh/runs"


def _emit_reducer_event(event: str, *, run_id: str, **fields: Any) -> None:
    """Structured per-stage log event for `reduce_identity_refresh`, matching
    this codebase's existing `event`-keyed JSON logging convention (e.g.
    source_dimensional_export.py's gold_table_started/completed, silver_protection.py's
    silver_table_merge_started/silver_table_merged). Before this, the
    reducer emitted zero output for its entire runtime -- a real prod
    ReduceIdentityRefresh task ran 17+ minutes with `describe-log-streams`
    reporting storedBytes: 0, indistinguishable from hung without reading
    the source. Printed to stderr (not stdout) so it never collides with
    reduce_identity_refresh.py's single final stdout JSON result line.
    """
    print(json.dumps({"event": event, "run_id": run_id, **fields}), file=sys.stderr, flush=True)


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
    """Validate every declared batch succeeded; no longer merges/promotes.

    DuckDB Retirement Cutover Ticket 10: canonical ``silver/sec/silver.duckdb``
    is no longer a write target for any command (see warehouse_orchestrator.py's
    ``_publish_silver_database_if_remote`` docstring). This reducer used to be
    a second, independent write path to that same canonical object --
    structurally identical to the monolith merge/stage/promote cycle, just
    built to survive 20-way concurrent identity-batch writers without a
    shared-object promotion race. That race can no longer happen once nothing
    promotes, so the merge/stage/promote body (and its
    ``PromotionConflictError`` retry loop) is retired with it.

    The manifest-completeness gate is kept: ``daily_incremental``'s
    ``PublishCompanyIdentityUpdates`` state still waits on this call, and
    "every declared batch actually succeeded" is a real, still-meaningful
    fan-out-failure signal even though there is nothing left to merge on
    success -- ``load_complete_run_manifest``/``validate_complete_run_manifest``
    still raise on any missing/failed/tampered batch, exactly as before.
    ``max_attempts`` is accepted for call-site compatibility (the CLI still
    passes it) but is no longer used -- retrying existed only to survive a
    lost canonical-promotion race.
    """
    manifest = load_complete_run_manifest(storage_root, run_id=run_id, image_identity=image_identity)
    validate_complete_run_manifest(manifest, expected_run_id=run_id, expected_image_identity=image_identity)
    _emit_reducer_event("identity_refresh_validated_no_publish", run_id=run_id)
    completed = {
        **manifest,
        "status": "succeeded",
        "reducer": {
            "canonical_promotion_count": 0,
            "note": "duckdb_write_path_retired",
        },
    }
    storage_root.write_immutable_bytes(completed_manifest_path(run_id), _json_bytes(completed))
    return completed


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
