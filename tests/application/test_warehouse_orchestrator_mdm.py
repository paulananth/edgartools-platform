"""Tests for MDM helpers and silver-owned warehouse tracking state.

MDM remains an explicit entity-management subsystem, but warehouse pipeline
tracking_status lives in sec_company_sync_state.
"""
from __future__ import annotations

import io
import json
import shutil
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def test_hydrate_silver_database_from_remote_storage(tmp_path):
    from edgar_warehouse.application import warehouse_orchestrator

    context = WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation("s3://warehouse-root/warehouse"),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="dev@example.com",
        runtime_mode="bronze_capture",
    )
    with patch.object(warehouse_orchestrator, "read_bytes", return_value=b"duckdb-bytes"):
        warehouse_orchestrator._hydrate_silver_database_from_storage(context)

    assert (Path(context.silver_root.join("silver", "sec", "silver.duckdb"))).read_bytes() == b"duckdb-bytes"


# ---------------------------------------------------------------------------
# _get_mdm_tracked_ciks — MDM is required, no fallback
# ---------------------------------------------------------------------------

def test_get_mdm_tracked_ciks_raises_without_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _get_mdm_tracked_ciks
    with pytest.raises(WarehouseRuntimeError, match="MDM_DATABASE_URL is required"):
        _get_mdm_tracked_ciks("active")


def test_get_mdm_tracked_ciks_raises_on_connection_failure(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    with patch("edgar_warehouse.mdm.database.get_engine", side_effect=Exception("no DB")):
        from edgar_warehouse.application.warehouse_orchestrator import _get_mdm_tracked_ciks
        with pytest.raises(Exception, match="no DB"):
            _get_mdm_tracked_ciks("active")


def test_get_mdm_tracked_ciks_returns_ciks_from_mdm(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _get_mdm_tracked_ciks

    with patch("edgar_warehouse.mdm.database.get_engine", return_value=MagicMock()):
        with patch("edgar_warehouse.mdm.universe.get_tracked_ciks", return_value=[100, 200]):
            result = _get_mdm_tracked_ciks("active")

    assert result == [100, 200]


# ---------------------------------------------------------------------------
# _resolve_target_ciks — MDM only, no DuckDB fallback
# ---------------------------------------------------------------------------

def test_resolve_target_ciks_uses_mdm(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
        return_value=[100, 200],
    ):
        result = _resolve_target_ciks(
            raw_ciks=None,
            command_name="bootstrap-full",
            tracking_status_filter="active",
        )

    assert result == [100, 200]


def test_resolve_target_ciks_raises_when_mdm_empty(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
        return_value=[],
    ):
        with pytest.raises(WarehouseRuntimeError, match="seeded MDM universe"):
            _resolve_target_ciks(
                raw_ciks=None,
                command_name="bootstrap-full",
                tracking_status_filter="active",
            )


def test_resolve_target_ciks_raises_without_mdm_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with pytest.raises(WarehouseRuntimeError, match="MDM_DATABASE_URL is required"):
        _resolve_target_ciks(
            raw_ciks=None,
            command_name="bootstrap-full",
            tracking_status_filter="active",
        )


def test_resolve_target_ciks_respects_raw_ciks(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks"
    ) as mock_mdm:
        result = _resolve_target_ciks(
            raw_ciks=["12345", "67890"],
            command_name="bootstrap-full",
            tracking_status_filter="active",
        )

    mock_mdm.assert_not_called()
    assert result == [12345, 67890]


# ---------------------------------------------------------------------------
# _filter_ciks_to_universe — silver tracking state
# ---------------------------------------------------------------------------

def test_filter_ciks_to_universe_filters_by_silver_tracking_state(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    db = MagicMock()
    db.get_tracked_ciks.return_value = [100, 200]
    result = _filter_ciks_to_universe([100, 200, 300], db=db)

    assert result == [100, 200]


def test_filter_ciks_to_universe_passes_through_when_silver_empty(monkeypatch):
    """Cold-start guard: if silver returns no active CIKs, pass all impacted CIKs through."""
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    db = MagicMock()
    db.get_tracked_ciks.return_value = []
    result = _filter_ciks_to_universe([100, 200, 300], db=db)

    assert result == [100, 200, 300]


def test_filter_ciks_to_universe_does_not_require_mdm_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    db = MagicMock()
    db.get_tracked_ciks.return_value = [100]

    assert _filter_ciks_to_universe([100, 200, 300], db=db) == [100]


# ---------------------------------------------------------------------------
# _sync_mdm_tracking_status — raises on failure, no silent swallow
# ---------------------------------------------------------------------------

def test_sync_mdm_tracking_status_raises_without_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _sync_mdm_tracking_status
    with pytest.raises(WarehouseRuntimeError, match="MDM_DATABASE_URL is required"):
        _sync_mdm_tracking_status(1234, "active")


def test_sync_mdm_tracking_status_calls_update_when_url_set(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _sync_mdm_tracking_status

    with patch("edgar_warehouse.mdm.database.get_engine", return_value=MagicMock()):
        with patch("edgar_warehouse.mdm.universe.update_tracking_status", return_value=True) as mock_update:
            _sync_mdm_tracking_status(1234, "active")
    mock_update.assert_called_once()
    args = mock_update.call_args[0]
    assert args[1] == 1234
    assert args[2] == "active"


def test_sync_mdm_tracking_status_raises_on_db_failure(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _sync_mdm_tracking_status

    with patch("edgar_warehouse.mdm.database.get_engine", side_effect=Exception("DB down")):
        with pytest.raises(Exception, match="DB down"):
            _sync_mdm_tracking_status(1234, "active")


# ---------------------------------------------------------------------------
# _mdm_auto_enroll — best-effort, non-fatal
# ---------------------------------------------------------------------------

def test_mdm_auto_enroll_calls_bulk_upsert(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _mdm_auto_enroll

    with patch("edgar_warehouse.mdm.database.get_engine", return_value=MagicMock()):
        with patch("edgar_warehouse.mdm.universe.bulk_upsert_universe", return_value=3) as mock_upsert:
            _mdm_auto_enroll([100, 200, 300], scope_reason="daily_index")

    mock_upsert.assert_called_once()
    rows_arg = mock_upsert.call_args[0][1]
    assert {r["cik"] for r in rows_arg} == {100, 200, 300}


def test_mdm_auto_enroll_is_noop_without_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _mdm_auto_enroll
    _mdm_auto_enroll([100, 200], scope_reason="daily_index")  # must not raise


def test_mdm_auto_enroll_does_not_raise_on_db_failure(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _mdm_auto_enroll

    with patch("edgar_warehouse.mdm.database.get_engine", side_effect=Exception("DB down")):
        _mdm_auto_enroll([100], scope_reason="daily_index")  # must not raise


# ---------------------------------------------------------------------------
# _resolve_bootstrap_target_ciks — cik_limit/cik_offset (Wave 0 stubs)
# ---------------------------------------------------------------------------

def test_resolve_bootstrap_target_ciks_applies_cik_offset_then_cik_limit(monkeypatch):
    """_resolve_bootstrap_target_ciks honors cik_limit/cik_offset when both are provided.

    Verifies that offset is applied before limit:
    input [100, 200, 300, 400, 500], offset=1, limit=2 -> [200, 300]
    """
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_bootstrap_target_ciks

    db = MagicMock()
    db.get_tracked_ciks.return_value = [100, 200, 300, 400, 500]
    result = _resolve_bootstrap_target_ciks(
        db=db,
        raw_ciks=None,
        command_name="bootstrap-full",
        tracking_status_filter="active",
        cik_limit=2,
        cik_offset=1,
    )

    assert result == [200, 300]


def test_apply_bronze_cik_limit_emits_deprecation_warning(monkeypatch):
    """WAREHOUSE_BRONZE_CIK_LIMIT env var emits DeprecationWarning when set."""
    monkeypatch.setenv("WAREHOUSE_BRONZE_CIK_LIMIT", "3")
    from edgar_warehouse.application.warehouse_orchestrator import _apply_bronze_cik_limit

    with pytest.warns(DeprecationWarning, match="WAREHOUSE_BRONZE_CIK_LIMIT"):
        result = _apply_bronze_cik_limit([100, 200, 300, 400, 500])

    assert result == [100, 200, 300]


# ---------------------------------------------------------------------------
# _publish_silver_database_if_remote
# ---------------------------------------------------------------------------

def test_publish_silver_database_returns_none_for_local_storage(tmp_path):
    """Local storage_root → skip upload, return None."""
    context = WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="dev@example.com",
        runtime_mode="bronze_capture",
    )

    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_if_remote,
    )
    result = _publish_silver_database_if_remote(context)
    assert result is None


def test_publish_silver_database_uploads_to_remote(tmp_path):
    """Remote storage_root, no canonical yet → stage+promote candidate as-is, no merge."""
    from edgar_warehouse.infrastructure.object_storage import ObjectVersion, PromotionResult

    context = WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation("s3://bucket/warehouse"),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="dev@example.com",
        runtime_mode="bronze_capture",
    )
    silver_db = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))
    silver_db.parent.mkdir(parents=True)
    silver_db.write_bytes(b"duckdb-data")

    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_if_remote,
    )
    with (
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.read_object_version",
            return_value=ObjectVersion(exists=False, etag=None, version_id=None),
        ),
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.write_staged_bytes",
            return_value="_staging/token/silver/sec/silver.duckdb",
        ) as mock_stage,
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.promote_staged",
            return_value=PromotionResult(
                canonical_path="s3://bucket/warehouse/silver/sec/silver.duckdb",
                staged_relative_path="_staging/token/silver/sec/silver.duckdb",
                previous_version=ObjectVersion(exists=False, etag=None, version_id=None),
                new_version=ObjectVersion(exists=True, etag="new-etag", version_id=None),
            ),
        ) as mock_promote,
    ):
        result = _publish_silver_database_if_remote(context)

    assert result is not None
    assert result["layer"] == "silver_database"
    assert result["relative_path"] == "silver/sec/silver.duckdb"
    assert result["size_bytes"] == len(b"duckdb-data")
    assert result["source_version"] is None
    assert result["canonical_version"] == "new-etag"
    assert result["tables_merged"] == []
    mock_stage.assert_called_once_with("silver/sec/silver.duckdb", b"duckdb-data")
    mock_promote.assert_called_once_with(
        "_staging/token/silver/sec/silver.duckdb", "silver/sec/silver.duckdb", expected_etag=None
    )


