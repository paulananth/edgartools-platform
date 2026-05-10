"""Tests that the warehouse orchestrator reads/writes tracked universe via MDM when configured."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _make_mock_db(ciks: list[int]) -> MagicMock:
    db = MagicMock()
    db.get_tracked_universe_ciks.return_value = ciks
    return db


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
# _get_mdm_tracked_ciks
# ---------------------------------------------------------------------------

def test_get_mdm_tracked_ciks_returns_empty_without_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _get_mdm_tracked_ciks
    assert _get_mdm_tracked_ciks("active") == []


def test_get_mdm_tracked_ciks_returns_empty_on_exception(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    with patch("edgar_warehouse.mdm.database.get_engine", side_effect=Exception("no DB")):
        from edgar_warehouse.application.warehouse_orchestrator import _get_mdm_tracked_ciks
        assert _get_mdm_tracked_ciks("active") == []


# ---------------------------------------------------------------------------
# _resolve_target_ciks — MDM-first, DuckDB fallback
# ---------------------------------------------------------------------------

def test_resolve_target_ciks_uses_mdm_when_configured(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
        return_value=[100, 200],
    ):
        db = _make_mock_db([999])
        result = _resolve_target_ciks(
            db=db,
            raw_ciks=None,
            command_name="bootstrap-full",
            tracking_status_filter="active",
        )

    assert result == [100, 200]
    db.get_tracked_universe_ciks.assert_not_called()


def test_resolve_target_ciks_falls_back_to_duckdb_when_mdm_empty(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
        return_value=[],
    ):
        db = _make_mock_db([100, 200])
        result = _resolve_target_ciks(
            db=db,
            raw_ciks=None,
            command_name="bootstrap-full",
            tracking_status_filter="active",
        )

    assert result == [100, 200]
    db.get_tracked_universe_ciks.assert_called_once_with(status_filter="active")


def test_resolve_target_ciks_uses_duckdb_when_no_mdm_url(monkeypatch):
    """Without MDM_DATABASE_URL, _get_mdm_tracked_ciks returns [] and DuckDB is used."""
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    db = _make_mock_db([100])
    result = _resolve_target_ciks(
        db=db,
        raw_ciks=None,
        command_name="bootstrap-full",
        tracking_status_filter="active",
    )

    db.get_tracked_universe_ciks.assert_called_once_with(status_filter="active")
    assert result == [100]


def test_resolve_target_ciks_respects_raw_ciks(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_target_ciks

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks"
    ) as mock_mdm:
        db = _make_mock_db([999])
        result = _resolve_target_ciks(
            db=db,
            raw_ciks=["12345", "67890"],
            command_name="bootstrap-full",
            tracking_status_filter="active",
        )

    mock_mdm.assert_not_called()
    assert result == [12345, 67890]


# ---------------------------------------------------------------------------
# _filter_ciks_to_universe — MDM-first, DuckDB fallback
# ---------------------------------------------------------------------------

def test_filter_ciks_to_universe_checks_mdm_first(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
        return_value=[100, 200],
    ):
        db = _make_mock_db([999])
        result = _filter_ciks_to_universe([100, 200, 300], db)

    assert result == [100, 200]
    db.get_tracked_universe_ciks.assert_not_called()


def test_filter_ciks_to_universe_falls_back_to_duckdb(monkeypatch):
    """Without MDM_DATABASE_URL, _get_mdm_tracked_ciks returns [] and DuckDB filters."""
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    db = _make_mock_db([100, 200])
    result = _filter_ciks_to_universe([100, 200, 300], db)

    db.get_tracked_universe_ciks.assert_called_once_with(status_filter="active")
    assert result == [100, 200]


# ---------------------------------------------------------------------------
# _sync_mdm_tracking_status
# ---------------------------------------------------------------------------

def test_sync_mdm_tracking_status_no_op_without_url(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _sync_mdm_tracking_status
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


def test_sync_mdm_tracking_status_swallows_exceptions(monkeypatch):
    monkeypatch.setenv("MDM_DATABASE_URL", "postgresql://localhost/test")
    from edgar_warehouse.application.warehouse_orchestrator import _sync_mdm_tracking_status

    with patch("edgar_warehouse.mdm.database.get_engine", side_effect=Exception("DB down")):
        _sync_mdm_tracking_status(1234, "active")


def test_filter_ciks_to_universe_passes_through_when_tracked_empty(monkeypatch):
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    db = _make_mock_db([])
    result = _filter_ciks_to_universe([100, 200, 300], db)
    assert result == [100, 200, 300]
