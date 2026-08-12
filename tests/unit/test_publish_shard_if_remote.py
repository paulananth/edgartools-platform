"""Tests for _publish_shard_if_remote's ETag guard (decoupled-bronze-pipeline
ticket 01's identified gap: this previously called upload_file directly, a
blind overwrite with no version check at all -- fixed via the shared
stage_and_promote primitive, see test_object_storage_stage_and_promote.py
for that primitive's own correctness tests).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import (
    ObjectVersion,
    PromotionConflictError,
    PromotionResult,
    StorageLocation,
)


@dataclass
class _FakeRemoteStorage:
    """Duck-typed stand-in for the pieces of StorageLocation this call site
    uses -- real S3 wiring is exercised by test_object_storage_stage_and_promote.py."""

    baseline_etag: str | None = "baseline-etag"
    conflict: bool = False
    calls: list = field(default_factory=list)

    @property
    def is_remote(self) -> bool:
        return True

    def read_object_version(self, relative_path: str) -> ObjectVersion:
        self.calls.append(("read_object_version", relative_path))
        return ObjectVersion(exists=self.baseline_etag is not None, etag=self.baseline_etag, version_id=None)

    def stage_and_promote(self, relative_path: str, payload: bytes, *, expected_etag: str | None) -> PromotionResult:
        self.calls.append(("stage_and_promote", relative_path, payload, expected_etag))
        if self.conflict:
            raise PromotionConflictError(relative_path, expected_etag, "someone-elses-etag", "staged/token")
        return PromotionResult(
            canonical_path=f"s3://bucket/{relative_path}",
            staged_relative_path="staged/token",
            previous_version=ObjectVersion(exists=True, etag=expected_etag, version_id=None),
            new_version=ObjectVersion(exists=True, etag="new-etag", version_id="v2"),
        )


def _context(tmp_path: Path, storage_root) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=storage_root,
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="tester@example.com",
        runtime_mode="bronze_capture",
    )


def _write_local_shard(context: WarehouseCommandContext, shard_index: int, content: bytes) -> Path:
    local_path = Path(context.silver_root.join("silver", "sec", "shards", f"shard-{shard_index}.duckdb"))
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(content)
    return local_path


def test_returns_none_when_storage_is_local(tmp_path):
    context = _context(tmp_path, StorageLocation(str(tmp_path / "warehouse")))
    assert warehouse_orchestrator._publish_shard_if_remote(context, 0) is None


def test_reads_baseline_version_before_publishing(tmp_path):
    fake_storage = _FakeRemoteStorage()
    context = _context(tmp_path, fake_storage)
    _write_local_shard(context, 3, b"shard-payload")

    result = warehouse_orchestrator._publish_shard_if_remote(context, 3)

    call_types = [c[0] for c in fake_storage.calls]
    assert call_types == ["read_object_version", "stage_and_promote"]
    stage_call = fake_storage.calls[1]
    assert stage_call[2] == b"shard-payload"
    assert stage_call[3] == "baseline-etag"  # expected_etag came from the baseline read
    assert result["layer"] == "silver_shard"
    assert result["shard_index"] == 3
    assert result["source_version"] == "baseline-etag"
    assert result["canonical_version"] == "new-etag"
    assert result["size_bytes"] == len(b"shard-payload")


def test_propagates_promotion_conflict_instead_of_retrying(tmp_path):
    fake_storage = _FakeRemoteStorage(conflict=True)
    context = _context(tmp_path, fake_storage)
    _write_local_shard(context, 5, b"shard-payload")

    with pytest.raises(PromotionConflictError):
        warehouse_orchestrator._publish_shard_if_remote(context, 5)


def test_missing_local_shard_raises_before_any_remote_call(tmp_path):
    fake_storage = _FakeRemoteStorage()
    context = _context(tmp_path, fake_storage)

    with pytest.raises(WarehouseRuntimeError, match="not found"):
        warehouse_orchestrator._publish_shard_if_remote(context, 9)
    assert fake_storage.calls == []