def test_publish_silver_database_raises_when_file_missing(tmp_path):
    """Missing local silver DB → WarehouseRuntimeError (not silent data loss)."""
    context = WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation("s3://bucket/warehouse"),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="dev@example.com",
        runtime_mode="bronze_capture",
    )

    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_if_remote,
    )

    with pytest.raises(WarehouseRuntimeError, match="not found"):
        _publish_silver_database_if_remote(context)


def test_publish_silver_database_merges_when_canonical_already_exists(tmp_path):
    """Remote storage_root with an existing canonical → merge, not blind overwrite."""
    from edgar_warehouse.infrastructure.object_storage import ObjectVersion, PromotionResult

    context = WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation("s3://bucket/warehouse"),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="dev@example.com",
        runtime_mode="bronze_capture",
    )
    silver_db = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))
    silver_db.parent.mkdir(parents=True)
    conn = duckdb.connect(str(silver_db))
    conn.execute("CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, last_synced_at TIMESTAMPTZ)")
    conn.execute("INSERT INTO sec_company VALUES (3, 'Gamma LLC', '2026-01-01 00:00:00')")
    conn.close()

    canonical_db = tmp_path / "canonical.duckdb"
    conn = duckdb.connect(str(canonical_db))
    conn.execute("CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, last_synced_at TIMESTAMPTZ)")
    conn.execute("INSERT INTO sec_company VALUES (1, 'Alpha Corp', '2026-01-01 00:00:00')")
    conn.close()
    canonical_bytes = canonical_db.read_bytes()

    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_if_remote,
    )
    with (
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.read_object_version",
            return_value=ObjectVersion(exists=True, etag="old-etag", version_id=None),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
            return_value=canonical_bytes,
        ),
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.write_staged_bytes",
            return_value="_staging/token/silver/sec/silver.duckdb",
        ),
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.promote_staged",
            return_value=PromotionResult(
                canonical_path="s3://bucket/warehouse/silver/sec/silver.duckdb",
                staged_relative_path="_staging/token/silver/sec/silver.duckdb",
                previous_version=ObjectVersion(exists=True, etag="old-etag", version_id=None),
                new_version=ObjectVersion(exists=True, etag="new-etag", version_id=None),
            ),
        ) as mock_promote,
    ):
        result = _publish_silver_database_if_remote(context)

    assert result["tables_merged"] == ["sec_company"]
    assert result["source_version"] == "old-etag"
    assert result["canonical_version"] == "new-etag"
    # The staged payload must contain BOTH the canonical-only row and the
    # candidate-only row -- a merge, not the candidate replacing canonical.
    staged_payload = mock_promote.call_args.args[0]
    assert isinstance(staged_payload, str)  # staged relative path was passed through


def test_publish_silver_database_propagates_ambiguous_conflict(tmp_path):
    """A same-key row differing with no declared authority column aborts publication."""
    from edgar_warehouse.infrastructure.object_storage import ObjectVersion
    from edgar_warehouse.silver_protection import SemanticMergeConflictError

    context = WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation("s3://bucket/warehouse"),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="dev@example.com",
        runtime_mode="bronze_capture",
    )
    silver_db = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))
    silver_db.parent.mkdir(parents=True)
    conn = duckdb.connect(str(silver_db))
    conn.execute("CREATE TABLE sec_adv_filing (accession_number TEXT PRIMARY KEY, adviser_name TEXT)")
    conn.execute("INSERT INTO sec_adv_filing VALUES ('acc-1', 'Adviser B')")
    conn.close()

    canonical_db = tmp_path / "canonical.duckdb"
    conn = duckdb.connect(str(canonical_db))
    conn.execute("CREATE TABLE sec_adv_filing (accession_number TEXT PRIMARY KEY, adviser_name TEXT)")
    conn.execute("INSERT INTO sec_adv_filing VALUES ('acc-1', 'Adviser A')")
    conn.close()
    canonical_bytes = canonical_db.read_bytes()

    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_if_remote,
    )
    with (
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.read_object_version",
            return_value=ObjectVersion(exists=True, etag="old-etag", version_id=None),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
            return_value=canonical_bytes,
        ),
    ):
        with pytest.raises(SemanticMergeConflictError):
            _publish_silver_database_if_remote(context)


def _publish_context(tmp_path: Path) -> WarehouseCommandContext:
    context = WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation("s3://bucket/warehouse"),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="dev@example.com",
        runtime_mode="bronze_capture",
    )
    silver_db = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))
    silver_db.parent.mkdir(parents=True)
    silver_db.write_bytes(b"duckdb-data")
    return context


