"""Tests for the DuckDB-vs-Snowflake silver parity check (silver-snowflake-
migration map, Ticket 10/12's correctness gate)."""

from __future__ import annotations

from edgar_warehouse.mdm.silver_parity import PARITY_TABLES, verify_silver_parity


class _FakeReader:
    """Minimal .fetch(sql, params)-compatible fake -- reader-agnostic by
    construction means this doesn't need to be a real ShardedSilverReader
    or SnowflakeSilverReader."""

    def __init__(self, table_counts: dict[str, int], ciks: list[int]) -> None:
        self._table_counts = table_counts
        self._ciks = ciks

    def fetch(self, sql: str, params=None) -> list[dict]:
        if "SELECT cik FROM sec_company" == sql:
            return [{"cik": cik} for cik in self._ciks]
        # Exact match on the table name after "FROM " -- a substring check
        # (e.g. "sec_company" in sql) would also match "sec_company_ticker"
        # queries and silently return the wrong fixture value, the same
        # stub-drift shape CLAUDE.md's INSTITUTIONAL_HOLDS incident warns
        # against for hand-rolled query stubs.
        table_name = sql.rsplit("FROM ", 1)[-1].strip()
        if table_name in self._table_counts:
            return [{"n": self._table_counts[table_name]}]
        raise AssertionError(f"no fixture for query: {sql}")


def _uniform_counts(value: int) -> dict[str, int]:
    return {table: value for table in PARITY_TABLES}


def test_identical_sources_pass():
    duckdb_reader = _FakeReader(_uniform_counts(5), ciks=[1, 2, 3])
    snowflake_reader = _FakeReader(_uniform_counts(5), ciks=[1, 2, 3])

    result = verify_silver_parity(duckdb_reader, snowflake_reader)

    assert result.passed is True
    assert all(t.matches for t in result.tables)
    assert result.cik_only_in_duckdb == []
    assert result.cik_only_in_snowflake == []


def test_every_parity_table_is_checked():
    duckdb_reader = _FakeReader(_uniform_counts(1), ciks=[])
    snowflake_reader = _FakeReader(_uniform_counts(1), ciks=[])

    result = verify_silver_parity(duckdb_reader, snowflake_reader)

    assert {t.table for t in result.tables} == set(PARITY_TABLES)


def test_row_count_mismatch_fails_and_is_reported():
    duckdb_counts = _uniform_counts(10)
    snowflake_counts = _uniform_counts(10)
    snowflake_counts["sec_company"] = 0  # matches Ticket 11's known live state

    duckdb_reader = _FakeReader(duckdb_counts, ciks=[1])
    snowflake_reader = _FakeReader(snowflake_counts, ciks=[])

    result = verify_silver_parity(duckdb_reader, snowflake_reader)

    assert result.passed is False
    company_result = next(t for t in result.tables if t.table == "sec_company")
    assert company_result.matches is False
    assert company_result.duckdb_count == 10
    assert company_result.snowflake_count == 0


def test_matching_counts_but_different_ciks_still_fails():
    # Ticket 10's exact stated concern: two sources could match on row
    # count and still resolve different CIKs to different entities. A
    # count-only check would pass this; the CIK-set diff must catch it.
    duckdb_reader = _FakeReader(_uniform_counts(2), ciks=[100, 200])
    snowflake_reader = _FakeReader(_uniform_counts(2), ciks=[100, 999])

    result = verify_silver_parity(duckdb_reader, snowflake_reader)

    assert result.passed is False
    assert all(t.matches for t in result.tables), "row counts alone matched -- CIK diff is what must fail this"
    assert result.cik_only_in_duckdb == [200]
    assert result.cik_only_in_snowflake == [999]


def test_a_missing_table_on_one_side_is_reported_as_an_error_not_a_silent_zero():
    class _MissingTableReader(_FakeReader):
        def fetch(self, sql: str, params=None) -> list[dict]:
            if "sec_guidance_fact_reject" in sql:
                raise Exception("SQL compilation error: Object 'SEC_GUIDANCE_FACT_REJECT' does not exist or not authorized")
            return super().fetch(sql, params)

    duckdb_reader = _FakeReader(_uniform_counts(3), ciks=[1])
    snowflake_reader = _MissingTableReader(_uniform_counts(3), ciks=[1])

    result = verify_silver_parity(duckdb_reader, snowflake_reader)

    assert result.passed is False
    reject_result = next(t for t in result.tables if t.table == "sec_guidance_fact_reject")
    assert reject_result.matches is False
    assert reject_result.error is not None
    assert "does not exist" in reject_result.error
    assert reject_result.snowflake_count is None
    assert reject_result.duckdb_count == 3  # the working side still reports its real count


def test_cik_set_fetch_failure_is_reported_not_raised():
    # Code review finding, 2026-08-18: the sec_company CIK-set comparison
    # used to be unguarded, unlike every per-table count above -- a real
    # connection error there would crash verify_silver_parity entirely
    # instead of surfacing as a failed, inspectable result.
    class _BrokenCikReader(_FakeReader):
        def fetch(self, sql: str, params=None) -> list[dict]:
            if sql == "SELECT cik FROM sec_company":
                raise Exception("SQL compilation error: Object 'SEC_COMPANY' does not exist or not authorized")
            return super().fetch(sql, params)

    duckdb_reader = _FakeReader(_uniform_counts(1), ciks=[1])
    snowflake_reader = _BrokenCikReader(_uniform_counts(1), ciks=[1])

    result = verify_silver_parity(duckdb_reader, snowflake_reader)

    assert result.passed is False
    assert result.cik_fetch_error is not None
    assert "does not exist" in result.cik_fetch_error
    assert result.payload["cik_fetch_error"] == result.cik_fetch_error


def test_payload_caps_reported_cik_samples():
    from edgar_warehouse.mdm.silver_parity import _MAX_REPORTED_CIK_SAMPLE

    many_ciks = list(range(_MAX_REPORTED_CIK_SAMPLE + 20))
    duckdb_reader = _FakeReader(_uniform_counts(0), ciks=many_ciks)
    snowflake_reader = _FakeReader(_uniform_counts(0), ciks=[])

    result = verify_silver_parity(duckdb_reader, snowflake_reader)
    payload = result.payload

    assert payload["cik_only_in_duckdb_total"] == len(many_ciks)
    assert len(payload["cik_only_in_duckdb_sample"]) == _MAX_REPORTED_CIK_SAMPLE


def test_verify_silver_parity_subcommand_is_registered():
    import argparse

    from edgar_warehouse.mdm.cli import register_mdm_subparser

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    register_mdm_subparser(sub)

    args = parser.parse_args(["mdm", "verify-silver-parity"])

    assert args.mdm_command == "verify-silver-parity"
    assert callable(args.handler)
