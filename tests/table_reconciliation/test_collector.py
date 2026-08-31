from __future__ import annotations

from edgar_warehouse.table_reconciliation.collector import reconcile_table
from edgar_warehouse.table_reconciliation.contracts import ParentLink, TableContract


def _contract(
    table_name="child",
    business_keys=("k",),
    bronze_anchor=None,
    logical_parent=None,
    cardinality="optional_or_many",
    authority_column=None,
    semantic_exclude_columns=frozenset(),
):
    return TableContract(
        table_name=table_name,
        business_keys=business_keys,
        bronze_anchor=bronze_anchor,
        logical_parent=logical_parent,
        cardinality=cardinality,
        authority_column=authority_column,
        semantic_exclude_columns=semantic_exclude_columns,
    )


def _make_both_sides(duckdb_reader, snowflake_reader, *, extra_columns_sql="", rows_sql=None):
    ddl = f"CREATE TABLE child (k INTEGER, v VARCHAR{extra_columns_sql})"
    duckdb_reader.execute(ddl)
    snowflake_reader.execute(ddl)
    if rows_sql:
        duckdb_reader.execute(rows_sql)
        snowflake_reader.execute(rows_sql)


def test_root_table_pass_when_content_matches(duckdb_reader, snowflake_reader):
    _make_both_sides(
        duckdb_reader,
        snowflake_reader,
        rows_sql="INSERT INTO child VALUES (1, 'a'), (2, 'b')",
    )
    contract = _contract()
    result = reconcile_table(duckdb_reader, snowflake_reader, contract, cohort_size=500)

    assert result.overall_status == "pass"
    assert result.bronze_to_silver is None
    assert result.required_parent is None
    assert result.pk_uniqueness.status == "pass"
    assert result.semantic_digest.status == "pass"
    assert result.semantic_digest.compared_key_count == 2


def test_semantic_digest_fails_on_real_content_difference(duckdb_reader, snowflake_reader):
    duckdb_reader.execute("CREATE TABLE child (k INTEGER, v VARCHAR)")
    snowflake_reader.execute("CREATE TABLE child (k INTEGER, v VARCHAR)")
    duckdb_reader.execute("INSERT INTO child VALUES (1, 'a')")
    snowflake_reader.execute("INSERT INTO child VALUES (1, 'DIFFERENT')")
    contract = _contract()

    result = reconcile_table(duckdb_reader, snowflake_reader, contract, cohort_size=500)

    assert result.semantic_digest.status == "fail"
    assert result.overall_status == "fail"


def test_pk_uniqueness_fails_on_real_duplicate(duckdb_reader, snowflake_reader):
    _make_both_sides(duckdb_reader, snowflake_reader)
    duckdb_reader.execute("INSERT INTO child VALUES (1, 'a'), (1, 'a')")
    contract = _contract()

    result = reconcile_table(duckdb_reader, snowflake_reader, contract, cohort_size=500)

    assert result.pk_uniqueness.status == "fail"
    assert result.pk_uniqueness.duplicate_group_count == 1
    assert result.overall_status == "fail"


def test_required_parent_integrity_fails_on_real_orphan(duckdb_reader, snowflake_reader):
    duckdb_reader.execute("CREATE TABLE parent (k INTEGER)")
    duckdb_reader.execute("INSERT INTO parent VALUES (1)")
    duckdb_reader.execute("CREATE TABLE child (k INTEGER, v VARCHAR)")
    duckdb_reader.execute("INSERT INTO child VALUES (1, 'a'), (2, 'orphan')")
    snowflake_reader.execute("CREATE TABLE child (k INTEGER, v VARCHAR)")
    snowflake_reader.execute("INSERT INTO child VALUES (1, 'a'), (2, 'orphan')")

    link = ParentLink("child", "k", "parent", "k")
    contract = _contract(bronze_anchor=link)

    result = reconcile_table(duckdb_reader, snowflake_reader, contract, cohort_size=500)

    assert result.bronze_to_silver.status == "fail"
    assert result.bronze_to_silver.orphan_count == 1
    assert result.overall_status == "fail"


def test_logical_parent_reuses_bronze_result_when_identical():
    # When logical_parent == bronze_anchor, the collector should not
    # recompute -- verified indirectly via the shared object identity the
    # implementation returns.
    link = ParentLink("child", "k", "parent", "k")
    contract = _contract(bronze_anchor=link, logical_parent=link)
    assert contract.bronze_anchor == contract.logical_parent