def test_publish_silver_database_retries_on_lost_promotion_race(tmp_path, monkeypatch):
    """Regression (2026-07-22): Ticket 20 runs concurrent Distributed Map
    batches that all publish to the same canonical silver.duckdb.
    PromotionConflictError's own docstring says it is retryable ("the staged
    object is left in place ... so a caller can re-read canonical, re-merge,
    and retry promotion"), but no caller ever did -- so the first batch to
    publish always won and every other concurrently-finishing batch failed
    outright, aborting the whole 0%-tolerance release even though its fetch
    and merge work was otherwise complete. A conflict on the first attempt
    must not be fatal if a later attempt succeeds."""
    from edgar_warehouse.infrastructure.object_storage import (
        ObjectVersion,
        PromotionConflictError,
        PromotionResult,
    )
    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_with_retry,
    )

    monkeypatch.setenv("WAREHOUSE_PUBLISH_CONFLICT_RETRY_BASE_SECONDS", "0.001")
    context = _publish_context(tmp_path)

    call_count = {"n": 0}

    def flaky_promote(staged_relative, relative_path, *, expected_etag):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise PromotionConflictError(relative_path, expected_etag, "someone-else-won", staged_relative)
        return PromotionResult(
            canonical_path="s3://bucket/warehouse/silver/sec/silver.duckdb",
            staged_relative_path=staged_relative,
            previous_version=ObjectVersion(exists=False, etag=None, version_id=None),
            new_version=ObjectVersion(exists=True, etag="new-etag", version_id=None),
        )

    with (
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.read_object_version",
            return_value=ObjectVersion(exists=False, etag=None, version_id=None),
        ),
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.write_staged_bytes",
            return_value="_staging/token/silver/sec/silver.duckdb",
        ),
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.promote_staged",
            side_effect=flaky_promote,
        ),
    ):
        result = _publish_silver_database_with_retry(context)

    assert result is not None
    assert result["canonical_version"] == "new-etag"
    assert call_count["n"] == 2


def test_publish_silver_database_retry_gives_up_after_max_attempts(tmp_path, monkeypatch):
    from edgar_warehouse.infrastructure.object_storage import (
        ObjectVersion,
        PromotionConflictError,
    )
    from edgar_warehouse.application.warehouse_orchestrator import (
        _publish_silver_database_with_retry,
    )

    monkeypatch.setenv("WAREHOUSE_PUBLISH_CONFLICT_ATTEMPTS", "2")
    monkeypatch.setenv("WAREHOUSE_PUBLISH_CONFLICT_RETRY_BASE_SECONDS", "0.001")
    context = _publish_context(tmp_path)

    call_count = {"n": 0}

    def always_conflicts(staged_relative, relative_path, *, expected_etag):
        call_count["n"] += 1
        raise PromotionConflictError(relative_path, expected_etag, "someone-else-won", staged_relative)

    with (
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.read_object_version",
            return_value=ObjectVersion(exists=False, etag=None, version_id=None),
        ),
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.write_staged_bytes",
            return_value="_staging/token/silver/sec/silver.duckdb",
        ),
        patch(
            "edgar_warehouse.infrastructure.object_storage.StorageLocation.promote_staged",
            side_effect=always_conflicts,
        ),
    ):
        with pytest.raises(PromotionConflictError):
            _publish_silver_database_with_retry(context)

    assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# _is_transient_artifact_error — release-mode artifact retry classifier
# ---------------------------------------------------------------------------


def test_403_status_is_classified_transient(monkeypatch):
    """Regression (2026-07-21): Ticket 20's strict release aborted an entire
    116-batch run because a single SEC 403 (fetching a quarterly full-index
    file) was not classified transient, so the existing retry loop gave up
    immediately instead of retrying. SEC EDGAR is unauthenticated, so 403 on
    a validly-built archive URL is its rate-limit/edge signal, not a real
    permission denial -- confirmed transient by an immediate manual re-fetch
    succeeding, and confirmed NOT concurrency-driven since three sibling
    batches running at the same moment completed with zero errors."""
    from edgar_warehouse.application.warehouse_orchestrator import (
        _is_transient_artifact_error,
    )

    class _FakeResponse:
        status_code = 403

    class _FakeHTTPStatusError(Exception):
        def __init__(self):
            super().__init__("403 Forbidden")
            self.response = _FakeResponse()

    assert _is_transient_artifact_error(_FakeHTTPStatusError()) is True


def test_other_retryable_statuses_remain_classified_transient(monkeypatch):
    from edgar_warehouse.application.warehouse_orchestrator import (
        _is_transient_artifact_error,
    )

    class _FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    class _FakeHTTPStatusError(Exception):
        def __init__(self, status_code):
            super().__init__(f"{status_code} error")
            self.response = _FakeResponse(status_code)

    for status_code in (408, 429, 500, 502, 503, 504):
        assert _is_transient_artifact_error(_FakeHTTPStatusError(status_code)) is True


def test_404_status_is_not_classified_transient():
    """A genuinely missing resource must not be retried -- retrying a 404
    just burns three attempts on a document that will never appear."""
    from edgar_warehouse.application.warehouse_orchestrator import (
        _is_transient_artifact_error,
    )

    class _FakeResponse:
        status_code = 404

    class _FakeHTTPStatusError(Exception):
        def __init__(self):
            super().__init__("404 Not Found")
            self.response = _FakeResponse()

    assert _is_transient_artifact_error(_FakeHTTPStatusError()) is False


def test_plain_value_error_is_not_classified_transient():
    from edgar_warehouse.application.warehouse_orchestrator import (
        _is_transient_artifact_error,
    )

    assert _is_transient_artifact_error(ValueError("no attachments found")) is False


def test_connection_error_is_classified_transient():
    from edgar_warehouse.application.warehouse_orchestrator import (
        _is_transient_artifact_error,
    )

    assert _is_transient_artifact_error(ConnectionError("connection reset")) is True
    assert _is_transient_artifact_error(TimeoutError("timed out")) is True


# ---------------------------------------------------------------------------
# silver_protection.merge_candidate_into_canonical — core merge semantics
# (ARTF-01: protected-table registry + fail-closed publication)
# ---------------------------------------------------------------------------


def _make_duckdb(path: Path, ddl: str, rows: list[str]) -> None:
    conn = duckdb.connect(str(path))
    conn.execute(ddl)
    for row_sql in rows:
        conn.execute(row_sql)
    conn.close()


def test_merge_preserves_canonical_only_rows_from_a_partial_candidate(tmp_path):
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, last_synced_at TIMESTAMPTZ)"
    _make_duckdb(
        canonical,
        ddl,
        [
            "INSERT INTO sec_company VALUES (1, 'Alpha Corp', '2026-01-01 00:00:00')",
            "INSERT INTO sec_company VALUES (2, 'Beta Inc', '2026-01-01 00:00:00')",
        ],
    )
    _make_duckdb(candidate, ddl, ["INSERT INTO sec_company VALUES (3, 'Gamma LLC', '2026-01-01 00:00:00')"])

    result = merge_candidate_into_canonical(candidate, canonical, output)

    conn = duckdb.connect(str(output))
    rows = conn.execute("SELECT cik, entity_name FROM sec_company ORDER BY cik").fetchall()
    conn.close()
    assert rows == [(1, "Alpha Corp"), (2, "Beta Inc"), (3, "Gamma LLC")]
    assert result.rows_inserted["sec_company"] == 1


