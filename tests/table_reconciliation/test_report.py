from __future__ import annotations

import json

from edgar_warehouse.table_reconciliation.contracts import TABLE_CONTRACTS
from edgar_warehouse.table_reconciliation.report import (
    build_report,
    compare_to_previous,
    render_report_json,
)


def _build_empty_schema(reader):
    for table_name, contract in TABLE_CONTRACTS.items():
        columns: dict[str, str] = {c: "VARCHAR" for c in contract.business_keys}
        if contract.bronze_anchor is not None:
            columns.setdefault(contract.bronze_anchor.child_column, "VARCHAR")
        if contract.logical_parent is not None:
            columns.setdefault(contract.logical_parent.child_column, "VARCHAR")
        if contract.authority_column:
            columns.setdefault(contract.authority_column, "TIMESTAMP")
        cols_sql = ", ".join(f'"{name}" {sql_type}' for name, sql_type in columns.items())
        reader.execute(f'CREATE TABLE "{table_name}" ({cols_sql})')


def test_build_report_against_empty_schema_is_fail_closed_but_clean(duckdb_reader, snowflake_reader):
    _build_empty_schema(duckdb_reader)
    _build_empty_schema(snowflake_reader)

    report = build_report(duckdb_reader, snowflake_reader, cohort_size=50)

    assert report["overall_status"] == "pass"
    assert report["tables_checked"] == len(TABLE_CONTRACTS)
    assert report["tables_failing"] == []
    assert "sec_thirteenf_holding" in report["tables"]
    assert report["case_coverage"]["volume_large"] == "sec_thirteenf_holding"
    # PASS/FAIL must be a literal, machine-checkable field on every table --
    # not something a reader has to infer from prose.
    for table_name, payload in report["tables"].items():
        assert payload["overall_status"] in {"pass", "fail"}, table_name


def test_build_report_restricted_to_a_table_subset(duckdb_reader, snowflake_reader):
    _build_empty_schema(duckdb_reader)
    _build_empty_schema(snowflake_reader)

    report = build_report(
        duckdb_reader, snowflake_reader, cohort_size=50, table_names=["sec_company", "sec_thirteenf_holding"]
    )

    assert report["tables_checked"] == 2
    assert set(report["tables"]) == {"sec_company", "sec_thirteenf_holding"}


def test_build_report_rejects_unknown_table_name(duckdb_reader, snowflake_reader):
    _build_empty_schema(duckdb_reader)
    _build_empty_schema(snowflake_reader)

    import pytest

    with pytest.raises(ValueError):
        build_report(duckdb_reader, snowflake_reader, table_names=["not_a_real_table"])


def test_render_report_json_round_trips(duckdb_reader, snowflake_reader):
    _build_empty_schema(duckdb_reader)
    _build_empty_schema(snowflake_reader)
    report = build_report(duckdb_reader, snowflake_reader, cohort_size=50, table_names=["sec_company"])
    rendered = render_report_json(report)
    parsed = json.loads(rendered)
    assert parsed["overall_status"] == "pass"


def test_compare_to_previous_detects_no_drift_between_two_clean_runs(duckdb_reader, snowflake_reader):
    _build_empty_schema(duckdb_reader)
    _build_empty_schema(snowflake_reader)
    first = build_report(duckdb_reader, snowflake_reader, cohort_size=50, table_names=["sec_company"])
    second = build_report(duckdb_reader, snowflake_reader, cohort_size=50, table_names=["sec_company"])

    comparison = compare_to_previous(second, first)
    assert comparison["status"] == "pass"
    assert comparison["drifted_tables"] == []


def test_compare_to_previous_detects_real_digest_drift(duckdb_reader, snowflake_reader):
    _build_empty_schema(duckdb_reader)
    _build_empty_schema(snowflake_reader)
    baseline = build_report(duckdb_reader, snowflake_reader, cohort_size=50, table_names=["sec_company"])

    duckdb_reader.execute(
        "INSERT INTO sec_company (cik, last_synced_at) VALUES ('0000320193', '2026-01-01')"
    )
    snowflake_reader.execute(
        "INSERT INTO sec_company (cik, last_synced_at) VALUES ('0000320193', '2026-01-01')"
    )
    changed = build_report(duckdb_reader, snowflake_reader, cohort_size=50, table_names=["sec_company"])

    comparison = compare_to_previous(changed, baseline)
    assert comparison["status"] == "fail"
    assert len(comparison["drifted_tables"]) == 1
    assert comparison["drifted_tables"][0]["table_name"] == "sec_company"
