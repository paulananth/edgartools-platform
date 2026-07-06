"""validate-data-quality command module."""

from __future__ import annotations

import json
from typing import Any

from edgar_warehouse.application.command_context_factory import build_warehouse_context
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext

_FK_CHECKS = [
    ("sec_company_address", "cik", "sec_company", "cik"),
    ("sec_company_former_name", "cik", "sec_company", "cik"),
    ("sec_company_submission_file", "cik", "sec_company", "cik"),
    ("sec_company_ticker", "cik", "sec_company", "cik"),
    ("sec_company_filing", "cik", "sec_company", "cik"),
    ("sec_filing_attachment", "accession_number", "sec_company_filing", "accession_number"),
    ("sec_filing_text", "accession_number", "sec_company_filing", "accession_number"),
    (
        "sec_ownership_reporting_owner",
        "accession_number",
        "sec_company_filing",
        "accession_number",
    ),
    (
        "sec_ownership_non_derivative_txn",
        "accession_number",
        "sec_company_filing",
        "accession_number",
    ),
    (
        "sec_ownership_derivative_txn",
        "accession_number",
        "sec_company_filing",
        "accession_number",
    ),
    ("sec_adv_office", "accession_number", "sec_adv_filing", "accession_number"),
    ("sec_adv_disclosure_event", "accession_number", "sec_adv_filing", "accession_number"),
    ("sec_adv_private_fund", "accession_number", "sec_adv_filing", "accession_number"),
    ("sec_financial_fact", "accession_number", "sec_company_filing", "accession_number"),
    ("sec_financial_derived", "accession_number", "sec_company_filing", "accession_number"),
    ("sec_earnings_release", "accession_number", "sec_company_filing", "accession_number"),
    ("sec_accounting_flag", "accession_number", "sec_company_filing", "accession_number"),
    ("sec_executive_record", "accession_number", "sec_company_filing", "accession_number"),
    ("sec_thirteenf_holding", "accession_number", "sec_company_filing", "accession_number"),
]

_DIRECT_GOLD_SILVER_TABLES = {
    "sec_financial_fact": "sec_financial_fact",
    "sec_thirteenf_holding": "sec_thirteenf_holding",
    "sec_financial_derived": "sec_financial_derived",
    "fact_earnings_release": "sec_earnings_release",
    "fact_executive_record": "sec_executive_record",
    "fact_accounting_flag": "sec_accounting_flag",
}


