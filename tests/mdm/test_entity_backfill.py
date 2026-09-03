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
import re
import uuid
from typing import Optional
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
    """Mimics snowflake-connector-python's cursor shape: .execute(sql, params)
    then .description (list of (name, ...) tuples) and .fetchall() (list of
    tuples), keyed by which table the query names.

    Genuinely simulates the keyset-pagination SQL shape
    _fetch_pending_rows_batches issues (large-profile-unscoped-load-audit
    Ticket 02): parses the ORDER BY column list and LIMIT out of the SQL
    text, applies the keyset filter (row-value tuple > params) when params
    are supplied, sorts by the key columns, and truncates to LIMIT -- the
    same technique the INSTITUTIONAL_HOLDS StubSilver uses for its own
    CIK-BETWEEN batching, adapted to keyset comparison instead of a range."""

    def __init__(
        self,
        rows_by_table: dict[str, tuple[list[str], list[tuple]]],
        execute_calls: list[tuple[str, str, list]],
    ) -> None:
        self._rows_by_table = rows_by_table
        self._execute_calls = execute_calls
        self.description: list[tuple] = []
        self._pending_rows: list[tuple] = []

    def execute(self, sql: str, params: Optional[list] = None) -> None:
        params = params or []
        table = sql.split("FROM", 1)[1].split("WHERE", 1)[0].strip()
        self._execute_calls.append((table, sql, list(params)))
        columns, rows = self._rows_by_table.get(table, ([], []))
        self.description = [(c,) for c in columns]

        order_match = re.search(r"ORDER BY (.+?) LIMIT", sql, re.IGNORECASE)
        limit_match = re.search(r"LIMIT (\d+)", sql, re.IGNORECASE)
        key_cols = [c.strip() for c in order_match.group(1).split(",")] if order_match else []
        limit = int(limit_match.group(1)) if limit_match else None
        col_index = {c.upper(): i for i, c in enumerate(columns)}
        key_indices = [col_index[c.upper()] for c in key_cols if c.upper() in col_index]

        filtered = list(rows)
        if params and key_indices:
            keyset = tuple(params)
            filtered = [r for r in filtered if tuple(r[i] for i in key_indices) > keyset]
        if key_indices:
            filtered.sort(key=lambda r: tuple(r[i] for i in key_indices))
        if limit is not None:
            filtered = filtered[:limit]
        self._pending_rows = filtered

    def fetchall(self) -> list[tuple]:
        return self._pending_rows

    def close(self) -> None:
        pass


class _FakeConnection:
    def __init__(self, rows_by_table: dict[str, tuple[list[str], list[tuple]]]) -> None:
        self._rows_by_table = rows_by_table
        # (table, sql, params) for every cursor.execute() call across every
        # cursor this connection has issued -- a fresh _FakeCursor is
        # created per page, mirroring _fetch_pending_rows_batches' real
        # per-page `connection.cursor()` call, so call tracking lives here.
        self.execute_calls: list[tuple[str, str, list]] = []

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows_by_table, self.execute_calls)

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
    # connect_with_qmark_paramstyle imports the real snowflake.connector
    # module to scope its global (see the module's own docstring); this
    # test's row-processing assertions don't need that real package, and
    # CI's "MDM tests" job installs the `mdm` extra, not `snowflake` -- so
    # bypass the dance entirely and go straight to the fake settings'
    # .connect(). test_sweep_connects_with_qmark_paramstyle (below) is the
    # one test that exercises the real dance, gated on
    # pytest.importorskip("snowflake.connector").
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
         patch(
             "edgar_warehouse.silver_support.snowflake_reader.connect_with_qmark_paramstyle",
             side_effect=lambda settings_factory: settings_factory().connect(),
         ), \
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


def test_sweep_connects_with_qmark_paramstyle(tmp_path) -> None:
    """bronze-capture-oom-adjacent live prod crash, 2026-09-02:
    _fetch_pending_rows_batches builds `?`-style SQL, but
    snowflake-connector-python defaults to pyformat and only honors qmark
    when the module-global paramstyle is set to "qmark" at connect() time
    (see connect_with_qmark_paramstyle's own docstring) -- confirmed live
    via TypeError: not all arguments converted during string formatting.
    The prior end-to-end test mocks _silver_connection_settings with a
    plain MagicMock, which never exercises this timing at all; this test
    uses a settings double that records the ambient paramstyle at the
    moment .connect() is called, the same technique
    test_connect_with_qmark_paramstyle.py uses for the shared helper
    itself."""
    sc = pytest.importorskip("snowflake.connector")

    mdm_db_path = tmp_path / "mdm.sqlite"
    engine = create_engine(f"sqlite:///{mdm_db_path}")
    Base.metadata.create_all(engine)
    engine.dispose()

    fake_connection = _FakeConnection({"SEC_COMPANY": (["CIK", "ENTITY_NAME", "MDM_ENTITY_ID"], [])})
    from tests.unit._fake_snowflake import RecordingConnectSettings

    recording_settings = RecordingConnectSettings(fake_connection)

    context = _local_context(tmp_path)

    with patch.dict(os.environ, {"MDM_DATABASE_URL": f"sqlite:///{mdm_db_path}"}), \
         patch("edgar_warehouse.mdm_entity_backfill._silver_connection_settings", return_value=recording_settings), \
         patch("edgar_warehouse.serving.silver_landing_writer.write_landing_export") as mock_write, \
         patch("edgar_warehouse.application.warehouse_orchestrator._emit_pipeline_event"):
        mock_write.return_value = {}
        from edgar_warehouse.mdm_entity_backfill import run_mdm_entity_backfill_sweep

        run_mdm_entity_backfill_sweep(context, "test-run")

    assert recording_settings.paramstyle_during_connect == "qmark"


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
         patch(
             "edgar_warehouse.silver_support.snowflake_reader.connect_with_qmark_paramstyle",
             side_effect=lambda settings_factory: settings_factory().connect(),
         ), \
         patch("edgar_warehouse.serving.silver_landing_writer.write_landing_export", return_value={}), \
         patch("edgar_warehouse.application.warehouse_orchestrator._emit_pipeline_event"):
        from edgar_warehouse.mdm_entity_backfill import run_mdm_entity_backfill_sweep

        result = run_mdm_entity_backfill_sweep(context, "test-run")

    assert result["totals"]["sec_company"] == 0
    assert result["remaining_null_count"] == 1
    assert result["remaining_by_table"]["sec_company"] == 1