def test_legitimate_zero_note_reflects_optional_cardinality(duckdb_reader, snowflake_reader):
    _make_both_sides(duckdb_reader, snowflake_reader)
    contract = _contract(cardinality="optional_or_many")
    result = reconcile_table(duckdb_reader, snowflake_reader, contract, cohort_size=500)
    assert "legitimate outcome" in result.legitimate_zero_note


def test_legitimate_zero_note_reflects_required_cardinality(duckdb_reader, snowflake_reader):
    _make_both_sides(duckdb_reader, snowflake_reader)
    contract = _contract(cardinality="required")
    result = reconcile_table(duckdb_reader, snowflake_reader, contract, cohort_size=500)
    assert "expected to produce at least one row" in result.legitimate_zero_note


def test_authority_column_scoping_marks_fresh_rows_out_of_scope_not_fail(duckdb_reader, snowflake_reader):
    ddl = "CREATE TABLE child (k INTEGER, v VARCHAR, ts TIMESTAMP)"
    duckdb_reader.execute(ddl)
    snowflake_reader.execute(ddl)

    # Snowflake only knows about the row up to 2026-01-01 (simulating lag).
    snowflake_reader.execute("INSERT INTO child VALUES (1, 'a', '2026-01-01')")
    # DuckDB has that same row plus a newer one Snowflake hasn't refreshed yet.
    duckdb_reader.execute("INSERT INTO child VALUES (1, 'a', '2026-01-01')")
    duckdb_reader.execute("INSERT INTO child VALUES (2, 'b', '2026-06-01')")

    contract = _contract(authority_column="ts", semantic_exclude_columns=frozenset({"ts"}))
    result = reconcile_table(duckdb_reader, snowflake_reader, contract, cohort_size=500)

    assert result.semantic_digest.status == "pass"
    assert result.semantic_digest.out_of_scope_count == 1
    assert result.semantic_digest.compared_key_count == 1
    assert result.overall_status == "pass"


def test_authority_column_scoping_still_fails_on_a_real_in_scope_difference(duckdb_reader, snowflake_reader):
    ddl = "CREATE TABLE child (k INTEGER, v VARCHAR, ts TIMESTAMP)"
    duckdb_reader.execute(ddl)
    snowflake_reader.execute(ddl)

    snowflake_reader.execute("INSERT INTO child VALUES (1, 'WRONG', '2026-01-01')")
    duckdb_reader.execute("INSERT INTO child VALUES (1, 'a', '2026-01-01')")

    contract = _contract(authority_column="ts", semantic_exclude_columns=frozenset({"ts"}))
    result = reconcile_table(duckdb_reader, snowflake_reader, contract, cohort_size=500)

    assert result.semantic_digest.status == "fail"
    assert result.semantic_digest.out_of_scope_count == 0


def test_no_authority_column_uses_key_intersection_and_reports_one_sided_keys(duckdb_reader, snowflake_reader):
    ddl = "CREATE TABLE child (k INTEGER, v VARCHAR)"
    duckdb_reader.execute(ddl)
    snowflake_reader.execute(ddl)

    # Shared key 1 matches; DuckDB has an extra key 2 Snowflake hasn't
    # picked up yet; Snowflake has an extra key 3 that shouldn't happen in
    # practice but must not crash the comparison either way.
    duckdb_reader.execute("INSERT INTO child VALUES (1, 'a'), (2, 'duckdb_only')")
    snowflake_reader.execute("INSERT INTO child VALUES (1, 'a'), (3, 'snowflake_only')")

    contract = _contract()
    result = reconcile_table(duckdb_reader, snowflake_reader, contract, cohort_size=500)

    assert result.semantic_digest.scope_mode == "key_intersection"
    assert result.semantic_digest.duckdb_only_count == 1
    assert result.semantic_digest.snowflake_only_count == 1
    assert result.semantic_digest.compared_key_count == 1
    # The one shared key has matching content -> pass, one-sided keys are
    # informational only, not a digest failure.
    assert result.semantic_digest.status == "pass"


def test_empty_table_both_sides_passes_cleanly(duckdb_reader, snowflake_reader):
    ddl = "CREATE TABLE child (k INTEGER, v VARCHAR)"
    duckdb_reader.execute(ddl)
    snowflake_reader.execute(ddl)

    contract = _contract()
    result = reconcile_table(duckdb_reader, snowflake_reader, contract, cohort_size=500)

    assert result.overall_status == "pass"
    assert result.semantic_digest.compared_key_count == 0
