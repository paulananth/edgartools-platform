"""silver-merge-engine-migration Ticket 10: `targeted-resync --scope-type
accession` reads the filing from EDGARTOOLS_SILVER.

DuckDB Retirement Cutover Ticket 10 stopped hydrating local DuckDB, and
Ticket 06d made `get_filing` answer only from rows recorded earlier in the
same run. An accession-scoped run records none before `_run_accession_resync`
asks for the filing, so it always raised "Unknown accession_number". The
accession branch now reads every (accession, cik) row from Snowflake silver
and records them first; the cik branch still gets its filings from its own
same-run submissions capture.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.silver_store import SilverDatabase
from tests.unit.test_targeted_resync_accession_conflict_isolation import (
    _context,
    _submissions_result,
)

ACCESSION = "0000320193-26-000073"


def _snowflake_row(cik: int) -> dict:
    return {
        "accession_number": ACCESSION,
        "cik": cik,
        "form": "4",
        "filing_date": date(2026, 9, 1),
        "report_date": None,
        "acceptance_datetime": "2026-09-01T16:30:00.000Z",
        "act": "34",
        "file_number": None,
        "film_number": None,
        "items": None,
        "size": 4321,
        "is_xbrl": False,
        "is_inline_xbrl": False,
        "primary_document": "xslF345X05/wk-form4.xml",
        "primary_doc_desc": "FORM 4",
        "last_sync_run_id": "earlier-run",
        "last_synced_at": datetime(2026, 9, 1, 21, tzinfo=UTC),
    }


def _run_accession_scope(tmp_path: Path, db: SilverDatabase, scope_key: str = ACCESSION):
    return warehouse_orchestrator._capture_bronze_raw(
        context=_context(tmp_path),
        db=db,
        bookkeeping=object(),
        command_name="targeted-resync",
        arguments={
            "scope_type": "accession",
            "scope_key": scope_key,
            "include_artifacts": False,
            "include_text": False,
            "include_parsers": False,
        },
        scope={"scope_type": "accession", "scope_key": scope_key},
        now=datetime(2026, 9, 14, 12, tzinfo=UTC),
        sync_run_id="resync-run",
    )


def test_accession_scope_resyncs_a_filing_recorded_by_an_earlier_run(tmp_path) -> None:
    landing = LandingExportBuffer()
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=landing)
    rows = [_snowflake_row(320193), _snowflake_row(1214156)]

    with patch.object(warehouse_orchestrator, "_filing_rows_snowflake", return_value=rows) as read:
        _raw_writes, metrics = _run_accession_scope(tmp_path, db)

    read.assert_called_once_with(ACCESSION)
    filing = db.get_filing(ACCESSION)
    assert filing is not None
    assert filing["cik"] == 320193
    landed = landing.tables()["sec_company_filing"]
    # Both CIK rows, then _run_accession_resync's own re-record of the first
    # (dbt collapses the copies); every row carries this run's sync stamp.
    assert [row["cik"] for row in landed] == [320193, 1214156, 320193]
    assert {row["last_sync_run_id"] for row in landed} == {"resync-run"}
    assert metrics["rows_inserted"] == 3


def test_accession_scope_fails_closed_when_silver_has_no_row(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=LandingExportBuffer())

    with (
        patch.object(warehouse_orchestrator, "_filing_rows_snowflake", return_value=[]),
        pytest.raises(WarehouseRuntimeError, match="EDGARTOOLS_SILVER") as excinfo,
    ):
        _run_accession_scope(tmp_path, db)

    assert "--scope-type cik" in str(excinfo.value)


def test_cik_scope_does_not_read_snowflake_silver(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=LandingExportBuffer())

    with (
        patch.object(
            warehouse_orchestrator, "submissions_orchestrator", return_value=_submissions_result([])
        ),
        patch.object(
            warehouse_orchestrator,
            "_filing_rows_snowflake",
            side_effect=AssertionError("cik scope must not read Snowflake silver"),
        ),
    ):
        warehouse_orchestrator._capture_bronze_raw(
            context=_context(tmp_path),
            db=db,
            bookkeeping=object(),
            command_name="targeted-resync",
            arguments={"scope_type": "cik", "scope_key": "320193", "include_artifacts": True},
            scope={"scope_type": "cik", "scope_key": "320193"},
            now=datetime(2026, 9, 14, 12, tzinfo=UTC),
            sync_run_id="resync-run",
        )


def test_accession_scope_refuses_parsers_without_artifacts(tmp_path) -> None:
    """The parsers read this run's attachment rows, which only the artifact
    step records. Without it every parse run would be marked failed while
    the command still succeeded, so the combination fails closed before any
    Snowflake read."""
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=LandingExportBuffer())

    with (
        patch.object(
            warehouse_orchestrator,
            "_filing_rows_snowflake",
            side_effect=AssertionError("must fail before reading Snowflake"),
        ),
        pytest.raises(WarehouseRuntimeError, match="--no-include-artifacts"),
    ):
        warehouse_orchestrator._capture_bronze_raw(
            context=_context(tmp_path),
            db=db,
            bookkeeping=object(),
            command_name="targeted-resync",
            arguments={
                "scope_type": "accession",
                "scope_key": ACCESSION,
                "include_artifacts": False,
                "include_text": False,
                "include_parsers": True,
            },
            scope={"scope_type": "accession", "scope_key": ACCESSION},
            now=datetime(2026, 9, 14, 12, tzinfo=UTC),
            sync_run_id="resync-run",
        )


class _FakeReader:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, list]] = []
        self.closed = False

    def fetch(self, sql: str, params: list | None = None) -> list[dict]:
        self.calls.append((sql, list(params or [])))
        return self.rows

    def close(self) -> None:
        self.closed = True


def test_filing_columns_match_the_silver_ddl(tmp_path) -> None:
    """Pinned to the real table, not a hand-copied list, so the constant
    cannot drift from silver_store._DDL unnoticed."""
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))

    assert warehouse_orchestrator._SNOWFLAKE_FILING_COLUMNS == tuple(
        db._table_columns("sec_company_filing")
    )


def test_filing_rows_snowflake_selects_named_columns_for_the_accession() -> None:
    from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader

    row = _snowflake_row(320193)
    reader = _FakeReader([row])
    with patch.object(SnowflakeSilverReader, "connect", return_value=reader):
        result = warehouse_orchestrator._filing_rows_snowflake(ACCESSION)

    assert result == [row]
    assert reader.closed
    sql, params = reader.calls[0]
    assert params == [ACCESSION]
    select_list = sql.split("SELECT", 1)[1].split("FROM", 1)[0]
    assert tuple(c.strip() for c in select_list.split(",")) == (
        warehouse_orchestrator._SNOWFLAKE_FILING_COLUMNS
    )
    assert "WHERE accession_number = ?" in sql
