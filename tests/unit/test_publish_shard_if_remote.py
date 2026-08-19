"""Tests for _publish_shard_if_remote's ETag guard (decoupled-bronze-pipeline
ticket 01's identified gap: this previously called upload_file directly, a
blind overwrite with no version check at all -- fixed via the shared
stage_and_promote primitive, see test_object_storage_stage_and_promote.py
for that primitive's own correctness tests), its merge-on-conflict retry
wrapper, and its skip-if-unchanged fast path (silver-snowflake-migration
map, 2026-08-19 fix): multiple concurrent BatchSilver Map items can land on
the same shard index (4 shards, MaxConcurrency 20), so a lost promotion
race is an expected, retryable event here -- not the "exactly one writer"
invariant violation the function's docstring used to claim. Three real prod
executions failed on this exact shard-0.duckdb conflict before the fix (see
the silver-snowflake-migration map's "Motivating evidence" and Ticket
12/14). A live Stage 14 execution during the same fix separately showed
bootstrap-batch's medium (4096MB) profile OOMing on this same shard size
(~823MB) even under the old no-merge code -- the skip-if-unchanged fast
path (ported from _publish_silver_database_if_remote's ticket-79 pattern)
avoids paying the new merge machinery's added memory cost on the dominant
no-op case (most BatchSilver batches during a reprocessing pass write zero
new rows).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import duckdb
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
from edgar_warehouse.silver_store import SilverDatabase


@dataclass
class _FakeRemoteStorage:
    """Duck-typed stand-in for the pieces of StorageLocation this call site
    uses -- real S3 wiring is exercised by test_object_storage_stage_and_promote.py."""

    baseline_etag: str | None = "baseline-etag"
    conflict: bool = False
    flaky_until_attempt: int | None = None  # conflicts on attempts before this one, then succeeds
    download_bytes: bytes | None = None  # content download_file writes, if any test exercises hydration
    calls: list = field(default_factory=list)
    _stage_attempts: int = field(default=0, init=False)

    @property
    def is_remote(self) -> bool:
        return True

    def join(self, *parts: str) -> str:
        return "s3://bucket/" + "/".join(parts)

    def download_file(self, relative_path: str, local_path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
        self.calls.append(("download_file", relative_path))
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(self.download_bytes or b"")
        return str(local_path)

    def read_object_version(self, relative_path: str) -> ObjectVersion:
        self.calls.append(("read_object_version", relative_path))
        return ObjectVersion(exists=self.baseline_etag is not None, etag=self.baseline_etag, version_id=None)

    def stage_and_promote(self, relative_path: str, payload: bytes, *, expected_etag: str | None) -> PromotionResult:
        self.calls.append(("stage_and_promote", relative_path, payload, expected_etag))
        self._stage_attempts += 1
        should_conflict = self.conflict or (
            self.flaky_until_attempt is not None and self._stage_attempts < self.flaky_until_attempt
        )
        if should_conflict:
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


def test_new_shard_skips_merge_and_uploads_local_directly(tmp_path):
    """No canonical object exists yet for this shard (baseline etag is
    None) -- first-ever publish, so there's nothing to merge against; the
    local candidate's bytes go up unchanged, matching
    _publish_silver_database_if_remote's own `baseline.exists` branch."""
    fake_storage = _FakeRemoteStorage(baseline_etag=None)
    context = _context(tmp_path, fake_storage)
    _write_local_shard(context, 3, b"shard-payload")

    result = warehouse_orchestrator._publish_shard_if_remote(context, 3)

    call_types = [c[0] for c in fake_storage.calls]
    assert call_types == ["read_object_version", "stage_and_promote"]
    stage_call = fake_storage.calls[1]
    assert stage_call[2] == b"shard-payload"
    assert stage_call[3] is None  # no baseline etag to guard against
    assert result["layer"] == "silver_shard"
    assert result["shard_index"] == 3
    assert result["source_version"] is None
    assert result["canonical_version"] == "new-etag"
    assert result["size_bytes"] == len(b"shard-payload")
    assert result["tables_merged"] == []