def test_merge_only_reads_canonical_rows_the_candidate_touches(tmp_path):
    """Regression (2026-07-20): merge_candidate_into_canonical unconditionally
    loaded the FULL canonical table into Python dicts on every publish,
    regardless of candidate size. Production sec_company_filing has 2.1M+
    rows; a 4-CIK company-identity candidate against it silently OOM-killed
    the ECS/Fargate task mid-merge (no error logged, canonical never updated).
    A canonical row whose key the candidate never touches can never be
    looked up by the merge loop, so it must never need to be read at all --
    proven here by scaling canonical far beyond what fetching everything
    into Python could tolerate inside a bounded-memory unit test process,
    while the candidate stays tiny."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = "CREATE TABLE sec_company_filing (accession_number TEXT PRIMARY KEY, cik BIGINT, last_synced_at TIMESTAMPTZ)"

    conn = duckdb.connect(str(canonical))
    conn.execute(ddl)
    conn.execute(
        "INSERT INTO sec_company_filing "
        "SELECT 'acc-' || i, i, TIMESTAMP '2026-01-01 00:00:00' "
        "FROM range(200000) AS t(i)"
    )
    conn.close()

    _make_duckdb(
        candidate,
        ddl,
        [
            "INSERT INTO sec_company_filing VALUES "
            "('acc-5', 5, '2026-02-01 00:00:00')",  # existing key, updated value
            "INSERT INTO sec_company_filing VALUES "
            "('acc-brand-new', 999999, '2026-02-01 00:00:00')",  # new key
        ],
    )

    result = merge_candidate_into_canonical(candidate, canonical, output)

    assert result.rows_inserted["sec_company_filing"] == 1
    assert result.rows_updated["sec_company_filing"] == 1

    conn = duckdb.connect(str(output))
    total = conn.execute("SELECT COUNT(*) FROM sec_company_filing").fetchone()[0]
    updated_row = conn.execute(
        "SELECT last_synced_at FROM sec_company_filing WHERE accession_number = 'acc-5'"
    ).fetchone()
    untouched_row = conn.execute(
        "SELECT last_synced_at FROM sec_company_filing WHERE accession_number = 'acc-6'"
    ).fetchone()
    conn.close()
    assert total == 200001
    assert str(updated_row[0]).startswith("2026-02-01")
    assert str(untouched_row[0]).startswith("2026-01-01")  # untouched canonical row preserved


def test_merge_only_reads_candidate_rows_that_actually_changed(tmp_path):
    """Regression (2026-07-21): bootstrap-fundamentals' windowed
    (--cik-offset/--cik-limit) publish path -- used by entity-facts,
    per-filing, thirteenf, and now company-identity's bulk mode -- hydrates
    the FULL canonical DB before mutating a handful of rows in place, so the
    "candidate" file can be as large as canonical itself even when a run
    only touches a few hundred CIKs. The previous fix
    (test_merge_only_reads_canonical_rows_the_candidate_touches) only bounded
    the canonical-side lookup; it assumed the candidate itself was already
    small, which doesn't hold for this shape. Prove the delta-based fetch
    handles a full-copy candidate (canonical-sized, mostly identical to
    canonical) without materializing the untouched rows."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = "CREATE TABLE sec_company_filing (accession_number TEXT PRIMARY KEY, cik BIGINT, last_synced_at TIMESTAMPTZ)"

    conn = duckdb.connect(str(canonical))
    conn.execute(ddl)
    conn.execute(
        "INSERT INTO sec_company_filing "
        "SELECT 'acc-' || i, i, TIMESTAMP '2026-01-01 00:00:00' "
        "FROM range(200000) AS t(i)"
    )
    conn.close()

    # Candidate = a full copy of canonical (the windowed hydrate-then-mutate
    # shape), with just two rows changed: one existing key updated, one brand
    # new key inserted -- everything else byte-identical to canonical.
    shutil.copy2(canonical, candidate)
    conn = duckdb.connect(str(candidate))
    conn.execute(
        "UPDATE sec_company_filing SET last_synced_at = '2026-02-01 00:00:00' "
        "WHERE accession_number = 'acc-5'"
    )
    conn.execute(
        "INSERT INTO sec_company_filing VALUES ('acc-brand-new', 999999, '2026-02-01 00:00:00')"
    )
    conn.close()

    result = merge_candidate_into_canonical(candidate, canonical, output)

    assert result.rows_inserted["sec_company_filing"] == 1
    assert result.rows_updated["sec_company_filing"] == 1
    assert result.rows_unchanged.get("sec_company_filing", 0) == 0

    conn = duckdb.connect(str(output))
    total = conn.execute("SELECT COUNT(*) FROM sec_company_filing").fetchone()[0]
    updated_row = conn.execute(
        "SELECT last_synced_at FROM sec_company_filing WHERE accession_number = 'acc-5'"
    ).fetchone()
    untouched_row = conn.execute(
        "SELECT last_synced_at FROM sec_company_filing WHERE accession_number = 'acc-6'"
    ).fetchone()
    conn.close()
    assert total == 200001
    assert str(updated_row[0]).startswith("2026-02-01")
    assert str(untouched_row[0]).startswith("2026-01-01")  # untouched row preserved


def test_merge_first_publish_of_new_classified_table_preserves_primary_key(tmp_path):
    """Regression (2026-07-21): the "new classified domain table, first time
    it's being published" branch created the canonical-side table via
    ``CREATE TABLE ... AS SELECT * FROM cand ... WHERE 1=0``, which copies
    column names/types but drops PRIMARY KEY/NOT NULL constraints. Production
    canonical silver.duckdb ended up with sec_employment_event and
    sec_thirteenf_filing carrying zero constraints (confirmed via
    duckdb_constraints()), so a later INSERT ... ON CONFLICT against either
    table failed with "specified columns as conflict target are not
    referenced by a UNIQUE/PRIMARY KEY CONSTRAINT" even on an empty table --
    DuckDB validates the ON CONFLICT target against the schema, not the
    data. Canonical starts here with the table entirely absent (the true
    first-publish shape); the merged output's table must carry the same
    PRIMARY KEY declared in silver_store.py's _DDL."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"

    # Canonical has no tables at all yet -- sec_employment_event has never
    # been published, matching the actual production first-publish gap.
    duckdb.connect(str(canonical)).close()

    ddl = """
    CREATE TABLE sec_employment_event (
        accession_number    TEXT NOT NULL,
        event_index         BIGINT NOT NULL,
        cik                 BIGINT NOT NULL,
        event_type          TEXT NOT NULL,
        person_name         TEXT NOT NULL,
        exec_role           TEXT,
        previous_role       TEXT,
        compensation_amount DOUBLE,
        effective_date      DATE NOT NULL,
        parser_version      TEXT NOT NULL,
        ingested_at         TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (accession_number, event_index)
    )
    """
    _make_duckdb(
        candidate,
        ddl,
        [
            "INSERT INTO sec_employment_event VALUES "
            "('acc-1', 0, 1, 'appointment', 'Jane Doe', 'CEO', NULL, NULL, "
            "'2026-01-01', 'v1', '2026-01-01 00:00:00')"
        ],
    )

    result = merge_candidate_into_canonical(candidate, canonical, output)
    assert result.rows_inserted["sec_employment_event"] == 1

    conn = duckdb.connect(str(output))
    pk = conn.execute(
        "SELECT constraint_column_names FROM duckdb_constraints() "
        "WHERE table_name = 'sec_employment_event' AND constraint_type = 'PRIMARY KEY'"
    ).fetchall()
    assert pk == [(["accession_number", "event_index"],)]

    # The constraint must actually be enforced, not merely reported -- an
    # INSERT ... ON CONFLICT against these exact columns must bind cleanly.
    conn.execute(
        "INSERT INTO sec_employment_event VALUES "
        "('acc-1', 0, 1, 'appointment', 'Jane Doe Updated', 'CEO', NULL, NULL, "
        "'2026-01-01', 'v2', '2026-02-01 00:00:00') "
        "ON CONFLICT (accession_number, event_index) DO UPDATE SET person_name = EXCLUDED.person_name"
    )
    updated = conn.execute(
        "SELECT person_name FROM sec_employment_event WHERE accession_number = 'acc-1' AND event_index = 0"
    ).fetchone()
    conn.close()
    assert updated == ("Jane Doe Updated",)


def test_merge_resolves_same_key_conflict_via_declared_authority_column(tmp_path):
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, last_synced_at TIMESTAMPTZ)"
    _make_duckdb(canonical, ddl, ["INSERT INTO sec_company VALUES (1, 'Alpha Corp', '2026-01-01 00:00:00')"])
    _make_duckdb(candidate, ddl, ["INSERT INTO sec_company VALUES (1, 'Alpha Corporation', '2026-02-01 00:00:00')"])

    result = merge_candidate_into_canonical(candidate, canonical, output)

    conn = duckdb.connect(str(output))
    rows = conn.execute("SELECT entity_name FROM sec_company WHERE cik = 1").fetchall()
    conn.close()
    assert rows == [("Alpha Corporation",)]
    assert result.rows_updated["sec_company"] == 1


def test_merge_keeps_canonical_when_candidate_is_older(tmp_path):
    """A stale candidate (older last_synced_at) must not regress canonical."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, last_synced_at TIMESTAMPTZ)"
    _make_duckdb(canonical, ddl, ["INSERT INTO sec_company VALUES (1, 'Alpha Corporation', '2026-02-01 00:00:00')"])
    _make_duckdb(candidate, ddl, ["INSERT INTO sec_company VALUES (1, 'Alpha Corp', '2026-01-01 00:00:00')"])

    merge_candidate_into_canonical(candidate, canonical, output)

    conn = duckdb.connect(str(output))
    rows = conn.execute("SELECT entity_name FROM sec_company WHERE cik = 1").fetchall()
    conn.close()
    assert rows == [("Alpha Corporation",)]


