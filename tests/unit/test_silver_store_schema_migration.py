"""Tests for the sec_financial_fact / sec_financial_derived period_end PK migration.

PR #57 added `period_end` to the primary key of `sec_financial_fact` and
`sec_financial_derived`. `CREATE TABLE IF NOT EXISTS` does not alter an
existing table's constraints, so a `silver.duckdb` created before that PR
retains the old PK and `merge_financial_facts`/`merge_financial_derived`'s
`ON CONFLICT (..., period_end)` clauses raise a binder error. These tests
build an old-PK store, open it via `SilverDatabase`, and confirm the
migration in `_ensure_schema_evolution`/`_migrate_financial_period_end_pk`
repairs it before any merge is attempted.
"""

from __future__ import annotations

import logging

import duckdb
import pytest

from edgar_warehouse.silver_store import SilverDatabase

# Pre-PR-#57 DDL (PK omits period_end) for sec_financial_fact / sec_financial_derived.
_OLD_FINANCIAL_FACT_DDL = """
CREATE TABLE sec_financial_fact (
    cik                 BIGINT NOT NULL,
    accession_number    TEXT NOT NULL,
    fiscal_year         INTEGER NOT NULL,
    fiscal_period       TEXT NOT NULL,
    period_end          DATE NOT NULL,
    form_type           TEXT NOT NULL,
    concept             TEXT NOT NULL,
    value               DOUBLE,
    unit                TEXT,
    decimals            INTEGER,
    segment             TEXT NOT NULL DEFAULT 'consolidated',
    parser_version      TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cik, accession_number, concept, fiscal_period, segment)
);
"""

_OLD_FINANCIAL_DERIVED_DDL = """
CREATE TABLE sec_financial_derived (
    cik                 BIGINT NOT NULL,
    accession_number    TEXT NOT NULL,
    fiscal_year         INTEGER NOT NULL,
    fiscal_period       TEXT NOT NULL,
    period_end          DATE NOT NULL,
    form_type           TEXT NOT NULL,
    revenue             DOUBLE,
    gross_profit        DOUBLE,
    ebitda              DOUBLE,
    ebit                DOUBLE,
    net_income          DOUBLE,
    eps_diluted         DOUBLE,
    total_assets        DOUBLE,
    total_liabilities   DOUBLE,
    total_equity        DOUBLE,
    cash_and_equivalents DOUBLE,
    total_debt          DOUBLE,
    operating_cash_flow DOUBLE,
    capex               DOUBLE,
    free_cash_flow      DOUBLE,
    gross_margin        DOUBLE,
    ebitda_margin       DOUBLE,
    net_margin          DOUBLE,
    roic                DOUBLE,
    roe                 DOUBLE,
    roa                 DOUBLE,
    parser_version      TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (cik, accession_number, fiscal_period)
);
"""


