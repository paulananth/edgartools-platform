"""Tests for the mdm-ahead-of-silver map's Phase B backfill sweep
(edgar_warehouse/mdm_entity_backfill.py).

Ticket 06 (.scratch/mdm-ahead-of-silver/issues/06-narrow-backfill-storage-target.md)
rewrote the sweep to be Snowflake-only, full-row re-emission -- no DuckDB is
read or written. These tests mock the Snowflake connection (a plain cursor
with .description/.fetchall(), matching snowflake-connector-python's shape)
and exercise backfill_pending_rows/run_mdm_entity_backfill_sweep against a
real MDM Postgres session (sqlite-backed, same pattern the rest of this test
suite uses) so the MdmSourceRef lookup is exercised for real, not mocked.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.mdm.database import Base, MdmEntity, MdmSourceRef
from edgar_warehouse.mdm_entity_backfill import (
    MDM_ENTITY_ID_TABLES,
    backfill_pending_rows,
)
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer


def _register(session: Session, *, entity_type: str, source_system: str, source_id: str) -> str:
    entity_id = str(uuid.uuid4())
    session.add(MdmEntity(entity_id=entity_id, entity_type=entity_type, resolution_method="test"))
    session.add(
        MdmSourceRef(
            entity_id=entity_id,
            source_system=source_system,
            source_id=source_id,
            source_priority=1,
        )
    )
    return entity_id


class _FakeCursor:
    """Mimics snowflake-connector-python's cursor shape: .execute(sql) then
    .description (list of (name, ...) tuples) and .fetchall() (list of
    tuples), keyed by which table the query names."""

    def __init__(self, rows_by_table: dict[str, tuple[list[str], list[tuple]]]) -> None:
        self._rows_by_table = rows_by_table
        self.description: list[tuple] = []
        self._pending_rows: list[tuple] = []

    def execute(self, sql: str) -> None:
        table = sql.split("FROM", 1)[1].split("WHERE", 1)[0].strip()
        columns, rows = self._rows_by_table.get(table, ([], []))
        self.description = [(c,) for c in columns]
        self._pending_rows = rows

    def fetchall(self) -> list[tuple]:
        return self._pending_rows

    def close(self) -> None:
        pass


class _FakeConnection:
    def __init__(self, rows_by_table: dict[str, tuple[list[str], list[tuple]]]) -> None:
        self._rows_by_table = rows_by_table

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows_by_table)

    def close(self) -> None:
        pass


def test_backfill_pending_rows_resolves_matched_and_leaves_unmatched_out(db_session) -> None:
    company_entity = _register(db_session, entity_type="company", source_system="edgar_cik", source_id="320193")

    rows_by_table = {
        "SEC_COMPANY": (
            ["CIK", "ENTITY_NAME", "MDM_ENTITY_ID"],
            [
                (320193, "Apple Inc", None),  # resolvable
                (999999, "Unresolved Co", None),  # no matching MdmSourceRef
            ],
        ),
    }
    connection = _FakeConnection(rows_by_table)
    landing_export = LandingExportBuffer()

    counts = backfill_pending_rows(connection, db_session, landing_export)

    assert counts["sec_company"] == {"pending": 2, "resolved": 1}
    for table in MDM_ENTITY_ID_TABLES:
        if table != "sec_company":
            assert counts[table] == {"pending": 0, "resolved": 0}

    recorded = landing_export.tables()["sec_company"]
    assert len(recorded) == 1
    assert recorded[0]["cik"] == 320193
    assert recorded[0]["entity_name"] == "Apple Inc"
    assert recorded[0]["mdm_entity_id"] == company_entity


def test_backfill_pending_rows_full_row_carries_every_source_column(db_session) -> None:
    """Full-row re-emission (ticket 06): every column from the pending row
    is carried into the recorded row, not just the key + mdm_entity_id --
    the whole point of the design chosen after the thin-append shape was
    found unsafe (.scratch/silver-landing-coalesce-bug/issues/01-...)."""
    entity_id = _register(db_session, entity_type="adviser", source_system="adv_filing", source_id="0001234567-25-000001")

    rows_by_table = {
        "SEC_ADV_FILING": (
            ["ACCESSION_NUMBER", "CIK", "FILING_DATE", "MDM_ENTITY_ID"],
            [("0001234567-25-000001", None, "2025-01-15", None)],
        ),
    }
    connection = _FakeConnection(rows_by_table)
    landing_export = LandingExportBuffer()

    backfill_pending_rows(connection, db_session, landing_export)

    recorded = landing_export.tables()["sec_adv_filing"][0]
    assert recorded["accession_number"] == "0001234567-25-000001"
    assert recorded["filing_date"] == "2025-01-15"
    assert recorded["mdm_entity_id"] == entity_id


def _local_context(tmp_path, *, silver_landing_export_root: bool = True) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        silver_landing_export_root=(
            StorageLocation(str(tmp_path / "silver_landing_export")) if silver_landing_export_root else None
        ),
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
    )


def test_sweep_requires_mdm_database_url(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import WarehouseRuntimeError
    from edgar_warehouse.mdm_entity_backfill import run_mdm_entity_backfill_sweep

    context = _local_context(tmp_path)
    env = dict(os.environ)
    env.pop("MDM_DATABASE_URL", None)
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(WarehouseRuntimeError, match="MDM_DATABASE_URL"):
            run_mdm_entity_backfill_sweep(context, "test-run")


def test_sweep_requires_silver_landing_export_root(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import WarehouseRuntimeError
    from edgar_warehouse.mdm_entity_backfill import run_mdm_entity_backfill_sweep

    context = _local_context(tmp_path, silver_landing_export_root=False)
    with patch.dict(os.environ, {"MDM_DATABASE_URL": "sqlite:///:memory:"}):
        with pytest.raises(WarehouseRuntimeError, match="SILVER_LANDING_EXPORT_ROOT"):
            run_mdm_entity_backfill_sweep(context, "test-run")


def test_sweep_end_to_end_writes_full_row_and_emits_completed_event(tmp_path) -> None:
    mdm_db_path = tmp_path / "mdm.sqlite"
    engine = create_engine(f"sqlite:///{mdm_db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as seed_session:
        company_entity = _register(seed_session, entity_type="company", source_system="edgar_cik", source_id="320193")
        seed_session.commit()
    engine.dispose()

    rows_by_table = {
        "SEC_COMPANY": (
            ["CIK", "ENTITY_NAME", "MDM_ENTITY_ID"],
            [(320193, "Apple Inc", None)],
        ),
    }
    fake_connection = _FakeConnection(rows_by_table)
    fake_settings = MagicMock()
    fake_settings.connect.return_value = fake_connection

    context = _local_context(tmp_path)

    with patch.dict(os.environ, {"MDM_DATABASE_URL": f"sqlite:///{mdm_db_path}"}), \
         patch("edgar_warehouse.mdm_entity_backfill._silver_connection_settings", return_value=fake_settings), \
         patch("edgar_warehouse.serving.silver_landing_writer.write_landing_export") as mock_write, \
         patch("edgar_warehouse.application.warehouse_orchestrator._emit_pipeline_event") as mock_emit:
        mock_write.return_value = {"sec_company": 1}
        from edgar_warehouse.mdm_entity_backfill import run_mdm_entity_backfill_sweep

        result = run_mdm_entity_backfill_sweep(context, "test-run")

    assert result["totals"]["sec_company"] == 1
    assert result["pending"]["sec_company"] == 1
    assert result["remaining_null_count"] == 0
    assert result["remaining_by_table"]["sec_company"] == 0
    assert result["landing_export"] == {"sec_company": 1}

    mock_write.assert_called_once()
    buffer_arg = mock_write.call_args.args[0]
    recorded = buffer_arg.tables()["sec_company"]
    assert recorded[0]["cik"] == 320193
    assert recorded[0]["mdm_entity_id"] == company_entity
    call_kwargs = mock_write.call_args.kwargs
    assert call_kwargs["run_id"] == "test-run"
    assert call_kwargs["command_name"] == "backfill-mdm-entity-ids"
    assert call_kwargs["environment_name"] == "test"

    mock_emit.assert_called_once()
    assert mock_emit.call_args.args[0] == "mdm_entity_backfill_completed"
    assert mock_emit.call_args.kwargs["run_id"] == "test-run"
    assert mock_emit.call_args.kwargs["remaining_null_count"] == 0
    assert mock_emit.call_args.kwargs["totals"]["sec_company"] == 1


def test_sweep_reports_remaining_null_count_for_unresolved_rows(tmp_path) -> None:
    """mdm-ahead-of-silver ticket 05's stuck-NULL alarm watches
    remaining_null_count -- rows with no matching MdmSourceRef yet must be
    left out of the landing-zone write and counted as remaining."""
    mdm_db_path = tmp_path / "mdm.sqlite"
    engine = create_engine(f"sqlite:///{mdm_db_path}")
    Base.metadata.create_all(engine)
    engine.dispose()  # No entities registered -- nothing will resolve.

    rows_by_table = {
        "SEC_COMPANY": (
            ["CIK", "ENTITY_NAME", "MDM_ENTITY_ID"],
            [(999999, "Unresolved Co", None)],
        ),
    }
    fake_connection = _FakeConnection(rows_by_table)
    fake_settings = MagicMock()
    fake_settings.connect.return_value = fake_connection

    context = _local_context(tmp_path)

    with patch.dict(os.environ, {"MDM_DATABASE_URL": f"sqlite:///{mdm_db_path}"}), \
         patch("edgar_warehouse.mdm_entity_backfill._silver_connection_settings", return_value=fake_settings), \
         patch("edgar_warehouse.serving.silver_landing_writer.write_landing_export", return_value={}), \
         patch("edgar_warehouse.application.warehouse_orchestrator._emit_pipeline_event"):
        from edgar_warehouse.mdm_entity_backfill import run_mdm_entity_backfill_sweep

        result = run_mdm_entity_backfill_sweep(context, "test-run")

    assert result["totals"]["sec_company"] == 0
    assert result["remaining_null_count"] == 1
    assert result["remaining_by_table"]["sec_company"] == 1
