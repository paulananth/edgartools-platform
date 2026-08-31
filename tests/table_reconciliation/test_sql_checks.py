from __future__ import annotations

from edgar_warehouse.table_reconciliation import sql_checks


def test_table_exists_true_and_false(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE present_table (id INTEGER)")
    assert sql_checks.table_exists(duckdb_reader, "present_table") is True
    assert sql_checks.table_exists(duckdb_reader, "absent_table") is False


def test_count_rows(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE t (id INTEGER)")
    duckdb_reader.execute("INSERT INTO t VALUES (1), (2), (3)")
    assert sql_checks.count_rows(duckdb_reader, "t") == 3


def test_orphan_count_zero_when_all_children_have_parents(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE parent (cik INTEGER)")
    duckdb_reader.execute("INSERT INTO parent VALUES (1), (2)")
    duckdb_reader.execute("CREATE TABLE child (cik INTEGER)")
    duckdb_reader.execute("INSERT INTO child VALUES (1), (2)")
    assert (
        sql_checks.orphan_count(
            duckdb_reader, child_table="child", child_column="cik", parent_table="parent", parent_column="cik"
        )
        == 0
    )


def test_orphan_count_detects_real_orphans(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE parent (cik INTEGER)")
    duckdb_reader.execute("INSERT INTO parent VALUES (1)")
    duckdb_reader.execute("CREATE TABLE child (cik INTEGER)")
    duckdb_reader.execute("INSERT INTO child VALUES (1), (2), (3)")
    assert (
        sql_checks.orphan_count(
            duckdb_reader, child_table="child", child_column="cik", parent_table="parent", parent_column="cik"
        )
        == 2
    )


def test_orphan_count_ignores_null_child_values(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE parent (cik INTEGER)")
    duckdb_reader.execute("INSERT INTO parent VALUES (1)")
    duckdb_reader.execute("CREATE TABLE child (cik INTEGER)")
    duckdb_reader.execute("INSERT INTO child VALUES (1), (NULL)")
    assert (
        sql_checks.orphan_count(
            duckdb_reader, child_table="child", child_column="cik", parent_table="parent", parent_column="cik"
        )
        == 0
    )


def test_duplicate_key_group_count_zero_for_unique_keys(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE t (a INTEGER, b INTEGER)")
    duckdb_reader.execute("INSERT INTO t VALUES (1, 1), (1, 2), (2, 1)")
    assert sql_checks.duplicate_key_group_count(duckdb_reader, "t", ("a", "b")) == 0


def test_duplicate_key_group_count_detects_real_duplicates(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE t (a INTEGER, b INTEGER)")
    duckdb_reader.execute("INSERT INTO t VALUES (1, 1), (1, 1), (2, 1), (2, 1), (2, 1)")
    # Two distinct duplicated key-tuples: (1,1) and (2,1) -- the count is of
    # duplicated *groups*, not extra rows.
    assert sql_checks.duplicate_key_group_count(duckdb_reader, "t", ("a", "b")) == 2


def test_max_authority_value(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE t (id INTEGER, ts TIMESTAMP)")
    duckdb_reader.execute("INSERT INTO t VALUES (1, '2026-01-01'), (2, '2026-06-01')")
    result = sql_checks.max_authority_value(duckdb_reader, "t", "ts")
    assert str(result).startswith("2026-06-01")


def test_fetch_key_cohort_includes_boundary_and_fills_to_limit(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE t (k INTEGER)")
    duckdb_reader.execute("INSERT INTO t SELECT * FROM range(1, 21)")
    cohort = sql_checks.fetch_key_cohort(duckdb_reader, "t", ("k",), limit=5)
    assert len(cohort) == 5
    values = {key[0] for key in cohort}
    assert 1 in values  # min boundary
    assert 20 in values  # max boundary


def test_fetch_key_cohort_returns_fewer_than_limit_on_small_table(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE t (k INTEGER)")
    duckdb_reader.execute("INSERT INTO t VALUES (1), (2)")
    cohort = sql_checks.fetch_key_cohort(duckdb_reader, "t", ("k",), limit=500)
    assert len(cohort) == 2


def test_fetch_key_cohort_is_deterministic_across_calls(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE t (k INTEGER)")
    duckdb_reader.execute("INSERT INTO t SELECT * FROM range(1, 101)")
    first = sql_checks.fetch_key_cohort(duckdb_reader, "t", ("k",), limit=10)
    second = sql_checks.fetch_key_cohort(duckdb_reader, "t", ("k",), limit=10)
    assert first == second


def test_fetch_key_cohort_respects_where_clause(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE t (k INTEGER, flag BOOLEAN)")
    duckdb_reader.execute("INSERT INTO t SELECT i, i <= 5 FROM range(1, 21) AS r(i)")
    cohort = sql_checks.fetch_key_cohort(
        duckdb_reader, "t", ("k",), limit=100, where_sql="flag = ?", where_params=[True]
    )
    values = {key[0] for key in cohort}
    assert values.issubset({1, 2, 3, 4, 5})


def test_fetch_rows_by_keys_returns_full_rows_for_exact_keys(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE t (a INTEGER, b INTEGER, payload VARCHAR)")
    duckdb_reader.execute(
        "INSERT INTO t VALUES (1, 1, 'x'), (1, 2, 'y'), (2, 1, 'z')"
    )
    rows = sql_checks.fetch_rows_by_keys(duckdb_reader, "t", ("a", "b"), [(1, 2), (2, 1)])
    payloads = {row["payload"] for row in rows}
    assert payloads == {"y", "z"}


def test_fetch_rows_by_keys_empty_keys_returns_empty_without_query(duckdb_reader):
    duckdb_reader.execute("CREATE TABLE t (a INTEGER)")
    assert sql_checks.fetch_rows_by_keys(duckdb_reader, "t", ("a",), []) == []


def test_safe_identifier_rejects_embedded_quote():
    import pytest

    with pytest.raises(ValueError):
        sql_checks.safe_identifier('bad"name')


def test_safe_identifier_rejects_sql_injection_attempt():
    import pytest

    with pytest.raises(ValueError):
        sql_checks.safe_identifier("t; DROP TABLE sec_company; --")


def test_safe_identifier_accepts_plain_token():
    assert sql_checks.safe_identifier("sec_company") == "sec_company"
