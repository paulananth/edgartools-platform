"""Tests for StorageLocation.stage_and_promote (decoupled-bronze-pipeline
ticket 09's Extract Function: the shared ETag-guarded stage-then-promote
sequence, pulled out of what were three independent hand-written copies).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from edgar_warehouse.infrastructure.object_storage import (
    PromotionConflictError,
    StorageLocation,
)


def test_first_publish_with_no_baseline_writes_canonical(tmp_path):
    storage = StorageLocation(str(tmp_path))

    result = storage.stage_and_promote("silver/sec/silver.duckdb", b"first", expected_etag=None)

    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"first"
    assert result.new_version.exists


def test_republish_with_the_correct_current_etag_succeeds(tmp_path):
    storage = StorageLocation(str(tmp_path))
    first = storage.stage_and_promote("silver/sec/silver.duckdb", b"first", expected_etag=None)

    second = storage.stage_and_promote(
        "silver/sec/silver.duckdb", b"second", expected_etag=first.new_version.etag
    )

    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"second"
    assert second.previous_version.etag == first.new_version.etag


def test_republish_with_a_stale_etag_raises_promotion_conflict_not_last_writer_wins(tmp_path):
    storage = StorageLocation(str(tmp_path))
    first = storage.stage_and_promote("silver/sec/silver.duckdb", b"first", expected_etag=None)
    # Someone else publishes in between, correctly, against the real baseline.
    storage.stage_and_promote(
        "silver/sec/silver.duckdb", b"someone-else", expected_etag=first.new_version.etag
    )

    # This caller's own baseline (read before the interleaved writer landed) is now stale.
    stale_etag = first.new_version.etag
    with pytest.raises(PromotionConflictError):
        storage.stage_and_promote("silver/sec/silver.duckdb", b"my-write", expected_etag=stale_etag)

    # The conflicting write never landed -- canonical still holds the interleaved writer's content.
    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"someone-else"


def test_stage_and_promote_leaves_the_staged_object_in_place_on_conflict(tmp_path):
    """promote_staged's own contract (retryable, staged object preserved for
    inspection) must survive being called through the extracted wrapper."""
    storage = StorageLocation(str(tmp_path))
    storage.stage_and_promote("silver/sec/silver.duckdb", b"first", expected_etag=None)

    with pytest.raises(PromotionConflictError) as exc_info:
        storage.stage_and_promote("silver/sec/silver.duckdb", b"my-write", expected_etag="stale")

    staged_relative = exc_info.value.staged_relative_path
    assert Path(storage.join(staged_relative)).read_bytes() == b"my-write"