# ---------------------------------------------------------------------------
# large-profile-unscoped-load-audit Ticket 02: _fetch_pending_rows used to
# issue one unbounded `SELECT * FROM {table} WHERE mdm_entity_id IS NULL`
# per table with no LIMIT -- the MANAGES_FUND OOM shape. Live-measured
# 2026-08-22: sec_adv_private_fund alone is 1,579,876 rows total (larger
# than MANAGES_FUND's own 563,631-row OOM trigger), currently 0 pending --
# the same "safe until it isn't" shape INSTITUTIONAL_HOLDS's pre-emptive
# fix addressed. Fix: keyset-paginated reads via _fetch_pending_rows_batches.
# ---------------------------------------------------------------------------

def test_backfill_pending_rows_pages_sec_company_in_bounded_chunks(monkeypatch, db_session) -> None:
    """5 pending sec_company rows, chunk size forced to 2 -> 3 bounded
    execute() calls (2, 2, 1), each carrying a LIMIT, not one unbounded
    fetch of all 5. Every row must still be seen exactly once (no gaps,
    no duplicates) and the resolved/pending totals must match what a
    single unbounded pass would have produced."""
    import edgar_warehouse.mdm_entity_backfill as backfill_module

    monkeypatch.setattr(backfill_module, "_ROW_CHUNK_SIZE", 2)

    ciks = [500, 100, 400, 200, 300]  # deliberately unsorted
    resolvable_ciks = {100, 200, 300}
    for cik in resolvable_ciks:
        _register(db_session, entity_type="company", source_system="edgar_cik", source_id=str(cik))

    rows_by_table = {
        "SEC_COMPANY": (
            ["CIK", "ENTITY_NAME", "MDM_ENTITY_ID"],
            [(cik, f"Company {cik}", None) for cik in ciks],
        ),
    }
    connection = _FakeConnection(rows_by_table)
    landing_export = LandingExportBuffer()

    counts = backfill_pending_rows(connection, db_session, landing_export)

    assert counts["sec_company"] == {"pending": 5, "resolved": 3}

    sec_company_calls = [c for c in connection.execute_calls if c[0] == "SEC_COMPANY"]
    # 5 rows at chunk size 2 -> 3 calls (2 + 2 + 1), not 1 unbounded call.
    assert len(sec_company_calls) == 3, sec_company_calls
    for _table, sql, _params in sec_company_calls:
        assert "LIMIT 2" in sql, sql

    recorded_ciks = {row["cik"] for row in landing_export.tables()["sec_company"]}
    assert recorded_ciks == resolvable_ciks


def test_backfill_pending_rows_batch_size_does_not_change_resolved_output(monkeypatch, db_session) -> None:
    """Batch equivalence: chunked reads (size 1) must resolve the exact
    same rows as one unbounded-equivalent pass (a chunk size larger than
    the whole fixture) -- chunking is a memory-shape change only, not a
    correctness change."""
    import edgar_warehouse.mdm_entity_backfill as backfill_module

    ciks = [100, 200, 300, 400]
    for cik in (100, 300):
        _register(db_session, entity_type="company", source_system="edgar_cik", source_id=str(cik))

    def _run(chunk_size: int) -> dict:
        monkeypatch.setattr(backfill_module, "_ROW_CHUNK_SIZE", chunk_size)
        rows_by_table = {
            "SEC_COMPANY": (
                ["CIK", "ENTITY_NAME", "MDM_ENTITY_ID"],
                [(cik, f"Company {cik}", None) for cik in ciks],
            ),
        }
        connection = _FakeConnection(rows_by_table)
        landing_export = LandingExportBuffer()
        counts = backfill_pending_rows(connection, db_session, landing_export)
        return counts, {row["cik"] for row in landing_export.tables()["sec_company"]}

    single_pass_counts, single_pass_ciks = _run(chunk_size=1_000)
    chunked_counts, chunked_ciks = _run(chunk_size=1)

    assert single_pass_counts == chunked_counts
    assert single_pass_counts["sec_company"] == {"pending": 4, "resolved": 2}
    assert single_pass_ciks == chunked_ciks == {100, 300}
