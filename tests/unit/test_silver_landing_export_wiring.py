"""Orchestrator-level wiring for the silver landing-zone export.

silver-snowflake-migration map, Ticket 01/build phase: LandingExportBuffer
and write_landing_export are unit-tested in isolation
(tests/unit/test_silver_landing_export.py); this file covers the remaining
seam -- that _execute_warehouse_bronze_capture actually constructs, threads,
and flushes the buffer, and stays a byte-for-byte no-op when
context.silver_landing_export_root is None (the default for every command
today, since SILVER_LANDING_EXPORT_ROOT is unset everywhere in prod as of
this change).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _context(tmp_path, *, silver_landing_export_root: StorageLocation | None = None) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
        silver_landing_export_root=silver_landing_export_root,
    )


def test_landing_export_is_a_noop_when_context_has_no_landing_root(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import _execute_warehouse_bronze_capture

    context = _context(tmp_path)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {}

    with (
        patch("edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database", return_value=fake_db
        ) as open_db,
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._resolve_scope",
            return_value={"limit": 100, "offset": 0},
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            return_value=([], {"rows_inserted": 0, "rows_skipped": 0, "sync_status": "succeeded"}),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_with_retry",
            return_value={"layer": "silver_database", "path": "silver.duckdb"},
        ),
        patch("edgar_warehouse.serving.gold_models.iter_gold_tables", return_value=iter(())),
        patch("edgar_warehouse.application.warehouse_orchestrator.write_landing_export") as write_landing,
    ):
        result = _execute_warehouse_bronze_capture(
            context=context,
            command_name="bootstrap-next",
            arguments={"run_id": "no-landing-run", "silver_only": True},
        )

    open_db.assert_called_once()
    assert open_db.call_args.kwargs["landing_export"] is None
    write_landing.assert_not_called()
    assert result["silver_landing_export_row_counts"] is None
    assert result["environment"]["silver_landing_export_root"] is None


def test_landing_export_flushes_rows_written_during_the_run(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import _execute_warehouse_bronze_capture

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {"sec_company": 1}

    captured: dict[str, object] = {}

    def _fake_open_silver_database(silver_root, *, landing_export=None):
        captured["buffer"] = landing_export
        # Models the real merge_company()->@track_landing_rows path a live
        # SilverDatabase would exercise -- this test stubs the DB itself, so
        # the row is recorded directly to prove the buffer that was passed
        # in is the one actually flushed.
        if landing_export is not None:
            landing_export.record("sec_company", [{"cik": 320193, "entity_name": "Apple Inc"}])
        return fake_db

    with (
        patch("edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
            side_effect=_fake_open_silver_database,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._resolve_scope",
            return_value={"limit": 100, "offset": 0},
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            return_value=([], {"rows_inserted": 1, "rows_skipped": 0, "sync_status": "succeeded"}),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_with_retry",
            return_value={"layer": "silver_database", "path": "silver.duckdb"},
        ),
        patch("edgar_warehouse.serving.gold_models.iter_gold_tables", return_value=iter(())),
    ):
        result = _execute_warehouse_bronze_capture(
            context=context,
            command_name="bootstrap-next",
            arguments={"run_id": "landing-run", "silver_only": True},
        )

    assert captured["buffer"] is not None
    assert result["silver_landing_export_row_counts"] == {"sec_company": 1}
    assert result["environment"]["silver_landing_export_root"] == landing_root.root

    written_files = list((tmp_path / "silver-landing" / "sec_company").rglob("*.parquet"))
    assert len(written_files) == 1


def test_landing_export_not_flushed_on_pipeline_failure(tmp_path) -> None:
    """A failed run must not publish a partial landing export -- matches
    silver_database_write, which is likewise only produced on the success path."""
    from edgar_warehouse.application.warehouse_orchestrator import _execute_warehouse_bronze_capture

    context = _context(tmp_path, silver_landing_export_root=StorageLocation(str(tmp_path / "silver-landing")))
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {}

    with (
        patch("edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database", return_value=fake_db
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._resolve_scope",
            return_value={"limit": 100, "offset": 0},
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            side_effect=RuntimeError("boom"),
        ),
        patch("edgar_warehouse.application.warehouse_orchestrator.write_landing_export") as write_landing,
    ):
        try:
            _execute_warehouse_bronze_capture(
                context=context,
                command_name="bootstrap-next",
                arguments={"run_id": "failed-run", "silver_only": True},
            )
        except RuntimeError:
            pass

    write_landing.assert_not_called()