def test_merge_treats_raw_object_provenance_columns_as_non_conflicting(tmp_path):
    """Regression (2026-07-22): sec_raw_object's business key is raw_object_id
    alone -- a content hash -- so identical bytes legitimately recur under a
    different (cik, accession_number, source_url, storage_path) than
    canonical's first-seen record (shared boilerplate/exhibit templates,
    common XBRL taxonomy files). fetched_at authority can never resolve this:
    both sides carry forward the same original first-fetch timestamp, so it's
    always an exact tie -- production hit exactly this and aborted a batch
    that had already fetched all 789/789 required accessions cleanly, on 10
    such rows. cik/accession_number/source_url/storage_path are declared
    provenance for this table; a same-key row that only differs on those
    columns must be treated as unchanged, not an ambiguous conflict."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = (
        "CREATE TABLE sec_raw_object ("
        "raw_object_id TEXT PRIMARY KEY, cik BIGINT, accession_number TEXT, "
        "source_url TEXT, storage_path TEXT, fetched_at TIMESTAMPTZ)"
    )
    same_hash = "deadbeef" * 8
    # Canonical first saw this exact content under CIK 1 / accession-A.
    _make_duckdb(
        canonical,
        ddl,
        [
            f"INSERT INTO sec_raw_object VALUES ('{same_hash}', 1, 'acc-A', "
            "'https://sec.gov/a', 's3://bucket/a', '2026-01-01 00:00:00')"
        ],
    )
    # Candidate independently fetched the identical bytes under a different
    # CIK/accession -- the hydrated candidate carries forward canonical's
    # original fetched_at (an exact tie), matching the real production shape.
    _make_duckdb(
        candidate,
        ddl,
        [
            f"INSERT INTO sec_raw_object VALUES ('{same_hash}', 2, 'acc-B', "
            "'https://sec.gov/b', 's3://bucket/b', '2026-01-01 00:00:00')"
        ],
    )

    result = merge_candidate_into_canonical(candidate, canonical, output)

    assert result.rows_unchanged.get("sec_raw_object", 0) == 1
    assert result.rows_updated.get("sec_raw_object", 0) == 0
    conn = duckdb.connect(str(output))
    row = conn.execute(
        "SELECT cik, accession_number FROM sec_raw_object WHERE raw_object_id = ?", [same_hash]
    ).fetchone()
    conn.close()
    # Canonical's first-seen association is preserved -- not overwritten by
    # whichever accession happened to be in this candidate.
    assert row == (1, "acc-A")


def test_merge_treats_every_raw_object_fetch_context_column_as_non_conflicting(tmp_path):
    """Regression (2026-07-22): the first sec_raw_object provenance fix only
    listed cik/accession_number/source_url/storage_path by hand and missed
    `form` -- a follow-up production run hit the identical ambiguous-conflict
    class on 4 rows differing only on `form`. Since raw_object_id IS the
    content hash, every column except sha256/byte_size (intrinsic to the
    bytes) is fetch-context and must be provenance, not just the four
    originally listed. This test walks every such column against the real
    production DDL (silver_store.py) so a future column addition to the
    fetch-context group can't silently regress the same way."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = (
        "CREATE TABLE sec_raw_object ("
        "raw_object_id TEXT PRIMARY KEY, source_type TEXT, cik BIGINT, "
        "accession_number TEXT, form TEXT, source_url TEXT, storage_path TEXT, "
        "content_type TEXT, content_encoding TEXT, byte_size BIGINT, "
        "sha256 TEXT, fetched_at TIMESTAMPTZ, http_status INTEGER, "
        "source_last_modified TIMESTAMPTZ, source_etag TEXT)"
    )
    same_hash = "cafebabe" * 8
    _make_duckdb(
        canonical,
        ddl,
        [
            f"INSERT INTO sec_raw_object VALUES ("
            f"'{same_hash}', 'filing_document', 1, 'acc-A', '10-K', "
            f"'https://sec.gov/a', 's3://bucket/a', 'text/html', 'gzip', 1024, "
            f"'{same_hash}', '2026-01-01 00:00:00', 200, "
            f"'2026-01-01 00:00:00', 'etag-a')"
        ],
    )
    # Candidate independently fetched the identical bytes referenced from a
    # different form type/URL/etc -- everything but the content-derived
    # columns (sha256, byte_size) and the tied authority column differs.
    _make_duckdb(
        candidate,
        ddl,
        [
            f"INSERT INTO sec_raw_object VALUES ("
            f"'{same_hash}', 'attachment', 2, 'acc-B', '10-K/A', "
            f"'https://sec.gov/b', 's3://bucket/b', 'application/octet-stream', "
            f"'identity', 1024, '{same_hash}', '2026-01-01 00:00:00', 304, "
            f"'2026-02-01 00:00:00', 'etag-b')"
        ],
    )

    result = merge_candidate_into_canonical(candidate, canonical, output)

    assert result.rows_unchanged.get("sec_raw_object", 0) == 1
    assert result.rows_updated.get("sec_raw_object", 0) == 0


def test_merge_raises_row_level_conflict_report_when_ambiguous(tmp_path):
    from edgar_warehouse.silver_protection import SemanticMergeConflictError, merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = "CREATE TABLE sec_adv_filing (accession_number TEXT PRIMARY KEY, adviser_name TEXT)"
    _make_duckdb(canonical, ddl, ["INSERT INTO sec_adv_filing VALUES ('acc-1', 'Adviser A')"])
    _make_duckdb(candidate, ddl, ["INSERT INTO sec_adv_filing VALUES ('acc-1', 'Adviser B')"])

    with pytest.raises(SemanticMergeConflictError) as exc_info:
        merge_candidate_into_canonical(candidate, canonical, output)

    conflicts = exc_info.value.conflicts
    assert len(conflicts) == 1
    assert conflicts[0].table_name == "sec_adv_filing"
    assert conflicts[0].business_key == {"accession_number": "acc-1"}
    assert conflicts[0].differing_columns == ("adviser_name",)


def test_merge_ignores_provenance_only_difference_on_no_authority_table(tmp_path):
    """sec_company_former_name has no authority_column: a same-key row that
    differs only in last_sync_run_id (which run re-affirmed it, not business
    data) must merge as unchanged, not abort as an ambiguous conflict --
    otherwise every idempotent re-sync of an already-loaded CIK's former
    names would fail forever.
    """
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = (
        "CREATE TABLE sec_company_former_name (cik BIGINT, former_name TEXT, "
        "date_changed DATE, ordinal INTEGER, last_sync_run_id TEXT, "
        "PRIMARY KEY (cik, ordinal))"
    )
    _make_duckdb(
        canonical, ddl,
        ["INSERT INTO sec_company_former_name VALUES (320193, 'APPLE COMPUTER INC', '1997-01-01', 1, 'old-run-id')"],
    )
    _make_duckdb(
        candidate, ddl,
        ["INSERT INTO sec_company_former_name VALUES (320193, 'APPLE COMPUTER INC', '1997-01-01', 1, 'fresh-run-id')"],
    )

    result = merge_candidate_into_canonical(candidate, canonical, output)

    assert result.rows_unchanged["sec_company_former_name"] == 1
    assert result.rows_updated.get("sec_company_former_name", 0) == 0


