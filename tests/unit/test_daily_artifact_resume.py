from __future__ import annotations

import pytest

from edgar_warehouse.application.daily_artifact_resume import (
    prepare_resume,
    record_repair_attestation,
    record_succeeded,
    record_terminal_repair,
)
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def test_resume_skips_completed_candidate_and_rejects_manifest_drift(tmp_path) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    pending, repairs, manifest = prepare_resume(storage, run_id="run-1", image_identity="sha256:image", daily_index_accessions=["a", "b"], selected_accessions=["a", "b"])
    assert pending == ["a", "b"] and repairs == []
    record_succeeded(storage, run_id="run-1", accession="a", manifest=manifest)
    pending, repairs, _ = prepare_resume(storage, run_id="run-1", image_identity="sha256:image", daily_index_accessions=["a", "b"], selected_accessions=["a", "b"])
    assert pending == ["b"] and repairs == []
    with pytest.raises(WarehouseRuntimeError, match="identity drift"):
        prepare_resume(storage, run_id="run-1", image_identity="sha256:other", daily_index_accessions=["a", "b"], selected_accessions=["a", "b"])


def test_terminal_repair_requires_immutable_operator_attestation(tmp_path) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    _, _, manifest = prepare_resume(storage, run_id="run-1", image_identity="sha256:image", daily_index_accessions=["a"], selected_accessions=["a"])
    record_terminal_repair(storage, run_id="run-1", accession="a", manifest=manifest, error_type="WarehouseRuntimeError", error="immutable object already exists with different content")
    pending, repairs, _ = prepare_resume(storage, run_id="run-1", image_identity="sha256:image", daily_index_accessions=["a"], selected_accessions=["a"])
    assert pending == [] and repairs == ["a"]
    record_repair_attestation(storage, run_id="run-1", accession="a", manifest=manifest, operator_identity="operator@example.com", repair_action="registered byte-exact content", conflict_evidence={"expected_sha256": "a" * 64})
    pending, repairs, _ = prepare_resume(storage, run_id="run-1", image_identity="sha256:image", daily_index_accessions=["a"], selected_accessions=["a"])
    assert pending == ["a"] and repairs == []
