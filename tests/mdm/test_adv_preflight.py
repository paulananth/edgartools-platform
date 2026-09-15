"""MDM adviser/fund preflight fail->pass tests.

Proves the _require_silver_reader gate transitions from FAIL (empty sec_adv_filing /
sec_adv_private_fund) to PASS (populated table) for adviser and fund entity types.

MDM-ADV-02 automated proof — no network, no S3, no live Postgres required.

DuckDB Retirement Cutover Ticket 05: _require_silver_reader's own reader is
always EDGARTOOLS_SILVER via SnowflakeSilverReader. SnowflakeSilverReader.connect
is monkeypatched to a reader that answers the preflight's only query shape
(``SELECT COUNT(*) AS n FROM <table>``) from a table->count dict, so the gate
is exercised for real rather than passing by accident because there is no
live Snowflake in the test environment (the false-confirmed-by-the-wrong-
mechanism gap CLAUDE.md's MDM Postgres migration-011 entry documents). The
DuckDB-file fixture this replaced went with the engine (silver-merge-engine-
migration Ticket 17).
"""

from __future__ import annotations

import pytest

import edgar_warehouse.mdm.cli as mdm_cli
from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader


class _CountReader:
    """fetch()/close() over a table->row-count dict, the reader seam MDM expects."""

    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    def fetch(self, sql: str, params: list | None = None) -> list[dict]:
        table_name = sql.split(" FROM ", 1)[1].split()[0]
        if table_name not in self._counts:
            raise RuntimeError(f"Catalog Error: Table with name {table_name} does not exist")
        return [{"n": self._counts[table_name]}]

    def close(self) -> None:
        pass


def _patch_silver_reader(monkeypatch, counts: dict[str, int]) -> None:
    monkeypatch.setattr(SnowflakeSilverReader, "connect", staticmethod(lambda: _CountReader(counts)))
    monkeypatch.delenv("WAREHOUSE_STORAGE_ROOT", raising=False)
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)


_EMPTY_ADV_TABLES = {"sec_adv_filing": 0, "sec_adv_private_fund": 0}


class TestAdviserPreflight:
    """sec_adv_filing must be nonempty before mdm mastering --entity-type adviser passes."""

    def test_adviser_fail_on_empty_sec_adv_filing(self, monkeypatch):
        _patch_silver_reader(monkeypatch, dict(_EMPTY_ADV_TABLES))

        required = mdm_cli._required_tables_for_run("adviser")
        reader, rc = mdm_cli._require_silver_reader(required, "mdm mastering")

        assert rc == 1, f"Expected rc=1 (FAIL) for empty sec_adv_filing, got rc={rc}"

    def test_adviser_pass_with_a_sec_adv_filing_row(self, monkeypatch):
        _patch_silver_reader(monkeypatch, {**_EMPTY_ADV_TABLES, "sec_adv_filing": 1})

        required = mdm_cli._required_tables_for_run("adviser")
        reader, rc = mdm_cli._require_silver_reader(required, "mdm mastering")

        assert rc == 0, f"Expected rc=0 (PASS) with a sec_adv_filing row, got rc={rc}"

    def test_adviser_validate_silver_tables_fail_empty(self, monkeypatch):
        """_validate_silver_tables returns a nonempty failures list when sec_adv_filing is empty."""
        _patch_silver_reader(monkeypatch, dict(_EMPTY_ADV_TABLES))

        required = mdm_cli._required_tables_for_run("adviser")
        reader, _rc = mdm_cli._require_silver_reader(
            {"sec_adv_filing": False},  # just-exist check — let reader be opened
            "mdm mastering",
        )
        if reader is None:
            pytest.skip("reader is None — silver source misconfigured in test env")

        failures = mdm_cli._validate_silver_tables(reader, required)
        assert failures, "Expected failures list to be nonempty for empty sec_adv_filing"
        assert any("sec_adv_filing" in f for f in failures)


class TestFundPreflight:
    """sec_adv_private_fund must be nonempty before mdm mastering --entity-type fund passes."""

    def test_fund_fail_on_empty_sec_adv_private_fund(self, monkeypatch):
        _patch_silver_reader(monkeypatch, dict(_EMPTY_ADV_TABLES))

        required = mdm_cli._required_tables_for_run("fund")
        reader, rc = mdm_cli._require_silver_reader(required, "mdm mastering")

        assert rc == 1, f"Expected rc=1 (FAIL) for empty sec_adv_private_fund, got rc={rc}"

    def test_fund_pass_with_a_sec_adv_private_fund_row(self, monkeypatch):
        _patch_silver_reader(monkeypatch, {**_EMPTY_ADV_TABLES, "sec_adv_private_fund": 1})

        required = mdm_cli._required_tables_for_run("fund")
        reader, rc = mdm_cli._require_silver_reader(required, "mdm mastering")

        assert rc == 0, f"Expected rc=0 (PASS) with a sec_adv_private_fund row, got rc={rc}"