def test_merge_still_raises_on_genuine_former_name_conflict(tmp_path):
    """A real difference in business data (former_name itself) on a table
    with no authority_column must still fail closed for manual review, even
    though provenance-only differences (test above) no longer do -- proves
    excluding last_sync_run_id from conflict detection didn't also mask real
    conflicts.
    """
    from edgar_warehouse.silver_protection import SemanticMergeConflictError, merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = (
        "CREATE TABLE sec_company_former_name (cik BIGINT, former_name TEXT, "
        "date_changed DATE, ordinal INTEGER, last_sync_run_id TEXT, "
        "PRIMARY KEY (cik, ordinal))"
    )
    _make_duckdb(
        canonical, ddl,
        ["INSERT INTO sec_company_former_name VALUES (320193, 'APPLE COMPUTER INC', '1997-01-01', 1, 'old-run-id')"],
    )
    _make_duckdb(
        candidate, ddl,
        ["INSERT INTO sec_company_former_name VALUES (320193, 'APPLE COMPUTER INCORPORATED', '1997-01-01', 1, 'fresh-run-id')"],
    )

    with pytest.raises(SemanticMergeConflictError) as exc_info:
        merge_candidate_into_canonical(candidate, canonical, output)

    conflicts = exc_info.value.conflicts
    assert len(conflicts) == 1
    assert conflicts[0].table_name == "sec_company_former_name"
    assert conflicts[0].differing_columns == ("former_name",)


def test_merge_fails_closed_on_unclassified_table(tmp_path):
    from edgar_warehouse.silver_protection import SilverPublicationError, merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = "CREATE TABLE totally_new_domain_table (id INTEGER PRIMARY KEY)"
    _make_duckdb(canonical, ddl, [])
    _make_duckdb(candidate, ddl, ["INSERT INTO totally_new_domain_table VALUES (1)"])

    with pytest.raises(SilverPublicationError, match="Unclassified"):
        merge_candidate_into_canonical(candidate, canonical, output)


def test_thirteenf_filing_and_employment_event_are_classified(tmp_path):
    """Regression (2026-07-20): sec_thirteenf_filing and sec_employment_event
    were present in silver_store.py's DDL but missing from
    PROTECTED_TABLE_REGISTRY, so every publish touching either table failed
    closed with "Unclassified silver table(s) block publication" -- surfaced
    by a real production bootstrap-fundamentals --mode company-identity run
    against a silver.duckdb that already had 13F/employment-event data."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = (
        "CREATE TABLE sec_thirteenf_filing "
        "(accession_number TEXT PRIMARY KEY, ingested_at TIMESTAMPTZ);"
        "CREATE TABLE sec_employment_event "
        "(accession_number TEXT, event_index BIGINT, ingested_at TIMESTAMPTZ, "
        "PRIMARY KEY (accession_number, event_index))"
    )
    _make_duckdb(canonical, ddl, [])
    _make_duckdb(
        candidate,
        ddl,
        [
            "INSERT INTO sec_thirteenf_filing VALUES ('acc-1', '2026-01-01 00:00:00')",
            "INSERT INTO sec_employment_event VALUES ('acc-2', 1, '2026-01-01 00:00:00')",
        ],
    )

    result = merge_candidate_into_canonical(candidate, canonical, output)

    assert result.rows_inserted["sec_thirteenf_filing"] == 1
    assert result.rows_inserted["sec_employment_event"] == 1


def test_migration_backup_tables_are_excluded_from_unclassified_check(tmp_path):
    """Regression (2026-07-24): a real production ingest-relationship-sources
    run hit SilverDatabase's fund_index BIGINT migration against a stale
    pre-migration silver.duckdb; the migration ran correctly (see
    test_silver_store_schema_migration.py), but the immediately-following
    publish step then failed closed on the migration's own
    backup_sec_adv_private_fund_fund_index_bigint_<timestamp> table --
    unclassified, since a runtime-timestamped name can never be
    pre-registered in EXCLUDED_OPERATIONAL_TABLES by exact match. Every
    backup-and-recreate schema migration (period_end PK, period_start PK,
    fund_index BIGINT) hits this same gap the first time it actually fires
    in a production store immediately followed by a publish."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, last_synced_at TIMESTAMPTZ)"
    _make_duckdb(canonical, ddl, [])
    _make_duckdb(
        candidate,
        ddl + "; CREATE TABLE backup_sec_adv_private_fund_fund_index_bigint_20260724160622919443 (id INTEGER)",
        ["INSERT INTO sec_company VALUES (1, 'Alpha Corp', '2026-01-01 00:00:00')"],
    )

    result = merge_candidate_into_canonical(candidate, canonical, output)

    assert result.rows_inserted["sec_company"] == 1


def test_every_silver_table_is_registered_or_excluded():
    """Architecture lock: every CREATE TABLE in silver_store.py's DDL must be
    either a ProtectedTablePolicy or an explicit operational exclusion --
    the same gap that caused the sec_thirteenf_filing/sec_employment_event
    regression must never silently reopen for a future table."""
    import re

    from edgar_warehouse import silver_store
    from edgar_warehouse.silver_protection import (
        EXCLUDED_OPERATIONAL_TABLES,
        PROTECTED_TABLE_REGISTRY,
    )

    ddl_text = Path(silver_store.__file__).read_text(encoding="utf-8")
    all_tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", ddl_text))
    assert all_tables, "expected to find silver table DDL"
    unclassified = all_tables - set(PROTECTED_TABLE_REGISTRY) - set(EXCLUDED_OPERATIONAL_TABLES)
    assert unclassified == set(), (
        f"tables missing a ProtectedTablePolicy or exclusion: {sorted(unclassified)}"
    )


def test_merge_ignores_excluded_operational_tables(tmp_path):
    """Operational/checkpoint tables are excluded from protection, not blocked."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = "CREATE TABLE sec_parse_run (parse_run_id TEXT PRIMARY KEY, status TEXT)"
    _make_duckdb(canonical, ddl, ["INSERT INTO sec_parse_run VALUES ('run-1', 'completed')"])
    _make_duckdb(candidate, ddl, ["INSERT INTO sec_parse_run VALUES ('run-2', 'running')"])

    result = merge_candidate_into_canonical(candidate, canonical, output)
    assert "sec_parse_run" not in result.tables_merged


def test_merge_permits_additive_schema_evolution(tmp_path):
    """Candidate declaring an extra column beyond canonical is allowed and preserved."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    _make_duckdb(
        canonical,
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, last_synced_at TIMESTAMPTZ)",
        ["INSERT INTO sec_company VALUES (1, 'Alpha Corp', '2026-01-01 00:00:00')"],
    )
    _make_duckdb(
        candidate,
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, last_synced_at TIMESTAMPTZ, sic TEXT)",
        ["INSERT INTO sec_company VALUES (2, 'Beta Inc', '2026-01-01 00:00:00', '7372')"],
    )

    merge_candidate_into_canonical(candidate, canonical, output)

    conn = duckdb.connect(str(output))
    columns = {row[0] for row in conn.execute("DESCRIBE sec_company").fetchall()}
    rows = conn.execute("SELECT cik, sic FROM sec_company ORDER BY cik").fetchall()
    conn.close()
    assert "sic" in columns
    assert rows == [(1, None), (2, "7372")]


