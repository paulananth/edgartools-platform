"""Assembles the fail-closed table-reconciliation report: runs
``collector.reconcile_table`` for every table in ``TABLE_CONTRACTS``
against real DuckDB canonical and Snowflake ``EDGARTOOLS_SILVER`` readers,
and renders unambiguous PASS/FAIL per table plus an overall verdict --
never a prose summary a human has to interpret (Ticket 08's own checklist
item 5).
"""
from __future__ import annotations

import json
from typing import Any

from edgar_warehouse.table_reconciliation.case_coverage import build_case_coverage
from edgar_warehouse.table_reconciliation.collector import (
    TableReconciliationResult,
    reconcile_table,
)
from edgar_warehouse.table_reconciliation.contracts import TABLE_CONTRACTS
from edgar_warehouse.table_reconciliation.digest import sha256_of
from edgar_warehouse.table_reconciliation.sql_checks import Reader


def _link_dict(link: Any) -> dict[str, Any] | None:
    if link is None:
        return None
    return {
        "child_table": link.child_table,
        "child_column": link.child_column,
        "parent_table": link.parent_table,
        "parent_column": link.parent_column,
    }


def _table_result_payload(result: TableReconciliationResult) -> dict[str, Any]:
    return {
        "table_name": result.table_name,
        "cardinality": result.cardinality,
        "overall_status": result.overall_status,
        "legitimate_zero_note": result.legitimate_zero_note,
        "bronze_to_silver_key_expectations": (
            {
                "link": _link_dict(result.bronze_to_silver.link),
                "orphan_count": result.bronze_to_silver.orphan_count,
                "status": result.bronze_to_silver.status,
            }
            if result.bronze_to_silver is not None
            else {"status": "not_applicable", "reason": "table is a root anchor for its own family"}
        ),
        "required_parent_integrity": (
            {
                "link": _link_dict(result.required_parent.link),
                "orphan_count": result.required_parent.orphan_count,
                "status": result.required_parent.status,
            }
            if result.required_parent is not None
            else {"status": "not_applicable", "reason": "table is a root anchor for its own family"}
        ),
        "primary_key_uniqueness": {
            "duplicate_group_count": result.pk_uniqueness.duplicate_group_count,
            "status": result.pk_uniqueness.status,
        },
        "semantic_content_digest": {
            "scope_mode": result.semantic_digest.scope_mode,
            "cohort_size": result.semantic_digest.cohort_size,
            "compared_key_count": result.semantic_digest.compared_key_count,
            "out_of_scope_count": result.semantic_digest.out_of_scope_count,
            "duckdb_only_count": result.semantic_digest.duckdb_only_count,
            "snowflake_only_count": result.semantic_digest.snowflake_only_count,
            "duckdb_key_digest": result.semantic_digest.duckdb_key_digest,
            "snowflake_key_digest": result.semantic_digest.snowflake_key_digest,
            "duckdb_semantic_digest": result.semantic_digest.duckdb_semantic_digest,
            "snowflake_semantic_digest": result.semantic_digest.snowflake_semantic_digest,
            "cohort_keys_digest": result.semantic_digest.cohort_keys_digest,
            "status": result.semantic_digest.status,
        },
    }


def build_report(
    duckdb_reader: Reader,
    snowflake_reader: Reader,
    *,
    cohort_size: int = 500,
    table_names: list[str] | None = None,
) -> dict[str, Any]:
    """Run the full reconciliation. ``table_names`` restricts the run to a
    subset (for fast targeted invocations); defaults to every table in
    ``TABLE_CONTRACTS``.
    """
    names = table_names if table_names is not None else sorted(TABLE_CONTRACTS)
    unknown = set(names) - set(TABLE_CONTRACTS)
    if unknown:
        raise ValueError(f"unknown table(s) requested: {sorted(unknown)}")

    table_results: dict[str, TableReconciliationResult] = {}
    for table_name in names:
        contract = TABLE_CONTRACTS[table_name]
        table_results[table_name] = reconcile_table(
            duckdb_reader, snowflake_reader, contract, cohort_size=cohort_size
        )

    tables_payload = {name: _table_result_payload(result) for name, result in table_results.items()}
    failing_tables = sorted(
        name for name, result in table_results.items() if result.overall_status == "fail"
    )
    coverage = build_case_coverage()

    report: dict[str, Any] = {
        "tool": "table_reconciliation",
        "ticket": "duckdb-retirement-cutover-08",
        "cohort_size": cohort_size,
        "tables_checked": len(table_results),
        "tables_failing": failing_tables,
        "overall_status": "fail" if failing_tables else "pass",
        "case_coverage": {
            "routing_band": coverage.routing_band,
            "volume_large": coverage.volume_large,
            "volume_small": coverage.volume_small,
            "parser_optional": coverage.parser_optional,
            "boundary": coverage.boundary_note,
            "no_op": coverage.no_op_note,
            "guarded_publication": coverage.guarded_publication_note,
        },
        "tables": tables_payload,
    }
    report["report_digest"] = sha256_of(tables_payload)
    return report


def compare_to_previous(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    """The no-op / rerun-idempotency check: two real invocations of this
    tool (against an unchanged Snowflake watermark) should reproduce
    identical per-table digests. Returns a report section, not a boolean --
    the caller decides how to fail closed on drift.
    """
    current_tables = current.get("tables", {})
    previous_tables = previous.get("tables", {})
    drifted: list[dict[str, Any]] = []
    for table_name in sorted(set(current_tables) & set(previous_tables)):
        cur = current_tables[table_name]["semantic_content_digest"]
        prev = previous_tables[table_name]["semantic_content_digest"]
        if (
            cur["duckdb_semantic_digest"] != prev["duckdb_semantic_digest"]
            or cur["snowflake_semantic_digest"] != prev["snowflake_semantic_digest"]
            or cur["duckdb_key_digest"] != prev["duckdb_key_digest"]
            or cur["snowflake_key_digest"] != prev["snowflake_key_digest"]
        ):
            drifted.append(
                {
                    "table_name": table_name,
                    "current": cur,
                    "previous": prev,
                }
            )
    only_in_current = sorted(set(current_tables) - set(previous_tables))
    only_in_previous = sorted(set(previous_tables) - set(current_tables))
    status = "pass" if not drifted and not only_in_current and not only_in_previous else "fail"
    return {
        "status": status,
        "drifted_tables": drifted,
        "tables_only_in_current": only_in_current,
        "tables_only_in_previous": only_in_previous,
    }


def render_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)
