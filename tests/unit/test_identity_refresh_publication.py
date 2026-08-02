from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application.identity_refresh_publication import (
    batch_id_for_ciks,
    persist_batch_outcome,
    persist_run_manifest,
    reduce_identity_refresh,
    validate_complete_run_manifest,
)
from edgar_warehouse.infrastructure.object_storage import (
    PromotionConflictError,
    StorageLocation,
)


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

    with pytest.raises(FileNotFoundError):
        reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image")
    assert not Path(storage.join("silver/sec/silver.duckdb")).exists()


def test_reducer_merges_only_verified_persisted_inputs_and_promotes_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    merged_inputs: list[bytes] = []

    def fake_merge(candidate: Path, canonical: Path, output: Path):
        merged_inputs.append(candidate.read_bytes())
        shutil.copy2(canonical, output)
        return type("Result", (), {"tables_merged": ("sec_company",)})()

    monkeypatch.setattr("edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical", fake_merge)
    completed = reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image")

    assert merged_inputs == [b"batch"]
    assert completed["reducer"]["canonical_promotion_count"] == 1
    assert completed["reducer"]["merge_order"] == [batch_id_for_ciks([100])]
    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"reference"


def test_ambiguous_merge_conflict_fails_before_canonical_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from edgar_warehouse.silver_protection import SemanticMergeConflictError

    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    def raise_conflict(candidate: Path, canonical: Path, output: Path):
        raise SemanticMergeConflictError([])

    monkeypatch.setattr("edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical", raise_conflict)
    with pytest.raises(SemanticMergeConflictError):
        reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image")
    assert not Path(storage.join("silver/sec/silver.duckdb")).exists()


def test_promotion_conflict_retries_only_the_reducer_with_same_delta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    merge_inputs: list[bytes] = []

    def fake_merge(candidate: Path, canonical: Path, output: Path):
        merge_inputs.append(candidate.read_bytes())
        shutil.copy2(canonical, output)
        return type("Result", (), {"tables_merged": ()})()

    original_promote = StorageLocation.promote_staged
    promotion_attempts = 0

    def conflict_once(self: StorageLocation, staged: str, canonical: str, *, expected_etag: str | None):
        nonlocal promotion_attempts
        promotion_attempts += 1
        if promotion_attempts == 1:
            raise PromotionConflictError(canonical, expected_etag, "newer", staged)
        return original_promote(self, staged, canonical, expected_etag=expected_etag)

    monkeypatch.setattr("edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical", fake_merge)
    monkeypatch.setattr(StorageLocation, "promote_staged", conflict_once)
    completed = reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image", max_attempts=2)

    assert completed["reducer"]["attempt"] == 2
    assert promotion_attempts == 2
    assert merge_inputs == [b"batch", b"batch"]