def test_existing_shard_merges_local_candidate_into_canonical_before_publish(tmp_path):
    """Regression for the actual Stage-14 bug: a shard that already has a
    canonical version must be merged (via merge_candidate_into_canonical,
    the same function the monolith publish path uses), not blindly
    overwritten with the local candidate's raw bytes -- otherwise a second
    writer's local shard (hydrated before the first writer's publish) would
    silently discard the first writer's row on a conflict-free publish, and
    the two writers' data could never coexist even with retry-on-conflict
    layered on top. Real SilverDatabase-backed files, not string/byte
    fakes, matching this workstream's established discipline
    (test_skip_noop_silver_publish.py)."""
    fake_storage = _FakeRemoteStorage(baseline_etag="canonical-etag-1")
    context = _context(tmp_path, fake_storage)

    canonical_path = tmp_path / "canonical-shard.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    canonical_db._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_synced_at) "
        "VALUES (1, 'Existing Corp', '2026-01-01 00:00:00')"
    )
    canonical_db.close()
    canonical_bytes = canonical_path.read_bytes()

    local_path = Path(context.silver_root.join("silver", "sec", "shards", "shard-2.duckdb"))
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_db = SilverDatabase(str(local_path))
    local_db._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_synced_at) "
        "VALUES (2, 'New Writer Corp', '2026-01-02 00:00:00')"
    )
    local_db.close()

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
        return_value=canonical_bytes,
    ):
        result = warehouse_orchestrator._publish_shard_if_remote(context, 2)

    assert "sec_company" in result["tables_merged"]
    staged_payload = fake_storage.calls[1][2]
    staged_path = tmp_path / "staged-result.duckdb"
    staged_path.write_bytes(staged_payload)
    check_conn = duckdb.connect(str(staged_path), read_only=True)
    ciks = {row[0] for row in check_conn.execute("SELECT cik FROM sec_company").fetchall()}
    check_conn.close()
    # Both writers' rows survive the merge -- neither was silently dropped.
    assert ciks == {1, 2}


def test_propagates_promotion_conflict_instead_of_retrying(tmp_path):
    """The bare (non-wrapped) function still does not retry on its own --
    only _publish_shard_if_remote_with_retry does. Uses baseline_etag=None
    (new-shard path) so the conflict is isolated from merge mechanics,
    covered separately above."""
    fake_storage = _FakeRemoteStorage(baseline_etag=None, conflict=True)
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


# ---------------------------------------------------------------------------
# _publish_shard_if_remote_with_retry -- the actual fix for the shard-0.duckdb
# race (3 real prod failures, ToleratedFailurePercentage: 0, see this test
# module's docstring). Mirrors test_warehouse_orchestrator_mdm.py's
# _publish_silver_database_with_retry tests exactly (same env vars, same
# flaky-then-succeeds / always-conflicts shapes).
# ---------------------------------------------------------------------------


def test_retries_on_lost_promotion_race_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("WAREHOUSE_PUBLISH_CONFLICT_RETRY_BASE_SECONDS", "0.001")
    fake_storage = _FakeRemoteStorage(baseline_etag=None, flaky_until_attempt=2)
    context = _context(tmp_path, fake_storage)
    _write_local_shard(context, 1, b"shard-payload")

    result = warehouse_orchestrator._publish_shard_if_remote_with_retry(context, 1)

    assert result is not None
    assert result["canonical_version"] == "new-etag"
    stage_calls = [c for c in fake_storage.calls if c[0] == "stage_and_promote"]
    assert len(stage_calls) == 2


def test_retry_gives_up_after_configured_max_attempts(tmp_path, monkeypatch):
    monkeypatch.setenv("WAREHOUSE_PUBLISH_CONFLICT_ATTEMPTS", "2")
    monkeypatch.setenv("WAREHOUSE_PUBLISH_CONFLICT_RETRY_BASE_SECONDS", "0.001")
    fake_storage = _FakeRemoteStorage(baseline_etag=None, conflict=True)
    context = _context(tmp_path, fake_storage)
    _write_local_shard(context, 1, b"shard-payload")

    with pytest.raises(PromotionConflictError):
        warehouse_orchestrator._publish_shard_if_remote_with_retry(context, 1)

    stage_calls = [c for c in fake_storage.calls if c[0] == "stage_and_promote"]
    assert len(stage_calls) == 2