def _pk_columns(conn: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    row = conn.execute(
        """
        SELECT constraint_column_names
        FROM duckdb_constraints()
        WHERE table_name = ? AND constraint_type = 'PRIMARY KEY'
        """,
        [table],
    ).fetchone()
    assert row is not None, f"{table} has no PRIMARY KEY constraint"
    return list(row[0])


def _build_old_pk_store(db_path: str) -> None:
    conn = duckdb.connect(db_path)
    try:
        conn.execute(_OLD_FINANCIAL_FACT_DDL)
        conn.execute(_OLD_FINANCIAL_DERIVED_DDL)
        # A "Frankenstein" row: same old-PK columns, but this is the kind of
        # row that would collide under the old PK once a comparative-period
        # row for the same (cik, accession, concept, fiscal_period, segment)
        # arrives with a different period_end.
        conn.execute(
            """
            INSERT INTO sec_financial_fact
                (cik, accession_number, fiscal_year, fiscal_period, period_end,
                 form_type, concept, value, unit, decimals, segment, parser_version)
            VALUES (320193, '0000320193-24-000123', 2024, 'Q4', '2024-09-28',
                    '10-K', 'us-gaap/Revenues', 391035000000, 'USD', 0,
                    'consolidated', 'old-pk-test')
            """
        )
        conn.execute(
            """
            INSERT INTO sec_financial_derived
                (cik, accession_number, fiscal_year, fiscal_period, period_end,
                 form_type, revenue, parser_version)
            VALUES (320193, '0000320193-24-000123', 2024, 'Q4', '2024-09-28',
                    '10-K', 391035000000, 'old-pk-test')
            """
        )
    finally:
        conn.close()


def test_migration_adds_period_end_to_pk_and_drops_old_rows(tmp_path, caplog):
    db_path = str(tmp_path / "silver.duckdb")
    _build_old_pk_store(db_path)

    with caplog.at_level(logging.WARNING, logger="edgar_warehouse.silver_store"):
        db = SilverDatabase(db_path)
    try:
        fact_pk = _pk_columns(db._conn, "sec_financial_fact")
        derived_pk = _pk_columns(db._conn, "sec_financial_derived")
        assert "period_end" in fact_pk
        assert "period_end" in derived_pk

        # Old rows are discarded as part of the drop+recreate.
        assert db.fetch("SELECT COUNT(*) AS n FROM sec_financial_fact")[0]["n"] == 0
        assert db.fetch("SELECT COUNT(*) AS n FROM sec_financial_derived")[0]["n"] == 0
    finally:
        db.close()

    assert "sec_financial_fact" in caplog.text
    assert "sec_financial_derived" in caplog.text


def test_merge_financial_facts_succeeds_after_migration(tmp_path):
    """The exact failure mode from the codex P1 finding: two rows sharing the
    old-PK columns but with different period_end (current vs. comparative
    prior period) must upsert cleanly, not raise a binder error.
    """
    db_path = str(tmp_path / "silver.duckdb")
    _build_old_pk_store(db_path)

    db = SilverDatabase(db_path)
    try:
        rows = [
            {
                "cik": 320193,
                "accession_number": "0000320193-25-000050",
                "fiscal_year": 2025,
                "fiscal_period": "Q3",
                "period_end": "2025-06-28",
                "form_type": "10-Q",
                "concept": "us-gaap/Revenues",
                "value": 100_000_000,
                "unit": "USD",
                "decimals": 0,
                "segment": "consolidated",
                "parser_version": "test",
            },
            {
                "cik": 320193,
                "accession_number": "0000320193-25-000050",
                "fiscal_year": 2024,
                "fiscal_period": "Q3",
                "period_end": "2024-06-29",
                "form_type": "10-Q",
                "concept": "us-gaap/Revenues",
                "value": 95_000_000,
                "unit": "USD",
                "decimals": 0,
                "segment": "consolidated",
                "parser_version": "test",
            },
        ]

        count = db.merge_financial_facts(rows, sync_run_id="test-sync")
        assert count == 2

        stored = db.fetch(
            "SELECT period_end, value FROM sec_financial_fact ORDER BY period_end"
        )
        assert len(stored) == 2
    finally:
        db.close()


def test_migration_is_noop_for_fresh_store(tmp_path, caplog):
    """A store created directly via SilverDatabase already has the new PK;
    reopening it must not log a migration warning or touch the tables.
    """
    db_path = str(tmp_path / "silver.duckdb")

    db = SilverDatabase(db_path)
    db.close()

    with caplog.at_level(logging.WARNING, logger="edgar_warehouse.silver_store"):
        db = SilverDatabase(db_path)
    try:
        assert "period_end" in _pk_columns(db._conn, "sec_financial_fact")
        assert "period_end" in _pk_columns(db._conn, "sec_financial_derived")
    finally:
        db.close()

    assert "sec_financial_fact" not in caplog.text
    assert "sec_financial_derived" not in caplog.text
