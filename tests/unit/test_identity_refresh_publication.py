from __future__ import annotations

import hashlib
import json
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
    read_bytes,
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


def test_reducer_bounds_peak_intermediate_disk_across_many_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard, company-identity-hydrate-elimination ticket 01/04:
    each merge iteration's superseded ``current`` file must be unlinked
    once no longer needed, so peak local disk during the merge loop stays
    ~O(1) attempt-local files, not O(candidate_count). Only the initial
    verified-cache reference file (reused across retry attempts) must
    survive -- everything else the loop itself created must not pile up."""
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    reference.write_bytes(b"reference")
    ciks_per_batch = [[100], [200], [300], [400]]
    persist_run_manifest(
        storage, run_id="run-1", image_identity="sha256:image",
        reference_snapshot_file=reference, batches=ciks_per_batch,
    )
    for ciks in ciks_per_batch:
        delta = tmp_path / f"batch-{ciks[0]}.duckdb"
        delta.write_bytes(f"batch-{ciks[0]}".encode())
        persist_batch_outcome(
            storage, run_id="run-1", image_identity="sha256:image", ciks=ciks, delta_file=delta,
        )

    peak_attempt_local_files: list[int] = []

    def fake_merge(candidate: Path, canonical: Path, output: Path):
        attempt_dir = output.parent
        peak_attempt_local_files.append(len(list(attempt_dir.glob("*.duckdb"))))
        output.write_bytes(canonical.read_bytes() + candidate.read_bytes())
        return type("Result", (), {"tables_merged": ("sec_company",)})()

    monkeypatch.setattr(
        "edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical",
        fake_merge,
    )
    reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image")

    # Reference doesn't exist as canonical yet, so the loop merges 4 batch
    # deltas starting from the reference file. Before this fix, file count
    # in the attempt-local tmp dir grew unbounded (1, 2, 3, 4 merged-*.duckdb
    # files coexisting); after it, at most 1 attempt-local file (the prior
    # `current`) should ever be present alongside the new output about to
    # be written -- i.e. never more than 1 pre-existing file at merge start.
    assert max(peak_attempt_local_files) <= 1, peak_attempt_local_files


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


def test_reducer_reads_each_reference_and_delta_object_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    def fake_merge(candidate: Path, canonical: Path, output: Path):
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

    read_calls: list[str] = []
    original_read_bytes = read_bytes

    def counting_read_bytes(storage_path: str) -> bytes:
        read_calls.append(storage_path)
        return original_read_bytes(storage_path)

    monkeypatch.setattr("edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical", fake_merge)
    monkeypatch.setattr(StorageLocation, "promote_staged", conflict_once)
    monkeypatch.setattr("edgar_warehouse.application.identity_refresh_publication.read_bytes", counting_read_bytes)
    completed = reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image", max_attempts=2)

    assert completed["reducer"]["attempt"] == 2
    assert promotion_attempts == 2
    reference_reads = [call for call in read_calls if call.endswith("reference_snapshot.duckdb")]
    delta_reads = [call for call in read_calls if call.endswith("delta.duckdb")]
    assert len(reference_reads) == 1, f"expected reference snapshot read exactly once, got {reference_reads}"
    assert len(delta_reads) == 1, f"expected batch delta read exactly once, got {delta_reads}"


def test_reducer_cleans_up_its_verified_candidate_cache_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Release-readiness ticket 83: verified candidates are written to a
    stable local cache directory (not held as Python bytes) for the whole
    call, replacing the in-memory dict that stacked with the merge's own
    working set and OOM-killed a real prod run. That cache directory must
    not leak after a successful call -- the exact class of disk-hygiene bug
    this workstream has already hit once (ticket 65's orphaned staged
    blobs)."""
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    def fake_merge(candidate: Path, canonical: Path, output: Path):
        assert candidate.exists(), "candidate must be a real cached local file, not an in-memory bytes object"
        shutil.copy2(canonical, output)
        return type("Result", (), {"tables_merged": ()})()

    monkeypatch.setattr(
        "edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical", fake_merge
    )

    import edgar_warehouse.application.identity_refresh_publication as mod

    captured: list[Path] = []
    original_mkdtemp = mod.tempfile.mkdtemp

    def capturing_mkdtemp(*args, **kwargs):
        created = original_mkdtemp(*args, **kwargs)
        if kwargs.get("prefix", "").startswith("identity-refresh-verified-"):
            captured.append(Path(created))
        return created

    monkeypatch.setattr(mod.tempfile, "mkdtemp", capturing_mkdtemp)

    reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image", max_attempts=1)

    assert len(captured) == 1
    assert not captured[0].exists(), "verified-candidate cache directory must be removed after the call"