def execute(args: Any) -> int:
    from edgar_warehouse.application import warehouse_orchestrator

    arguments = warehouse_orchestrator._namespace_to_payload(args)
    try:
        context = build_warehouse_context("validate-data-quality")
        report = validate_data_quality(context=context)
    except WarehouseRuntimeError as exc:
        print(
            json.dumps(
                warehouse_orchestrator._error_payload(
                    "validate-data-quality",
                    arguments,
                    str(exc),
                    runtime_mode="bronze_capture",
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


def validate_data_quality(*, context: WarehouseCommandContext) -> dict[str, Any]:
    from edgar_warehouse.application.warehouse_orchestrator import (
        _hydrate_silver_database_from_storage,
    )
    from edgar_warehouse.silver_support.session import open_silver_database

    _hydrate_silver_database_from_storage(context)
    db = open_silver_database(context.silver_root)
    try:
        table_counts = _current_table_counts(db)
        findings: list[dict[str, Any]] = []
        checks = {
            "row_count_monotonic": _check_row_count_monotonic(db, table_counts, findings),
            "foreign_keys": _check_foreign_keys(db, findings),
            "gold_vs_silver": _check_gold_vs_silver(db, table_counts, findings),
            "null_ratios": _build_null_ratio_report(db, table_counts),
        }
    finally:
        db.close()

    status = "ok" if not findings else "failed"
    return {
        "command": "validate-data-quality",
        "status": status,
        "checks": checks,
        "findings": findings,
    }


def _check_row_count_monotonic(
    db: Any,
    table_counts: dict[str, int],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    previous = _latest_previous_table_counts(db)
    if previous is None:
        return {
            "status": "skipped",
            "reason": "no previous completed pipeline_run with silver_table_counts",
            "current_counts": table_counts,
        }

    previous_run_id = previous["pipeline_run_id"]
    previous_counts = previous["table_counts"]
    regressions = []
    for table, previous_count in sorted(previous_counts.items()):
        if table not in table_counts:
            continue
        current_count = table_counts[table]
        if current_count < previous_count:
            finding = {
                "type": "row_count_regression",
                "table": table,
                "previous_count": previous_count,
                "current_count": current_count,
                "previous_pipeline_run_id": previous_run_id,
            }
            regressions.append(finding)
            findings.append(finding)

    return {
        "status": "ok" if not regressions else "failed",
        "previous_pipeline_run_id": previous_run_id,
        "regressions": regressions,
        "current_counts": table_counts,
    }


def _latest_previous_table_counts(db: Any) -> dict[str, Any] | None:
    rows = db.fetch(
        """
        SELECT pipeline_run_id, metrics_json
        FROM pipeline_run
        WHERE status IN ('succeeded', 'ok')
          AND metrics_json IS NOT NULL
        ORDER BY completed_at DESC NULLS LAST, started_at DESC
        LIMIT 10
        """
    )
    for row in rows:
        metrics = _json_object(row.get("metrics_json"))
        table_counts = metrics.get("silver_table_counts")
        if isinstance(table_counts, dict):
            return {
                "pipeline_run_id": row["pipeline_run_id"],
                "table_counts": {
                    str(table): int(count)
                    for table, count in table_counts.items()
                    if isinstance(count, int)
                },
            }
    return None


def _check_foreign_keys(db: Any, findings: list[dict[str, Any]]) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    for child_table, child_column, parent_table, parent_column in _FK_CHECKS:
        check_name = f"{child_table}.{child_column}->{parent_table}.{parent_column}"
        if not _table_exists(db, child_table) or not _table_exists(db, parent_table):
            checks[check_name] = {"status": "skipped", "reason": "table_missing"}
            continue
        orphan_count = _orphan_count(
            db,
            child_table=child_table,
            child_column=child_column,
            parent_table=parent_table,
            parent_column=parent_column,
        )
        status = "ok" if orphan_count == 0 else "failed"
        checks[check_name] = {
            "status": status,
            "orphan_count": orphan_count,
            "table": child_table,
            "column": child_column,
            "referenced_table": parent_table,
            "referenced_column": parent_column,
        }
        if orphan_count:
            findings.append(
                {
                    "type": "foreign_key_orphan",
                    "table": child_table,
                    "column": child_column,
                    "referenced_table": parent_table,
                    "referenced_column": parent_column,
                    "orphan_count": orphan_count,
                }
            )

    return {
        "status": "ok"
        if all(check["status"] in {"ok", "skipped"} for check in checks.values())
        else "failed",
        "checks": checks,
    }


def _check_gold_vs_silver(
    db: Any,
    table_counts: dict[str, int],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    from edgar_warehouse.serving.gold_models import build_gold

    try:
        gold_tables = build_gold(db)
    except Exception as exc:
        finding = {"type": "gold_build_error", "error": str(exc)}
        findings.append(finding)
        return {"status": "failed", "tables": {}, "error": str(exc)}

    tables: dict[str, dict[str, Any]] = {}
    for gold_table, silver_table in _DIRECT_GOLD_SILVER_TABLES.items():
        if gold_table not in gold_tables:
            tables[gold_table] = {
                "silver_table": silver_table,
                "gold_table": gold_table,
                "status": "skipped",
                "reason": "gold_table_missing",
            }
            continue
        silver_rows = table_counts.get(silver_table, _count_rows(db, silver_table))
        gold_result = gold_tables[gold_table]
        gold_rows = int(
            gold_result.num_rows if hasattr(gold_result, "num_rows") else len(gold_result)
        )
        status = "ok" if silver_rows == gold_rows else "failed"
        tables[gold_table] = {
            "silver_table": silver_table,
            "gold_table": gold_table,
            "silver_rows": silver_rows,
            "gold_rows": gold_rows,
            "status": status,
        }
        if status != "ok":
            findings.append(
                {
                    "type": "gold_silver_count_mismatch",
                    "silver_table": silver_table,
                    "gold_table": gold_table,
                    "silver_rows": silver_rows,
                    "gold_rows": gold_rows,
                }
            )

    return {
        "status": "ok"
        if all(table["status"] in {"ok", "skipped"} for table in tables.values())
        else "failed",
        "tables": tables,
    }


def _build_null_ratio_report(db: Any, table_counts: dict[str, int]) -> dict[str, Any]:
    tables: dict[str, dict[str, Any]] = {}
    for table, row_count in sorted(table_counts.items()):
        columns: dict[str, dict[str, Any]] = {}
        for column in _table_columns(db, table):
            nulls = _null_count(db, table, column)
            columns[column] = {
                "nulls": nulls,
                "rows": row_count,
                "ratio": round(nulls / row_count, 6) if row_count else None,
            }
        tables[table] = {"rows": row_count, "columns": columns}
    return {"status": "reported", "tables": tables}


def _current_table_counts(db: Any) -> dict[str, int]:
    rows = db.fetch(
        """
        SELECT table_name
        FROM duckdb_tables()
        WHERE table_name NOT LIKE 'backup_%'
        ORDER BY table_name
        """
    )
    return {row["table_name"]: _count_rows(db, row["table_name"]) for row in rows}


def _table_columns(db: Any, table: str) -> list[str]:
    rows = db.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'main'
          AND table_name = ?
        ORDER BY ordinal_position
        """,
        [table],
    )
    return [row["column_name"] for row in rows]


def _orphan_count(
    db: Any,
    *,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
) -> int:
    rows = db.fetch(
        f"""
        SELECT COUNT(*) AS orphan_count
        FROM {_quote_identifier(child_table)} child
        LEFT JOIN {_quote_identifier(parent_table)} parent
          ON child.{_quote_identifier(child_column)} = parent.{_quote_identifier(parent_column)}
        WHERE child.{_quote_identifier(child_column)} IS NOT NULL
          AND parent.{_quote_identifier(parent_column)} IS NULL
        """
    )
    return int(rows[0]["orphan_count"])


def _null_count(db: Any, table: str, column: str) -> int:
    rows = db.fetch(
        f"""
        SELECT SUM(CASE WHEN {_quote_identifier(column)} IS NULL THEN 1 ELSE 0 END) AS nulls
        FROM {_quote_identifier(table)}
        """
    )
    return int(rows[0]["nulls"] or 0)


def _count_rows(db: Any, table: str) -> int:
    rows = db.fetch(f"SELECT COUNT(*) AS row_count FROM {_quote_identifier(table)}")
    return int(rows[0]["row_count"])


def _table_exists(db: Any, table: str) -> bool:
    rows = db.fetch(
        "SELECT 1 AS present FROM duckdb_tables() WHERE table_name = ? LIMIT 1",
        [table],
    )
    return bool(rows)


def _json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def _quote_identifier(identifier: str) -> str:
    if '"' in identifier:
        raise WarehouseRuntimeError(f"Invalid SQL identifier: {identifier}")
    return f'"{identifier}"'
