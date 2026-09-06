from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application.identity_refresh_publication import (
    batch_id_for_ciks,
    completed_manifest_path,
    persist_batch_outcome,
    persist_run_manifest,
    reduce_identity_refresh,
    validate_complete_run_manifest,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _manifest(*, batch_status: str = "succeeded", image: str = "sha256:image") -> dict:
    ciks = [100, 200]
    return {
        "run_id": "run-1",
        "image_identity": image,
        "reference_snapshot": {"path": "reference.duckdb", "sha256": _sha("reference")},
        "batches": [{
            "batch_id": batch_id_for_ciks(ciks), "ciks": ciks, "status": batch_status,
            "delta_path": "batch.duckdb", "sha256": _sha("batch"),
        }],
    }


def test_complete_manifest_returns_inputs_in_declared_order() -> None:
    inputs = validate_complete_run_manifest(_manifest(), expected_run_id="run-1", expected_image_identity="sha256:image")
    assert [(item.batch_id, item.cik_list) for item in inputs] == [(batch_id_for_ciks([100, 200]), (100, 200))]


def test_partial_or_failed_manifest_cannot_reach_reducer() -> None:
    with pytest.raises(WarehouseRuntimeError, match="incomplete"):
        validate_complete_run_manifest(_manifest(batch_status="failed"), expected_run_id="run-1")


def test_reducer_rejects_changed_run_or_image_identity() -> None:
    with pytest.raises(WarehouseRuntimeError, match="run_id"):
        validate_complete_run_manifest(_manifest(), expected_run_id="other")
    with pytest.raises(WarehouseRuntimeError, match="image_identity"):
        validate_complete_run_manifest(_manifest(), expected_run_id="run-1", expected_image_identity="sha256:other")


def test_batch_id_rejects_unordered_or_duplicate_ciks() -> None:
    with pytest.raises(WarehouseRuntimeError, match="sorted"):
        batch_id_for_ciks([200, 100])
    with pytest.raises(WarehouseRuntimeError, match="sorted"):
        batch_id_for_ciks([100, 100])


# ---------------------------------------------------------------------------
# reduce_identity_refresh (DuckDB Retirement Cutover Ticket 10): no longer
# merges/promotes into canonical silver.duckdb -- only validates that every
# declared batch actually succeeded, and records that validation immutably.
# ---------------------------------------------------------------------------


def test_reducer_never_touches_canonical_silver_duckdb(tmp_path: Path) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(
        storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference,
        batches=[[100]],
    )
    persist_batch_outcome(
        storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta,
    )

    completed = reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image")

    assert completed["status"] == "succeeded"
    assert completed["reducer"] == {"canonical_promotion_count": 0, "note": "duckdb_write_path_retired"}
    assert not Path(storage.join("silver/sec/silver.duckdb")).exists()


def test_reducer_never_publishes_a_partial_declared_run(tmp_path: Path) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    reference.write_bytes(b"reference")
    persist_run_manifest(
        storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference,
        batches=[[100], [200]],
    )
    delta = tmp_path / "batch.duckdb"
    delta.write_bytes(b"batch")
    persist_batch_outcome(
        storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta,
    )

    # Only one of two declared batches has an outcome -- the manifest is
    # incomplete, so the reducer must still fail closed rather than treat
    # "no merge to do" as "nothing to validate" (same FileNotFoundError as
    # before this ticket: the second batch's outcome.json was never written).
    with pytest.raises(FileNotFoundError):
        reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image")
    assert not Path(storage.join("silver/sec/silver.duckdb")).exists()


def test_reducer_writes_completed_manifest_immutably(tmp_path: Path) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image")

    completed = json.loads(read_bytes(storage.join(completed_manifest_path("run-1"))).decode("utf-8"))
    assert completed["status"] == "succeeded"
    assert completed["reducer"]["canonical_promotion_count"] == 0


def test_reducer_accepts_but_ignores_max_attempts(tmp_path: Path) -> None:
    """max_attempts is kept for call-site compatibility (the CLI still passes
    it) but no longer changes behavior -- there is nothing left to retry."""
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    completed = reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image", max_attempts=1)

    assert completed["reducer"]["canonical_promotion_count"] == 0