def test_reducer_cleans_up_its_verified_candidate_cache_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cache directory must not leak even when the merge itself raises --
    matches the identity-refresh lease's own 'release-on-failure is
    best-effort, cleanup must not depend on the happy path' discipline."""
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    def failing_merge(candidate: Path, canonical: Path, output: Path):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical", failing_merge
    )

    import edgar_warehouse.application.identity_refresh_publication as mod

    captured: list[Path] = []
    original_mkdtemp = mod.tempfile.mkdtemp

    def capturing_mkdtemp(*args, **kwargs):
        created = original_mkdtemp(*args, **kwargs)
        if kwargs.get("prefix", "").startswith("identity-refresh-verified-"):
            captured.append(Path(created))
        return created

    monkeypatch.setattr(mod.tempfile, "mkdtemp", capturing_mkdtemp)

    with pytest.raises(RuntimeError, match="boom"):
        reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image", max_attempts=1)

    assert len(captured) == 1
    assert not captured[0].exists(), "verified-candidate cache directory must be removed even when the merge raises"


def test_reducer_deletes_its_own_staged_object_after_successful_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Release-readiness ticket 65: promote_staged never deletes the staged
    object it just promoted (deliberately, so a conflict leaves it in place
    for retry/inspection) -- confirmed live in prod: 46 orphaned objects,
    49.3GB, in the staging prefix with no lifecycle rule. The reducer must
    delete its own staged object once a promotion actually succeeds."""
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    def fake_merge(candidate: Path, canonical: Path, output: Path):
        shutil.copy2(canonical, output)
        return type("Result", (), {"tables_merged": ()})()

    monkeypatch.setattr("edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical", fake_merge)
    completed = reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image")

    staged_path = completed["reducer"]["staged_path"]
    assert not Path(storage.join(staged_path)).exists()


def test_reducer_preserves_staged_object_after_promotion_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    def fake_merge(candidate: Path, canonical: Path, output: Path):
        shutil.copy2(canonical, output)
        return type("Result", (), {"tables_merged": ()})()

    original_promote = StorageLocation.promote_staged
    staged_paths: list[str] = []
    promotion_attempts = 0

    def record_and_conflict_once(self: StorageLocation, staged: str, canonical: str, *, expected_etag: str | None):
        nonlocal promotion_attempts
        promotion_attempts += 1
        staged_paths.append(staged)
        if promotion_attempts == 1:
            raise PromotionConflictError(canonical, expected_etag, "newer", staged)
        return original_promote(self, staged, canonical, expected_etag=expected_etag)

    monkeypatch.setattr("edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical", fake_merge)
    monkeypatch.setattr(StorageLocation, "promote_staged", record_and_conflict_once)
    completed = reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image", max_attempts=2)

    assert len(staged_paths) == 2
    conflicted_staged_path, succeeded_staged_path = staged_paths
    assert conflicted_staged_path != succeeded_staged_path
    # The conflicted attempt's staged object is left in place for inspection/retry.
    assert Path(storage.join(conflicted_staged_path)).exists()
    # The successful attempt's own staged object is cleaned up.
    assert not Path(storage.join(succeeded_staged_path)).exists()
    assert completed["reducer"]["staged_path"] == succeeded_staged_path


def _events_from_stderr(capsys: pytest.CaptureFixture) -> list[dict]:
    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_reducer_emits_progress_events_in_order_for_a_multi_batch_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Ticket 64: reduce_identity_refresh previously emitted zero log output
    for its entire runtime -- a real prod ReduceIdentityRefresh task ran 17+
    minutes with CloudWatch reporting storedBytes: 0, indistinguishable from
    hung without reading the source. This asserts the reducer now emits the
    named started/completed events, in order, for every stage across a
    multi-batch merge."""
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta_a = tmp_path / "batch-a.duckdb"
    delta_b = tmp_path / "batch-b.duckdb"
    reference.write_bytes(b"reference")
    delta_a.write_bytes(b"batch-a")
    delta_b.write_bytes(b"batch-b")
    persist_run_manifest(
        storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference,
        batches=[[100], [200]],
    )
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta_a)
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[200], delta_file=delta_b)

    def fake_merge(candidate: Path, canonical: Path, output: Path):
        shutil.copy2(canonical, output)
        return type("Result", (), {"tables_merged": ("sec_company",)})()

    monkeypatch.setattr("edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical", fake_merge)
    capsys.readouterr()  # discard any setup output
    reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image")
    events = _events_from_stderr(capsys)

    batch_a_id = batch_id_for_ciks([100])
    batch_b_id = batch_id_for_ciks([200])
    assert [e["event"] for e in events] == [
        "identity_refresh_attempt_started",
        "identity_refresh_baseline_read_completed",
        "identity_refresh_candidate_merge_started",
        "identity_refresh_candidate_merge_completed",
        "identity_refresh_candidate_merge_started",
        "identity_refresh_candidate_merge_completed",
        "identity_refresh_stage_and_promote_started",
        "identity_refresh_stage_and_promote_completed",
    ]
    assert all(e["run_id"] == "run-1" for e in events)
    attempt_started = events[0]
    assert attempt_started["attempt"] == 1
    assert attempt_started["max_attempts"] == 3
    baseline_read = events[1]
    assert baseline_read["canonical_exists"] is False
    assert baseline_read["byte_size"] == len(b"reference")
    merge_started_a, merge_completed_a, merge_started_b, merge_completed_b = events[2:6]
    assert merge_started_a["batch_id"] == batch_a_id
    assert merge_completed_a["batch_id"] == batch_a_id
    assert merge_completed_a["tables_merged"] == ["sec_company"]
    assert merge_started_b["batch_id"] == batch_b_id
    assert merge_completed_b["batch_id"] == batch_b_id
    stage_started, stage_completed = events[6:8]
    assert stage_started["byte_size"] == len(b"reference")
    assert "staged_path" in stage_completed
    assert "result_etag" in stage_completed


