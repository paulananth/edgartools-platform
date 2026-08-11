"""Orchestration-level tests for the per-event silver reducer (decoupled-
bronze-pipeline Phase 0). merge_candidate_into_canonical is faked here to
isolate the reducer's own logic (verification, dedup, retry, promotion) --
see tests/application/test_silver_event_reducer_idempotency.py for the real
end-to-end proof that reordering/duplicates are safe against the actual
merge function and real DuckDB databases, not a mock.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.application.silver_event_reducer import (
    AccessionDelta,
    reduce_silver_events,
)
from edgar_warehouse.infrastructure.object_storage import (
    PromotionConflictError,
    StorageLocation,
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_delta(storage: StorageLocation, relative: str, payload: bytes) -> AccessionDelta:
    storage.write_bytes(relative, payload)
    accession = relative.rsplit("/", 1)[-1].removesuffix(".duckdb")
    return AccessionDelta(accession_number=accession, delta_path=relative, sha256=_sha(payload))


def test_no_deltas_is_a_safe_no_op(tmp_path: Path):
    storage = StorageLocation(str(tmp_path))
    result = reduce_silver_events(storage, deltas=[])
    assert result["status"] == "no_op"
    assert not Path(storage.join("silver/sec/silver.duckdb")).exists()


def test_checksum_mismatch_is_rejected_before_any_merge(tmp_path: Path, monkeypatch):
    storage = StorageLocation(str(tmp_path))
    storage.write_bytes("deltas/a.duckdb", b"real-content")
    bad_delta = AccessionDelta(accession_number="a", delta_path="deltas/a.duckdb", sha256=_sha(b"wrong-content"))

    merge_calls = []
    monkeypatch.setattr(
        "edgar_warehouse.application.silver_event_reducer.merge_candidate_into_canonical",
        lambda *a, **k: merge_calls.append(a) or type("R", (), {"tables_merged": ()})(),
    )

    with pytest.raises(WarehouseRuntimeError, match="checksum mismatch"):
        reduce_silver_events(storage, deltas=[bad_delta])
    assert merge_calls == []


def test_first_ever_publish_seeds_canonical_from_the_first_delta(tmp_path: Path, monkeypatch):
    storage = StorageLocation(str(tmp_path))
    delta_a = _write_delta(storage, "deltas/a.duckdb", b"delta-a")

    monkeypatch.setattr(
        "edgar_warehouse.application.silver_event_reducer.merge_candidate_into_canonical",
        lambda *a, **k: pytest.fail("no merge should run for a single first-ever delta"),
    )

    result = reduce_silver_events(storage, deltas=[delta_a])

    assert result["status"] == "succeeded"
    assert result["accessions_merged"] == ["a"]
    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"delta-a"


def test_multiple_deltas_are_merged_in_order_and_promoted_once(tmp_path: Path, monkeypatch):
    storage = StorageLocation(str(tmp_path))
    delta_a = _write_delta(storage, "deltas/a.duckdb", b"delta-a")
    delta_b = _write_delta(storage, "deltas/b.duckdb", b"delta-b")

    merge_order: list[bytes] = []

    def fake_merge(candidate: Path, canonical: Path, output: Path):
        merge_order.append(candidate.read_bytes())
        output.write_bytes(canonical.read_bytes() + b"+" + candidate.read_bytes())
        return type("R", (), {"tables_merged": ("sec_company",)})()

    monkeypatch.setattr(
        "edgar_warehouse.application.silver_event_reducer.merge_candidate_into_canonical", fake_merge
    )

    result = reduce_silver_events(storage, deltas=[delta_a, delta_b])

    assert merge_order == [b"delta-b"]  # 'a' seeds canonical directly, only 'b' is merged on top
    assert result["accessions_merged"] == ["a", "b"]
    assert result["canonical_promotion_count"] == 1
    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"delta-a+delta-b"


def test_a_duplicate_accession_within_one_call_is_deduplicated_up_front(tmp_path: Path, monkeypatch):
    storage = StorageLocation(str(tmp_path))
    delta_a = _write_delta(storage, "deltas/a.duckdb", b"delta-a")
    duplicate_of_a = AccessionDelta(accession_number="a", delta_path=delta_a.delta_path, sha256=delta_a.sha256)

    merge_calls = []
    monkeypatch.setattr(
        "edgar_warehouse.application.silver_event_reducer.merge_candidate_into_canonical",
        lambda *a, **k: merge_calls.append(a),
    )

    result = reduce_silver_events(storage, deltas=[delta_a, duplicate_of_a])

    assert result["accessions_merged"] == ["a"]
    assert merge_calls == []  # single delta after dedup -> seeds directly, no merge call needed


def test_redelivery_of_an_already_merged_accession_in_a_later_call_still_succeeds(tmp_path: Path, monkeypatch):
    """Simulates SQS at-least-once redelivery across two separate reducer
    invocations, not just duplicates inside one batch."""
    storage = StorageLocation(str(tmp_path))
    delta_a = _write_delta(storage, "deltas/a.duckdb", b"delta-a")
    delta_b = _write_delta(storage, "deltas/b.duckdb", b"delta-b")

    def fake_merge(candidate: Path, canonical: Path, output: Path):
        # Idempotent-by-construction fake: merging the same candidate twice
        # against the same canonical is a no-op, matching the real
        # merge_candidate_into_canonical's business-key semantics (identical
        # same-key rows are left alone -- see the real end-to-end proof in
        # test_silver_event_reducer_idempotency.py).
        current = canonical.read_bytes()
        candidate_bytes = candidate.read_bytes()
        output.write_bytes(current if candidate_bytes in current else current + b"+" + candidate_bytes)
        return type("R", (), {"tables_merged": ("sec_company",)})()

    monkeypatch.setattr(
        "edgar_warehouse.application.silver_event_reducer.merge_candidate_into_canonical", fake_merge
    )

    first = reduce_silver_events(storage, deltas=[delta_a])
    assert first["status"] == "succeeded"

    # 'a' redelivered alongside a genuinely new 'b'.
    second = reduce_silver_events(storage, deltas=[delta_a, delta_b])
    assert second["status"] == "succeeded"
    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"delta-a+delta-b"


def test_promotion_conflict_retries_up_to_max_attempts_then_raises(tmp_path: Path, monkeypatch):
    storage = StorageLocation(str(tmp_path))
    delta_a = _write_delta(storage, "deltas/a.duckdb", b"delta-a")

    monkeypatch.setattr(
        "edgar_warehouse.application.silver_event_reducer.merge_candidate_into_canonical",
        lambda *a, **k: type("R", (), {"tables_merged": ()})(),
    )

    attempts = []

    def always_conflict(self, staged_relative, canonical_relative, *, expected_etag):
        attempts.append(expected_etag)
        raise PromotionConflictError(canonical_relative, expected_etag, "other-etag", staged_relative)

    monkeypatch.setattr(StorageLocation, "promote_staged", always_conflict)

    with pytest.raises(PromotionConflictError):
        reduce_silver_events(storage, deltas=[delta_a], max_attempts=3)
    assert len(attempts) == 3


def test_max_attempts_must_be_positive(tmp_path: Path):
    storage = StorageLocation(str(tmp_path))
    with pytest.raises(WarehouseRuntimeError, match="max_attempts must be positive"):
        reduce_silver_events(storage, deltas=[], max_attempts=0)