def test_retry_is_unbounded_by_default(tmp_path, monkeypatch):
    """No WAREHOUSE_PUBLISH_CONFLICT_ATTEMPTS set -> keeps retrying past a
    small number of conflicts rather than giving up early, matching
    _publish_silver_database_with_retry's own documented "no attempt
    ceiling by default" policy (sibling writers may legitimately win more
    than five times in a row)."""
    monkeypatch.delenv("WAREHOUSE_PUBLISH_CONFLICT_ATTEMPTS", raising=False)
    monkeypatch.setenv("WAREHOUSE_PUBLISH_CONFLICT_RETRY_BASE_SECONDS", "0.001")
    fake_storage = _FakeRemoteStorage(baseline_etag=None, flaky_until_attempt=6)
    context = _context(tmp_path, fake_storage)
    _write_local_shard(context, 1, b"shard-payload")

    result = warehouse_orchestrator._publish_shard_if_remote_with_retry(context, 1)

    assert result["canonical_version"] == "new-etag"
    stage_calls = [c for c in fake_storage.calls if c[0] == "stage_and_promote"]
    assert len(stage_calls) == 6


def test_concurrent_shard_writers_retry_preserves_both_writers_data(tmp_path, monkeypatch):
    """End-to-end regression for the actual Stage-14 failure shape: two
    BatchSilver Map items partitioned onto the same shard both hydrate from
    the same starting canonical, then race to publish. The first publish
    succeeds outright; the second must lose the ETag race, retry, re-merge
    against the first writer's now-current canonical, and land both
    writers' rows -- not raise, and not silently drop the first writer's
    data."""
    monkeypatch.setenv("WAREHOUSE_PUBLISH_CONFLICT_RETRY_BASE_SECONDS", "0.001")

    shared_baseline_path = tmp_path / "shared-baseline.duckdb"
    shared_baseline_db = SilverDatabase(str(shared_baseline_path))
    shared_baseline_db.close()
    original_baseline_bytes = shared_baseline_path.read_bytes()

    # A single shared fake canonical store both writers publish against.
    canonical_state = {"bytes": original_baseline_bytes, "etag": "baseline-etag"}
    frozen_baseline_etag = canonical_state["etag"]

    class _LiveCanonical:
        is_remote = True

        def join(self, *parts: str) -> str:
            return "s3://bucket/" + "/".join(parts)

        def read_object_version(self, relative_path: str) -> ObjectVersion:
            return ObjectVersion(exists=True, etag=canonical_state["etag"], version_id=None)

        def stage_and_promote(self, relative_path: str, payload: bytes, *, expected_etag: str | None) -> PromotionResult:
            if expected_etag != canonical_state["etag"]:
                raise PromotionConflictError(relative_path, expected_etag, canonical_state["etag"], "staged/token")
            previous_etag = canonical_state["etag"]
            canonical_state["bytes"] = payload
            canonical_state["etag"] = f"etag-{len(payload)}-{previous_etag}"
            return PromotionResult(
                canonical_path=f"s3://bucket/{relative_path}",
                staged_relative_path="staged/token",
                previous_version=ObjectVersion(exists=True, etag=previous_etag, version_id=None),
                new_version=ObjectVersion(exists=True, etag=canonical_state["etag"], version_id="v2"),
            )

    class _StaleFirstReadCanonical(_LiveCanonical):
        """Simulates writer B's baseline read racing ahead of writer A's
        commit: returns the frozen pre-publish etag on its own first read,
        live state on every read after -- the actual real-world shape of
        the race (both writers' GETs land before either's PUT), which a
        purely sequential test can't reproduce via simple call ordering."""

        def __init__(self) -> None:
            self._read_calls = 0

        def read_object_version(self, relative_path: str) -> ObjectVersion:
            self._read_calls += 1
            if self._read_calls == 1:
                return ObjectVersion(exists=True, etag=frozen_baseline_etag, version_id=None)
            return super().read_object_version(relative_path)

    storage_for_a = _LiveCanonical()
    storage_for_b = _StaleFirstReadCanonical()

    # Writer A: hydrates the shared baseline, writes CIK 1.
    context_a = _context(tmp_path / "writer-a", storage_for_a)
    local_a = Path(context_a.silver_root.join("silver", "sec", "shards", "shard-0.duckdb"))
    local_a.parent.mkdir(parents=True, exist_ok=True)
    local_a.write_bytes(original_baseline_bytes)
    db_a = SilverDatabase(str(local_a))
    db_a._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_synced_at) "
        "VALUES (1, 'Writer A Corp', '2026-01-01 00:00:00')"
    )
    db_a.close()

    # Writer B: hydrates the SAME original baseline (before A published), writes CIK 2.
    context_b = _context(tmp_path / "writer-b", storage_for_b)
    local_b = Path(context_b.silver_root.join("silver", "sec", "shards", "shard-0.duckdb"))
    local_b.parent.mkdir(parents=True, exist_ok=True)
    local_b.write_bytes(original_baseline_bytes)
    db_b = SilverDatabase(str(local_b))
    db_b._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_synced_at) "
        "VALUES (2, 'Writer B Corp', '2026-01-02 00:00:00')"
    )
    db_b.close()

    def fake_read_bytes(_uri):
        return canonical_state["bytes"]

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
        side_effect=fake_read_bytes,
    ):
        result_a = warehouse_orchestrator._publish_shard_if_remote_with_retry(context_a, 0)
        result_b = warehouse_orchestrator._publish_shard_if_remote_with_retry(context_b, 0)

    assert result_a is not None
    assert result_b is not None

    final_path = tmp_path / "final-canonical.duckdb"
    final_path.write_bytes(canonical_state["bytes"])
    conn = duckdb.connect(str(final_path), read_only=True)
    ciks = {row[0] for row in conn.execute("SELECT cik FROM sec_company").fetchall()}
    conn.close()
    assert ciks == {1, 2}