def test_reducer_emits_promotion_conflict_event_with_conflicting_etag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    reference = tmp_path / "reference.duckdb"
    delta = tmp_path / "batch.duckdb"
    reference.write_bytes(b"reference")
    delta.write_bytes(b"batch")
    persist_run_manifest(storage, run_id="run-1", image_identity="sha256:image", reference_snapshot_file=reference, batches=[[100]])
    persist_batch_outcome(storage, run_id="run-1", image_identity="sha256:image", ciks=[100], delta_file=delta)

    def fake_merge(candidate: Path, canonical: Path, output: Path):
        shutil.copy2(canonical, output)
        return type("Result", (), {"tables_merged": ()})()

    original_promote = StorageLocation.promote_staged
    promotion_attempts = 0

    def conflict_once(self: StorageLocation, staged: str, canonical: str, *, expected_etag: str | None):
        nonlocal promotion_attempts
        promotion_attempts += 1
        if promotion_attempts == 1:
            raise PromotionConflictError(canonical, expected_etag, "newer-etag", staged)
        return original_promote(self, staged, canonical, expected_etag=expected_etag)

    monkeypatch.setattr("edgar_warehouse.application.identity_refresh_publication.merge_candidate_into_canonical", fake_merge)
    monkeypatch.setattr(StorageLocation, "promote_staged", conflict_once)
    capsys.readouterr()
    reduce_identity_refresh(storage, run_id="run-1", image_identity="sha256:image", max_attempts=2)
    events = _events_from_stderr(capsys)

    conflict_events = [e for e in events if e["event"] == "identity_refresh_promotion_conflict"]
    assert len(conflict_events) == 1
    assert conflict_events[0]["attempt"] == 1
    assert conflict_events[0]["max_attempts"] == 2
    assert conflict_events[0]["conflicting_etag"] == "newer-etag"
    # A second full attempt cycle followed the conflict.
    assert [e["event"] for e in events].count("identity_refresh_attempt_started") == 2
