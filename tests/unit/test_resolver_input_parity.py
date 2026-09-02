"""DuckDB Retirement Cutover Ticket 05's correctness evidence:
verify_resolver_input_parity's digest-based row comparison.

Uses .fetch()-based fakes on both sides (reader-type agnostic by
construction, same as verify_silver_parity), so no real DuckDB or
Snowflake connection is needed to exercise the comparator itself.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from edgar_warehouse.mdm.silver_parity import (
    RESOLVER_INPUT_TABLES,
    verify_resolver_input_parity,
)


class _FakeReader:
    """Minimal .fetch()-based fake: `rows` maps table -> list of row dicts.
    Supports ORDER BY <cols> ASC/DESC LIMIT <n> and WHERE <col> = ? AND ...
    against those in-memory rows, matching exactly the two SQL shapes
    verify_resolver_input_parity issues.
    """

    def __init__(self, rows: dict[str, list[dict]]) -> None:
        self._rows = rows

    def fetch(self, sql: str, params: list | None = None) -> list[dict]:
        table = next(name for name in self._rows if name in sql)
        rows = self._rows[table]

        if sql.strip().upper().startswith("SELECT * FROM") and "WHERE" in sql.upper():
            # Row-by-key fetch: params are the key column values, in the
            # same order the WHERE clause was built (key_columns order).
            key_columns = tuple(part.split("=")[0].strip() for part in sql.split("WHERE", 1)[1].split("AND"))
            matches = [
                row for row in rows
                if all(row.get(col) == value for col, value in zip(key_columns, params or []))
            ]
            return matches

        # Sample-keys fetch: "SELECT <cols> FROM <table> ORDER BY <cols> ASC|DESC LIMIT <n>"
        select_cols = sql.split("SELECT", 1)[1].split("FROM", 1)[0].strip().split(", ")
        descending = "DESC" in sql.upper()
        limit = int(sql.strip().rsplit(" ", 1)[-1])
        order_cols = select_cols
        sorted_rows = sorted(
            rows, key=lambda row: tuple(row[col] for col in order_cols), reverse=descending
        )
        return [{col: row[col] for col in select_cols} for row in sorted_rows[:limit]]


def _company_rows(n: int, *, offset: int = 0) -> list[dict]:
    return [{"cik": offset + i, "entity_name": f"Company {offset + i}"} for i in range(n)]


class TestVerifyResolverInputParityIdenticalRows:
    def test_identical_rows_on_both_sides_pass(self) -> None:
        rows = _company_rows(5)
        duckdb_reader = _FakeReader({"sec_company": rows})
        snowflake_reader = _FakeReader({"sec_company": [dict(r) for r in rows]})

        result = verify_resolver_input_parity(
            duckdb_reader, snowflake_reader, entity_types=["company"]
        )

        assert result["company"].passed
        table = result["company"].tables[0]
        assert table.table == "sec_company"
        assert table.keys_compared == 5
        assert table.mismatched_keys == []
        assert table.missing_keys == []

    def test_payload_reports_missing_and_mismatched_as_separate_fields(self) -> None:
        duckdb_rows = _company_rows(3)  # cik 0, 1, 2
        snowflake_rows = [dict(r) for r in duckdb_rows if r["cik"] != 2]  # drop cik 2
        snowflake_rows[1]["entity_name"] = "Drifted Name"  # cik 1 content differs

        duckdb_reader = _FakeReader({"sec_company": duckdb_rows})
        snowflake_reader = _FakeReader({"sec_company": snowflake_rows})

        result = verify_resolver_input_parity(
            duckdb_reader, snowflake_reader, entity_types=["company"]
        )

        payload = result["company"].tables[0].to_payload()
        assert payload["mismatched_keys_total"] == 1
        assert payload["mismatched_keys_sample"] == [[1]]
        assert payload["missing_keys_total"] == 1
        assert payload["missing_keys_sample"] == [[2]]
        assert payload["matches"] is False


class TestVerifyResolverInputParityMismatch:
    def test_mismatched_content_fails_and_reports_the_key(self) -> None:
        duckdb_rows = _company_rows(3)
        snowflake_rows = [dict(r) for r in duckdb_rows]
        snowflake_rows[1]["entity_name"] = "Drifted Name"  # cik=1 differs

        duckdb_reader = _FakeReader({"sec_company": duckdb_rows})
        snowflake_reader = _FakeReader({"sec_company": snowflake_rows})

        result = verify_resolver_input_parity(
            duckdb_reader, snowflake_reader, entity_types=["company"]
        )

        assert not result["company"].passed
        table = result["company"].tables[0]
        assert table.mismatched_keys == [(1,)]

    def test_row_missing_on_one_side_still_fails_but_is_reported_as_missing_not_mismatched(self) -> None:
        """DuckDB Retirement Cutover Ticket 05's own flagged defect: the gate
        used to conflate 'row absent on the other side' with 'row present on
        both sides but content differs', reporting a coverage gap as a
        content mismatch. A missing row must still fail the overall check
        (this is not silently downgraded to a pass -- Ticket 15's job is to
        close coverage gaps, not this gate's job to look past them) but must
        be reported in its own category so an operator reading the payload
        can tell a coverage gap from real content corruption."""
        duckdb_rows = _company_rows(3)
        snowflake_reader_rows = [r for r in duckdb_rows if r["cik"] != 2]

        duckdb_reader = _FakeReader({"sec_company": duckdb_rows})
        snowflake_reader = _FakeReader({"sec_company": snowflake_reader_rows})

        result = verify_resolver_input_parity(
            duckdb_reader, snowflake_reader, entity_types=["company"]
        )

        assert not result["company"].passed
        table = result["company"].tables[0]
        assert (2,) in table.missing_keys
        assert (2,) not in table.mismatched_keys

    def test_scope_divergence_alone_does_not_masquerade_as_content_corruption(self) -> None:
        """The actual bug this fix closes: previously, a key sampled from
        DuckDB that simply doesn't exist yet in Snowflake (real prod state
        as of 2026-09-01, per this ticket's own live-verification note) was
        reported identically to a key whose content genuinely differs. Every
        genuinely-overlapping row here is byte-identical; only one side has
        an extra, non-overlapping row -- the payload must show that as pure
        missingness, zero content mismatches."""
        duckdb_rows = _company_rows(3)  # cik 0, 1, 2
        snowflake_rows = [dict(r) for r in duckdb_rows if r["cik"] != 2]  # missing cik 2 only

        duckdb_reader = _FakeReader({"sec_company": duckdb_rows})
        snowflake_reader = _FakeReader({"sec_company": snowflake_rows})

        result = verify_resolver_input_parity(
            duckdb_reader, snowflake_reader, entity_types=["company"]
        )

        table = result["company"].tables[0]
        assert table.mismatched_keys == []
        assert table.missing_keys == [(2,)]
        assert not table.matches  # still fails overall -- missingness is not silently waved through


class TestVerifyResolverInputParityTypeCoercion:
    def test_decimal_vs_int_type_drift_is_caught_not_normalized_away(self) -> None:
        """Advisor-flagged failure mode: Snowflake's connector returns Decimal
        where DuckDB returns int for numeric columns. content_hash's
        json.dumps(..., default=str) serializes these differently on
        purpose -- this is a real cross-backend behavior difference MDM's
        own _skip_if_unchanged already depends on being stable, not a
        cosmetic one to normalize away."""
        duckdb_rows: list[dict[str, Any]] = [{"cik": 1, "aum_amount": 100}]
        snowflake_rows: list[dict[str, Any]] = [{"cik": 1, "aum_amount": Decimal("100")}]

        duckdb_reader = _FakeReader({"sec_company": duckdb_rows})
        snowflake_reader = _FakeReader({"sec_company": snowflake_rows})

        result = verify_resolver_input_parity(
            duckdb_reader, snowflake_reader, entity_types=["company"]
        )

        assert not result["company"].passed
        assert result["company"].tables[0].mismatched_keys == [(1,)]


class TestVerifyResolverInputParitySampling:
    def test_large_tables_get_a_larger_sample_than_default(self) -> None:
        # 300 rows in each of the two ownership tables; default sample_size=25
        # would undercount them if the large-table override weren't applied.
        big = [
            {"accession_number": f"A{i:04d}", "owner_index": 0, "txn_index": 0, "shares": i}
            for i in range(300)
        ]
        duckdb_reader = _FakeReader(
            {
                "sec_ownership_non_derivative_txn": big,
                "sec_ownership_derivative_txn": big,
            }
        )
        snowflake_reader = _FakeReader(
            {
                "sec_ownership_non_derivative_txn": [dict(r) for r in big],
                "sec_ownership_derivative_txn": [dict(r) for r in big],
            }
        )

        result = verify_resolver_input_parity(
            duckdb_reader,
            snowflake_reader,
            entity_types=["security"],
            sample_size=5,
            large_table_sample_size=50,
        )

        assert result["security"].passed
        for table in result["security"].tables:
            # ASC(50) + DESC(50) deduplicated -- 100 for a 300-row table with
            # no overlap between the two halves.
            assert table.keys_compared == 100

    def test_small_tables_use_the_default_sample_size(self) -> None:
        rows = _company_rows(3)
        duckdb_reader = _FakeReader({"sec_company": rows})
        snowflake_reader = _FakeReader({"sec_company": [dict(r) for r in rows]})

        result = verify_resolver_input_parity(
            duckdb_reader, snowflake_reader, entity_types=["company"], sample_size=25
        )

        # Only 3 rows exist; ASC(25) + DESC(25) dedupe down to all 3.
        assert result["company"].tables[0].keys_compared == 3


class TestVerifyResolverInputParityErrors:
    def test_missing_table_surfaces_as_a_table_error_not_a_crash(self) -> None:
        class _RaisingReader:
            def fetch(self, sql, params=None):
                raise RuntimeError("Catalog Error: table does not exist")

        result = verify_resolver_input_parity(
            _RaisingReader(), _RaisingReader(), entity_types=["company"]
        )

        assert not result["company"].passed
        assert result["company"].tables[0].error is not None

    def test_all_five_entity_types_covered_by_default(self) -> None:
        assert set(RESOLVER_INPUT_TABLES) == {"company", "adviser", "fund", "person", "security"}

    def test_defaults_to_all_entity_types_when_none_specified(self) -> None:
        rows = _company_rows(1)
        empty_reader = _FakeReader(
            {
                "sec_company": rows,
                "sec_adv_filing": [],
                "sec_adv_private_fund": [],
                "sec_ownership_reporting_owner": [],
                "sec_ownership_non_derivative_txn": [],
                "sec_ownership_derivative_txn": [],
            }
        )

        result = verify_resolver_input_parity(empty_reader, empty_reader)

        assert set(result) == {"company", "adviser", "fund", "person", "security"}
