from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase
from tests.unit._fake_snowflake import (
    EMPTY_ORPHAN_EVIDENCE_TABLE_DATA,
    FakeSnowflakeConnectionSettings,
)

# validate_data_quality() calls build_source_export(), which includes 5 builders that
# read Snowflake's EDGARTOOLS_SILVER directly instead of the local DuckDB
# fixture (dbt-gold-silver-rewiring map, Ticket 06) -- patch their connection
# so these tests don't attempt a real Snowflake connection.
_patch_silver_connection = patch(
    "edgar_warehouse.mdm.export.silver_connection_settings",
    return_value=FakeSnowflakeConnectionSettings(EMPTY_ORPHAN_EVIDENCE_TABLE_DATA),
)


def _patch_bookkeeping_store(bookkeeping):
    # DuckDB Retirement Cutover Ticket 15: pipeline_run now lives in the
    # bookkeeping store, not SilverDatabase.
    return patch(
        "edgar_warehouse.application.commands.validate_data_quality._bookkeeping_store",
        return_value=bookkeeping,
    )


def _context(tmp_path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
    )


def _db_path(context: WarehouseCommandContext) -> str:
    return context.silver_root.join("silver", "sec", "silver.duckdb")


def _insert_company_and_filing(
    db: SilverDatabase,
    *,
    cik: int = 320193,
    accession_number: str = "0000320193-24-000123",
) -> None:
    db._conn.execute(
        """
        INSERT INTO sec_company (cik, entity_name, last_sync_run_id)
        VALUES (?, ?, ?)
        """,
        [cik, "Apple Inc.", "run-1"],
    )
    db._conn.execute(
        """
        INSERT INTO sec_company_filing
            (accession_number, cik, form, filing_date, report_date, last_sync_run_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [accession_number, cik, "10-K", "2024-11-01", "2024-09-28", "run-1"],
    )


def test_validate_data_quality_flags_row_count_regressions(tmp_path) -> None:
    from edgar_warehouse.application.commands.validate_data_quality import (
        validate_data_quality,
    )
    from tests.support.bookkeeping_fixtures import bookkeeping_fixture

    context = _context(tmp_path)
    db = SilverDatabase(_db_path(context))
    try:
        _insert_company_and_filing(db)
    finally:
        db.close()

    bookkeeping = bookkeeping_fixture()
    bookkeeping.start_pipeline_run(
        {
            "pipeline_run_id": "previous-run",
            "command_name": "bootstrap",
            "runtime_mode": "bronze_capture",
            "environment_name": "test",
            "started_at": datetime(2026, 1, 1, tzinfo=UTC),
            "status": "running",
            "arguments": {},
            "scope": {},
            "bronze_root": context.bronze_root.root,
            "storage_root": context.storage_root.root,
            "silver_root": context.silver_root.root,
        }
    )
    bookkeeping.complete_pipeline_run(
        "previous-run",
        status="succeeded",
        writes=[],
        raw_writes=[],
        metrics={"silver_table_counts": {"sec_company": 2}},
    )

    with _patch_silver_connection, _patch_bookkeeping_store(bookkeeping):
        report = validate_data_quality(context=context)

    assert report["checks"]["row_count_monotonic"]["status"] == "failed"
    assert {
        "type": "row_count_regression",
        "table": "sec_company",
        "previous_count": 2,
        "current_count": 1,
        "previous_pipeline_run_id": "previous-run",
    } in report["findings"]


def test_validate_data_quality_flags_foreign_key_orphans(tmp_path) -> None:
    from edgar_warehouse.application.commands.validate_data_quality import (
        validate_data_quality,
    )

    context = _context(tmp_path)
    db = SilverDatabase(_db_path(context))
    try:
        db._conn.execute(
            """
            INSERT INTO sec_company_filing (accession_number, cik, form, filing_date)
            VALUES ('0000000000-24-000001', 9999999999, '10-K', '2024-01-01')
            """
        )
    finally:
        db.close()

    fake_bookkeeping = MagicMock()
    fake_bookkeeping.get_recent_successful_pipeline_runs.return_value = []
    with _patch_silver_connection, _patch_bookkeeping_store(fake_bookkeeping):
        report = validate_data_quality(context=context)

    assert report["status"] == "failed"
    assert {
        "type": "foreign_key_orphan",
        "table": "sec_company_filing",
        "column": "cik",
        "referenced_table": "sec_company",
        "referenced_column": "cik",
        "orphan_count": 1,
    } in report["findings"]


def test_validate_data_quality_compares_direct_gold_and_silver_counts(tmp_path) -> None:
    from edgar_warehouse.application.commands.validate_data_quality import (
        validate_data_quality,
    )

    context = _context(tmp_path)
    db = SilverDatabase(_db_path(context))
    try:
        _insert_company_and_filing(db)
        db._conn.execute(
            """
            INSERT INTO sec_financial_fact
                (cik, accession_number, fiscal_year, fiscal_period, period_end,
                 period_start, form_type, concept, value, unit, decimals, segment,
                 parser_version)
            VALUES (320193, '0000320193-24-000123', 2024, 'FY', '2024-09-28',
                    '2023-09-29', '10-K', 'us-gaap/Revenues', 391035000000,
                    'USD', 0, 'consolidated', 'test')
            """
        )
    finally:
        db.close()

    fake_bookkeeping = MagicMock()
    fake_bookkeeping.get_recent_successful_pipeline_runs.return_value = []
    with _patch_silver_connection, _patch_bookkeeping_store(fake_bookkeeping):
        report = validate_data_quality(context=context)

    comparison = report["checks"]["gold_vs_silver"]["tables"]["sec_financial_fact"]
    assert comparison == {
        "silver_table": "sec_financial_fact",
        "gold_table": "sec_financial_fact",
        "silver_rows": 1,
        "gold_rows": 1,
        "status": "ok",
    }


def test_validate_data_quality_reports_null_ratios(tmp_path) -> None:
    from edgar_warehouse.application.commands.validate_data_quality import (
        validate_data_quality,
    )

    context = _context(tmp_path)
    db = SilverDatabase(_db_path(context))
    try:
        db._conn.execute(
            """
            INSERT INTO sec_company (cik, entity_name, entity_type, last_sync_run_id)
            VALUES (320193, 'Apple Inc.', NULL, 'run-1')
            """
        )
    finally:
        db.close()

    fake_bookkeeping = MagicMock()
    fake_bookkeeping.get_recent_successful_pipeline_runs.return_value = []
    with _patch_silver_connection, _patch_bookkeeping_store(fake_bookkeeping):
        report = validate_data_quality(context=context)

    entity_type_ratio = report["checks"]["null_ratios"]["tables"]["sec_company"]["columns"][
        "entity_type"
    ]
    assert entity_type_ratio == {"nulls": 1, "rows": 1, "ratio": 1.0}
    json.dumps(report)
