"""Tests that MDM (mdm_company.tracking_status) is the sole system of record
for company universe tracking. Silver DuckDB fallbacks have been removed.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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
# _filter_ciks_to_universe — MDM only, no DuckDB fallback
# ---------------------------------------------------------------------------

def test_filter_ciks_to_universe_filters_by_mdm(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
        return_value=[100, 200],
    ):
        result = _filter_ciks_to_universe([100, 200, 300])

    assert result == [100, 200]


def test_filter_ciks_to_universe_passes_through_when_mdm_empty(monkeypatch):
    """Cold-start guard: if MDM returns no active CIKs, pass all impacted CIKs through."""
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
        return_value=[],
    ):
        result = _filter_ciks_to_universe([100, 200, 300])

    assert result == [100, 200, 300]


def test_filter_ciks_to_universe_raises_without_mdm_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    with pytest.raises(WarehouseRuntimeError, match="MDM_DATABASE_URL is required"):
        _filter_ciks_to_universe([100, 200, 300])


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

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
        return_value=[100, 200, 300, 400, 500],
    ):
        result = _resolve_bootstrap_target_ciks(
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