def test_merge_fails_closed_on_dropped_canonical_column(tmp_path):
    """Candidate schema dropping a canonical column is destructive; ordinary merge refuses."""
    from edgar_warehouse.silver_protection import SilverPublicationError, merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    _make_duckdb(
        canonical,
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, sic TEXT)",
        ["INSERT INTO sec_company VALUES (1, 'Alpha Corp', '7372')"],
    )
    _make_duckdb(
        candidate,
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT)",
        ["INSERT INTO sec_company VALUES (2, 'Beta Inc')"],
    )

    with pytest.raises(SilverPublicationError, match="drops canonical column"):
        merge_candidate_into_canonical(candidate, canonical, output)


def test_merge_fails_closed_on_column_type_change(tmp_path):
    from edgar_warehouse.silver_protection import SilverPublicationError, merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    _make_duckdb(
        canonical,
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT)",
        ["INSERT INTO sec_company VALUES (1, 'Alpha Corp')"],
    )
    _make_duckdb(
        candidate,
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name INTEGER)",
        ["INSERT INTO sec_company VALUES (2, 42)"],
    )

    with pytest.raises(SilverPublicationError, match="changes column type"):
        merge_candidate_into_canonical(candidate, canonical, output)


def test_merge_publishes_a_new_classified_table_for_the_first_time(tmp_path):
    """A classified table that simply doesn't exist in canonical yet is not
    'unclassified'. The candidate here declares the real production DDL
    columns (matching silver_store.py's sec_thirteenf_holding schema) since
    a real candidate is always built via SilverDatabase, which uses that
    same DDL -- the first-publish branch now enforces the same
    dropped-column check as any later publish, so a candidate schema must
    satisfy it."""
    from edgar_warehouse.silver_protection import merge_candidate_into_canonical

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    _make_duckdb(canonical, "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT)", [])
    _make_duckdb(
        candidate,
        """
        CREATE TABLE sec_thirteenf_holding (
            cik                 BIGINT NOT NULL,
            accession_number    TEXT NOT NULL,
            holding_index       BIGINT NOT NULL,
            period_of_report    DATE NOT NULL,
            cusip               TEXT,
            issuer_name         TEXT,
            security_title      TEXT,
            shares_held         DOUBLE,
            market_value        DOUBLE,
            security_class      TEXT,
            put_call            TEXT,
            discretion_type     TEXT,
            voting_auth_sole    DOUBLE,
            voting_auth_shared  DOUBLE,
            voting_auth_none    DOUBLE,
            parser_version      TEXT,
            ingested_at         TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (cik, accession_number, holding_index)
        )
        """,
        [
            "INSERT INTO sec_thirteenf_holding "
            "(cik, accession_number, holding_index, period_of_report, issuer_name) "
            "VALUES (1, 'acc-1', 1, '2026-01-01', 'Issuer X')"
        ],
    )

    result = merge_candidate_into_canonical(candidate, canonical, output)
    assert "sec_thirteenf_holding" in result.tables_merged

    conn = duckdb.connect(str(output))
    rows = conn.execute("SELECT issuer_name FROM sec_thirteenf_holding").fetchall()
    pk = conn.execute(
        "SELECT constraint_column_names FROM duckdb_constraints() "
        "WHERE table_name = 'sec_thirteenf_holding' AND constraint_type = 'PRIMARY KEY'"
    ).fetchall()
    conn.close()
    assert rows == [("Issuer X",)]
    assert pk == [(["cik", "accession_number", "holding_index"],)]


# ---------------------------------------------------------------------------
# object_storage — staged optimistic-concurrency promotion (ARTF-02)
# ---------------------------------------------------------------------------


def test_read_object_version_reports_missing_object(tmp_path):
    from edgar_warehouse.infrastructure.object_storage import StorageLocation as SL

    storage = SL(str(tmp_path))
    version = storage.read_object_version("does/not/exist.duckdb")
    assert version.exists is False
    assert version.etag is None


def test_read_object_version_is_stable_for_unchanged_content(tmp_path):
    from edgar_warehouse.infrastructure.object_storage import StorageLocation as SL

    storage = SL(str(tmp_path))
    storage.write_bytes("silver/sec/silver.duckdb", b"same-bytes")
    first = storage.read_object_version("silver/sec/silver.duckdb")
    second = storage.read_object_version("silver/sec/silver.duckdb")
    assert first.exists is True
    assert first.etag == second.etag


def test_read_object_version_changes_when_content_changes(tmp_path):
    from edgar_warehouse.infrastructure.object_storage import StorageLocation as SL

    storage = SL(str(tmp_path))
    storage.write_bytes("silver/sec/silver.duckdb", b"version-a")
    before = storage.read_object_version("silver/sec/silver.duckdb")
    storage.write_bytes("silver/sec/silver.duckdb", b"version-b")
    after = storage.read_object_version("silver/sec/silver.duckdb")
    assert before.etag != after.etag


def test_write_staged_bytes_never_collides_with_canonical_or_itself(tmp_path):
    from edgar_warehouse.infrastructure.object_storage import StorageLocation as SL

    storage = SL(str(tmp_path))
    staged_one = storage.write_staged_bytes("silver/sec/silver.duckdb", b"payload-1")
    staged_two = storage.write_staged_bytes("silver/sec/silver.duckdb", b"payload-2")
    assert staged_one != staged_two
    assert staged_one != "silver/sec/silver.duckdb"
    assert not Path(storage.join("silver/sec/silver.duckdb")).exists()


def test_promote_staged_succeeds_when_canonical_etag_still_matches(tmp_path):
    from edgar_warehouse.infrastructure.object_storage import StorageLocation as SL

    storage = SL(str(tmp_path))
    storage.write_bytes("silver/sec/silver.duckdb", b"original")
    baseline = storage.read_object_version("silver/sec/silver.duckdb")

    staged = storage.write_staged_bytes("silver/sec/silver.duckdb", b"merged-result")
    result = storage.promote_staged(staged, "silver/sec/silver.duckdb", expected_etag=baseline.etag)

    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"merged-result"
    assert result.new_version.etag != baseline.etag


def test_promote_staged_raises_on_concurrent_canonical_change_and_preserves_staged_object(tmp_path):
    """A simulated concurrent canonical write between baseline-read and promote must abort."""
    from edgar_warehouse.infrastructure.object_storage import PromotionConflictError, StorageLocation as SL

    storage = SL(str(tmp_path))
    storage.write_bytes("silver/sec/silver.duckdb", b"original")
    baseline = storage.read_object_version("silver/sec/silver.duckdb")

    staged = storage.write_staged_bytes("silver/sec/silver.duckdb", b"merged-result")

    # Simulate a concurrent writer landing between baseline read and promotion.
    storage.write_bytes("silver/sec/silver.duckdb", b"concurrent-write")

    with pytest.raises(PromotionConflictError):
        storage.promote_staged(staged, "silver/sec/silver.duckdb", expected_etag=baseline.etag)

    # Canonical keeps the concurrent writer's content -- no last-writer-wins.
    assert Path(storage.join("silver/sec/silver.duckdb")).read_bytes() == b"concurrent-write"
    # Staged diagnostics are preserved for inspection/retry, not deleted.
    assert Path(storage.join(staged)).read_bytes() == b"merged-result"


# ---------------------------------------------------------------------------
# silver_protection — destructive repair contract (separate from --force)
# ---------------------------------------------------------------------------


def test_execute_silver_repair_requires_a_non_empty_reason(tmp_path):
    from edgar_warehouse.silver_protection import SilverRepairRequiresReasonError, execute_silver_repair

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    ddl = "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT)"
    _make_duckdb(canonical, ddl, [])
    _make_duckdb(candidate, ddl, [])

    with pytest.raises(SilverRepairRequiresReasonError):
        execute_silver_repair(
            candidate, canonical, output,
            table_name="sec_company", operator="ops@example.com", reason="   ",
        )