# ---------------------------------------------------------------------------
# Skip-if-unchanged fast path (release-readiness ticket 79's pattern, ported
# to shards 2026-08-19) -- avoids the merge branch's added memory/network
# cost for the dominant no-op batch, using real hydrate-then-publish (not
# hand-constructed fingerprints), matching test_skip_noop_silver_publish.py's
# established real-DB-backed discipline.
# ---------------------------------------------------------------------------


def test_unchanged_shard_is_skipped_without_touching_s3_merge_path(tmp_path):
    canonical_path = tmp_path / "canonical-shard.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    canonical_db._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_synced_at) "
        "VALUES (1, 'Existing Corp', '2026-01-01 00:00:00')"
    )
    canonical_db.close()
    canonical_bytes = canonical_path.read_bytes()

    fake_storage = _FakeRemoteStorage(baseline_etag="canonical-etag-1", download_bytes=canonical_bytes)
    context = _context(tmp_path, fake_storage)

    warehouse_orchestrator._hydrate_shard_for_window(context, 4)
    fake_storage.calls.clear()  # only the publish call's own remote calls matter below

    result = warehouse_orchestrator._publish_shard_if_remote(context, 4)

    assert result["skipped"] is True
    assert result["tables_merged"] == []
    assert fake_storage.calls == []  # no read_object_version, no stage_and_promote at all


def test_genuinely_changed_shard_still_runs_full_merge(tmp_path):
    canonical_path = tmp_path / "canonical-shard.duckdb"
    canonical_db = SilverDatabase(str(canonical_path))
    canonical_db._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_synced_at) "
        "VALUES (1, 'Existing Corp', '2026-01-01 00:00:00')"
    )
    canonical_db.close()
    canonical_bytes = canonical_path.read_bytes()

    fake_storage = _FakeRemoteStorage(baseline_etag="canonical-etag-1", download_bytes=canonical_bytes)
    context = _context(tmp_path, fake_storage)

    warehouse_orchestrator._hydrate_shard_for_window(context, 4)
    fake_storage.calls.clear()

    local_path = Path(context.silver_root.join("silver", "sec", "shards", "shard-4.duckdb"))
    conn = duckdb.connect(str(local_path))
    conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_synced_at) "
        "VALUES (2, 'New Writer Corp', '2026-01-02 00:00:00')"
    )
    conn.close()

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
        return_value=canonical_bytes,
    ):
        result = warehouse_orchestrator._publish_shard_if_remote(context, 4)

    assert "skipped" not in result
    assert "sec_company" in result["tables_merged"]
    call_types = [c[0] for c in fake_storage.calls]
    assert call_types == ["read_object_version", "stage_and_promote"]
