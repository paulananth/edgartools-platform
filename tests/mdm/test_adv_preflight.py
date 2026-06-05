"""Fixture-based MDM adviser/fund preflight fail->pass tests.

Proves the _require_silver_reader gate transitions from FAIL (empty sec_adv_filing /
sec_adv_private_fund) to PASS (populated table) for adviser and fund entity types.

MDM-ADV-02 automated proof — no network, no S3, no live Postgres required.
"""

from __future__ import annotations

import duckdb
import pytest

import edgar_warehouse.mdm.cli as mdm_cli


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_adv_fixture_db(path: str) -> None:
    """Create a minimal DuckDB at *path* with ADV silver tables (empty)."""
    con = duckdb.connect(path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sec_adv_filing (
            accession_number    TEXT PRIMARY KEY,
            cik                 BIGINT,
            form                TEXT,
            adviser_name        TEXT,
            sec_file_number     TEXT,
            crd_number          TEXT,
            effective_date      DATE,
            filing_status       TEXT,
            source_format       TEXT,
            parser_version      TEXT,
            last_sync_run_id    TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sec_adv_private_fund (
            accession_number    TEXT,
            fund_index          SMALLINT,
            fund_name           TEXT,
            fund_type           TEXT,
            jurisdiction        TEXT,
            aum_amount          DECIMAL(28,2),
            parser_version      TEXT,
            last_sync_run_id    TEXT,
            PRIMARY KEY (accession_number, fund_index)
        )
    """)
    con.close()


# ---------------------------------------------------------------------------
# Adviser preflight tests
# ---------------------------------------------------------------------------


class TestAdviserPreflight:
    """sec_adv_filing must be nonempty before mdm run --entity-type adviser passes."""

    def test_adviser_fail_on_empty_sec_adv_filing(self, tmp_path, monkeypatch):
        """Empty sec_adv_filing → _require_silver_reader returns rc=1."""
        db_path = str(tmp_path / "silver.duckdb")
        _make_adv_fixture_db(db_path)

        monkeypatch.setenv("MDM_SILVER_DUCKDB", db_path)
        monkeypatch.delenv("WAREHOUSE_STORAGE_ROOT", raising=False)
        monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

        required = mdm_cli._required_tables_for_run("adviser")
        reader, rc = mdm_cli._require_silver_reader(required, "mdm run")

        assert rc == 1, f"Expected rc=1 (FAIL) for empty sec_adv_filing, got rc={rc}"

    def test_adviser_pass_after_inserting_sec_adv_filing_row(self, tmp_path, monkeypatch):
        """One row in sec_adv_filing → _require_silver_reader returns rc=0."""
        db_path = str(tmp_path / "silver.duckdb")
        _make_adv_fixture_db(db_path)

        con = duckdb.connect(db_path)
        con.execute("""
            INSERT INTO sec_adv_filing
            (accession_number, cik, form, adviser_name, sec_file_number,
             crd_number, effective_date, filing_status, source_format, parser_version)
            VALUES
            ('ADV-105958-20241218', 105958, 'ADV', 'THE VANGUARD GROUP, INC.',
             '801-11953', '105958', '2024-12-18', 'ACTIVE', 'xml', '1')
        """)
        con.close()

        monkeypatch.setenv("MDM_SILVER_DUCKDB", db_path)
        monkeypatch.delenv("WAREHOUSE_STORAGE_ROOT", raising=False)
        monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

        required = mdm_cli._required_tables_for_run("adviser")
        reader, rc = mdm_cli._require_silver_reader(required, "mdm run")

        assert rc == 0, f"Expected rc=0 (PASS) after inserting sec_adv_filing row, got rc={rc}"

    def test_adviser_validate_silver_tables_fail_empty(self, tmp_path, monkeypatch):
        """_validate_silver_tables returns a nonempty failures list when sec_adv_filing is empty."""
        db_path = str(tmp_path / "silver.duckdb")
        _make_adv_fixture_db(db_path)

        monkeypatch.setenv("MDM_SILVER_DUCKDB", db_path)
        monkeypatch.delenv("WAREHOUSE_STORAGE_ROOT", raising=False)

        required = mdm_cli._required_tables_for_run("adviser")
        reader, _rc = mdm_cli._require_silver_reader(
            {"sec_adv_filing": False},  # just-exist check — let reader be opened
            "mdm run",
        )
        if reader is None:
            pytest.skip("reader is None — silver source misconfigured in test env")

        failures = mdm_cli._validate_silver_tables(reader, required)
        assert failures, "Expected failures list to be nonempty for empty sec_adv_filing"
        assert any("sec_adv_filing" in f for f in failures)


# ---------------------------------------------------------------------------
# Fund preflight tests
# ---------------------------------------------------------------------------


class TestFundPreflight:
    """sec_adv_private_fund must be nonempty before mdm run --entity-type fund passes."""

    def test_fund_fail_on_empty_sec_adv_private_fund(self, tmp_path, monkeypatch):
        """Empty sec_adv_private_fund → _require_silver_reader returns rc=1."""
        db_path = str(tmp_path / "silver.duckdb")
        _make_adv_fixture_db(db_path)

        monkeypatch.setenv("MDM_SILVER_DUCKDB", db_path)
        monkeypatch.delenv("WAREHOUSE_STORAGE_ROOT", raising=False)
        monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

        required = mdm_cli._required_tables_for_run("fund")
        reader, rc = mdm_cli._require_silver_reader(required, "mdm run")

        assert rc == 1, f"Expected rc=1 (FAIL) for empty sec_adv_private_fund, got rc={rc}"

    def test_fund_pass_after_inserting_sec_adv_private_fund_row(self, tmp_path, monkeypatch):
        """One row in sec_adv_private_fund → _require_silver_reader returns rc=0."""
        db_path = str(tmp_path / "silver.duckdb")
        _make_adv_fixture_db(db_path)

        con = duckdb.connect(db_path)
        con.execute("""
            INSERT INTO sec_adv_private_fund
            (accession_number, fund_index, fund_name, fund_type, jurisdiction, aum_amount, parser_version)
            VALUES
            ('ADV-105958-20241218', 1, 'CSF PRIVATE FUND', 'Hedge Fund', 'Cayman Islands', 276012482.00, '1')
        """)
        con.close()

        monkeypatch.setenv("MDM_SILVER_DUCKDB", db_path)
        monkeypatch.delenv("WAREHOUSE_STORAGE_ROOT", raising=False)
        monkeypatch.delenv("MDM_DATABASE_URL", raising=False)

        required = mdm_cli._required_tables_for_run("fund")
        reader, rc = mdm_cli._require_silver_reader(required, "mdm run")

        assert rc == 0, f"Expected rc=0 (PASS) after inserting sec_adv_private_fund row, got rc={rc}"