def test_execute_silver_repair_dry_run_computes_diff_without_mutating_output(tmp_path):
    from edgar_warehouse.silver_protection import execute_silver_repair

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    _make_duckdb(
        canonical,
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, sic TEXT)",
        ["INSERT INTO sec_company VALUES (1, 'Alpha Corp', '7372')"],
    )
    _make_duckdb(
        candidate,
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT)",
        ["INSERT INTO sec_company VALUES (1, 'Alpha Corp')"],
    )

    record = execute_silver_repair(
        candidate, canonical, output,
        table_name="sec_company", operator="ops@example.com", reason="drop deprecated sic column",
        dry_run=True,
    )

    assert record.applied is False
    assert record.diff.dropped_columns == ("sic",)
    assert record.diff.is_destructive is True
    assert not output.exists()


def test_execute_silver_repair_applies_destructive_change_when_not_dry_run(tmp_path):
    from edgar_warehouse.silver_protection import execute_silver_repair

    canonical = tmp_path / "canonical.duckdb"
    candidate = tmp_path / "candidate.duckdb"
    output = tmp_path / "output.duckdb"
    _make_duckdb(
        canonical,
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT, sic TEXT)",
        ["INSERT INTO sec_company VALUES (1, 'Alpha Corp', '7372')"],
    )
    _make_duckdb(
        candidate,
        "CREATE TABLE sec_company (cik BIGINT PRIMARY KEY, entity_name TEXT)",
        ["INSERT INTO sec_company VALUES (1, 'Alpha Corp')"],
    )

    record = execute_silver_repair(
        candidate, canonical, output,
        table_name="sec_company", operator="ops@example.com", reason="drop deprecated sic column",
        dry_run=False,
    )

    assert record.applied is True
    conn = duckdb.connect(str(output))
    columns = {row[0] for row in conn.execute("DESCRIBE sec_company").fetchall()}
    conn.close()
    assert "sic" not in columns


# ---------------------------------------------------------------------------
# bootstrap_fundamentals.execute — upload block wiring
# ---------------------------------------------------------------------------

def test_bootstrap_fundamentals_skips_upload_without_storage_root(
    tmp_path, monkeypatch
):
    """No WAREHOUSE_STORAGE_ROOT → publish helper returns None."""
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.delenv("WAREHOUSE_STORAGE_ROOT", raising=False)
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

    from edgar_warehouse.application.commands import bootstrap_fundamentals

    with patch(
        "edgar_warehouse.application.commands.bootstrap_fundamentals._resolve_fundamentals_ciks",
        return_value=[320193],
    ), patch(
        "edgar_warehouse.silver_support.session.open_silver_database"
    ) as mock_open, patch(
        "edgar_warehouse.application.workflows.fundamentals_ingest.run_bootstrap_entity_facts",
        return_value={"entity_facts_written": 1},
    ), patch(
        "edgar_warehouse.parsers.accounting_flags.backfill_accounting_flags",
        return_value=0,
    ), patch(
        "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_if_remote",
        return_value=None,
    ) as mock_upload:
        mock_db = MagicMock()
        mock_open.return_value = mock_db

        class _Args:
            cik_list = [320193]
            mode = "entity-facts"
            run_id = "test-run"
            silver_root = None
            cik_offset = 0
            cik_limit = None

        rc = bootstrap_fundamentals.execute(_Args())

    assert rc == 0
    mock_upload.assert_called_once()


def test_bootstrap_fundamentals_uses_unified_silver_database(
    tmp_path, monkeypatch
):
    """Issue 3: Branch B writes to the canonical SEC silver database, not a separate shard."""
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(tmp_path / "warehouse"))
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

    from edgar_warehouse.application.commands import bootstrap_fundamentals

    with patch(
        "edgar_warehouse.application.commands.bootstrap_fundamentals._resolve_fundamentals_ciks",
        return_value=[320193],
    ), patch(
        "edgar_warehouse.silver_support.session.open_silver_database"
    ) as mock_open_database, patch(
        "edgar_warehouse.silver_support.session.open_silver_shard"
    ) as mock_open_shard, patch(
        "edgar_warehouse.application.workflows.fundamentals_ingest.run_bootstrap_entity_facts",
        return_value={"entity_facts_written": 1},
    ), patch(
        "edgar_warehouse.parsers.accounting_flags.backfill_accounting_flags",
        return_value=0,
    ):
        mock_db = MagicMock()
        mock_open_database.return_value = mock_db

        class _Args:
            cik_list = [320193]
            mode = "entity-facts"
            run_id = "test-run"
            silver_root = None
            cik_offset = 0
            cik_limit = None

        rc = bootstrap_fundamentals.execute(_Args())

    assert rc == 0
    mock_open_database.assert_called_once()
    assert mock_open_database.call_args[0][0].root == str(tmp_path / "silver")
    mock_open_shard.assert_not_called()


def test_bootstrap_fundamentals_upload_failure_returns_exit_code_1(
    tmp_path, monkeypatch
):
    """Upload error → exit code 1 (distinct from config error 2)."""
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", "s3://bucket/warehouse")
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

    from edgar_warehouse.application.commands import bootstrap_fundamentals

    with patch(
        "edgar_warehouse.application.commands.bootstrap_fundamentals._resolve_fundamentals_ciks",
        return_value=[320193],
    ), patch(
        "edgar_warehouse.silver_support.session.open_silver_database"
    ) as mock_open, patch(
        "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
    ), patch(
        "edgar_warehouse.application.workflows.fundamentals_ingest.run_bootstrap_entity_facts",
        return_value={"entity_facts_written": 1},
    ), patch(
        "edgar_warehouse.parsers.accounting_flags.backfill_accounting_flags",
        return_value=0,
    ), patch(
        "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_if_remote",
        side_effect=WarehouseRuntimeError("S3 write failed"),
    ):
        mock_db = MagicMock()
        mock_open.return_value = mock_db

        class _Args:
            cik_list = [320193]
            mode = "entity-facts"
            run_id = "test-run"
            silver_root = None
            cik_offset = 0
            cik_limit = None

        rc = bootstrap_fundamentals.execute(_Args())

    assert rc == 1


def test_bootstrap_fundamentals_upload_success_sets_metrics(
    tmp_path, monkeypatch
):
    """Upload succeeds → metrics carry uploaded=True and size_bytes, rc=0."""
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", "s3://bucket/warehouse")
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

    from edgar_warehouse.application.commands import bootstrap_fundamentals

    upload_record = {
        "layer": "silver_database",
        "path": "s3://bucket/warehouse/silver/sec/silver.duckdb",
        "relative_path": "silver/sec/silver.duckdb",
        "size_bytes": len(b"duckdb"),
    }

    with patch(
        "edgar_warehouse.application.commands.bootstrap_fundamentals._resolve_fundamentals_ciks",
        return_value=[320193],
    ), patch(
        "edgar_warehouse.silver_support.session.open_silver_database"
    ) as mock_open, patch(
        "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
    ), patch(
        "edgar_warehouse.application.workflows.fundamentals_ingest.run_bootstrap_entity_facts",
        return_value={"entity_facts_written": 1},
    ), patch(
        "edgar_warehouse.parsers.accounting_flags.backfill_accounting_flags",
        return_value=0,
    ), patch(
        "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_if_remote",
        return_value=upload_record,
    ):
        mock_db = MagicMock()
        mock_open.return_value = mock_db

        buf = io.StringIO()

        class _Args:
            cik_list = [320193]
            mode = "entity-facts"
            run_id = "test-run"
            silver_root = None
            cik_offset = 0
            cik_limit = None

        with redirect_stdout(buf):
            rc = bootstrap_fundamentals.execute(_Args())

    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["metrics"]["silver_database_uploaded"] is True
    assert payload["metrics"]["silver_database_size_bytes"] == len(b"duckdb")
