from __future__ import annotations

import pytest

from edgar_warehouse.application.daily_artifact_resume import (
    prepare_resume,
    record_repair_attestation,
    record_succeeded,
    record_terminal_repair,
)
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes


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


def test_resume_checks_outcomes_with_one_batched_listing_not_per_candidate(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    accessions = [f"000000000{i:03d}-99-000001" for i in range(40)]

    find_existing_calls = 0
    original_find_existing = StorageLocation.find_existing

    def counting_find_existing(self: StorageLocation, relative_glob: str):
        nonlocal find_existing_calls
        find_existing_calls += 1
        return original_find_existing(self, relative_glob)

    read_calls: list[str] = []

    def counting_read_bytes(storage_path: str) -> bytes:
        read_calls.append(storage_path)
        return read_bytes(storage_path)

    monkeypatch.setattr(StorageLocation, "find_existing", counting_find_existing)
    monkeypatch.setattr("edgar_warehouse.application.daily_artifact_resume.read_bytes", counting_read_bytes)

    pending, repairs, _ = prepare_resume(
        storage, run_id="run-1", image_identity="sha256:image",
        daily_index_accessions=accessions, selected_accessions=accessions,
    )

    assert pending == accessions and repairs == []
    assert find_existing_calls == 1, f"expected exactly one batched listing call, got {find_existing_calls}"
    # The only read is the manifest itself (written and re-read once); zero
    # per-candidate outcome GetObjects, regardless of candidate count.
    assert read_calls == [storage.join("daily_artifact/runs/run-1/run_manifest.json")]


def test_resume_batched_check_matches_per_candidate_categorization(tmp_path) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    accessions = ["succeeded-one", "terminal-attested", "terminal-unattested", "never-run"]
    _, _, manifest = prepare_resume(storage, run_id="run-1", image_identity="sha256:image", daily_index_accessions=accessions, selected_accessions=accessions)
    record_succeeded(storage, run_id="run-1", accession="succeeded-one", manifest=manifest)
    record_terminal_repair(storage, run_id="run-1", accession="terminal-attested", manifest=manifest, error_type="WarehouseRuntimeError", error="conflict")
    record_repair_attestation(storage, run_id="run-1", accession="terminal-attested", manifest=manifest, operator_identity="operator@example.com", repair_action="registered byte-exact content", conflict_evidence={"expected_sha256": "a" * 64})
    record_terminal_repair(storage, run_id="run-1", accession="terminal-unattested", manifest=manifest, error_type="WarehouseRuntimeError", error="conflict")

    pending, repairs, _ = prepare_resume(storage, run_id="run-1", image_identity="sha256:image", daily_index_accessions=accessions, selected_accessions=accessions)

    assert sorted(pending) == ["never-run", "terminal-attested"]
    assert repairs == ["terminal-unattested"]
