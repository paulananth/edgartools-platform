"""Snowflake serving publishers for Gold outputs."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory
from edgar_warehouse.serving.gold_models import _write_parquet
from edgar_warehouse.serving.targets.base import ServingTarget


class SnowflakeTarget:
    """Serving target that writes Parquet packages consumed by Snowflake native pull."""

    provider_name = "snowflake"

    def write_gold(
        self,
        tables: dict[str, pa.Table],
        export_root: Any,
        *,
        run_id: str,
        business_date: str,
    ) -> dict[str, int]:
        return write_gold_to_serving_export(
            tables,
            export_root,
            run_id=run_id,
            business_date=business_date,
        )

    def write_ticker_reference(
        self,
        table: pa.Table,
        export_root: Any,
        *,
        run_id: str,
        business_date: str,
    ) -> int:
        return write_ticker_reference_to_serving_export(
            table,
            export_root,
            run_id=run_id,
            business_date=business_date,
        )


def default_serving_target() -> ServingTarget:
    return SnowflakeTarget()


def write_ticker_reference_to_serving_export(
    table: pa.Table,
    export_root: Any,
    run_id: str,
    business_date: str,
) -> int:
    export_spec = default_capture_spec_factory().serving_export_table(
        table_path="ticker_reference",
        business_date=business_date,
        run_id=run_id,
    )
    _write_parquet(table, export_root, export_spec.relative_path)
    return table.num_rows


def write_gold_to_serving_export(
    tables: dict[str, pa.Table],
    export_root: Any,
    run_id: str,
    business_date: str,
) -> dict[str, int]:
    """Write each gold table to its serving-export Parquet path.

    The mapping is:
      <export_name in S3 path>  ←  <build_gold() dict key>

    The current serving package is consumed by Snowflake native pull. Existing
    entries are dimension/fact tables for the ownership graph. PR-2 adds 6
    entries for Branch B fundamentals:
      - 3 passthrough tables (SEC_FINANCIAL_FACT etc.) — keep silver-table
        snake_case names matching the export bucket prefix structure.
      - 3 dimensional tables (EARNINGS_RELEASE etc.) — same shape as the
        existing 8 facts: surrogate fact_key + dim FKs.
    """
    export_map = {
        # Existing 9-table ownership/ADV gold
        "company": "dim_company",
        "filing_activity": "fact_filing_activity",
        "ownership_activity": "fact_ownership_transaction",
        "ownership_holdings": "fact_ownership_holding_snapshot",
        "adviser_offices": "fact_adv_office",
        "adviser_disclosures": "fact_adv_disclosure",
        "private_funds": "fact_adv_private_fund",
        "filing_detail": "dim_filing",
        # Branch B fundamentals (PR-2) — Q1-C passthrough split.
        # Passthrough tables retain SEC_ prefix in their S3 path / Snowflake
        # source table names (per PR-1 sources.yml).
        "sec_financial_fact": "sec_financial_fact",
        "sec_thirteenf_holding": "sec_thirteenf_holding",
        "sec_financial_derived": "sec_financial_derived",
        # Dimensional tables drop SEC_ prefix (per PR-1 source naming).
        "earnings_release": "fact_earnings_release",
        "executive_record": "fact_executive_record",
        "accounting_flag": "fact_accounting_flag",
        # Agent neighborhood evidence (ticket 08)
        "sec_subsidiary_evidence": "sec_subsidiary_evidence",
        "sec_auditor_report_evidence": "sec_auditor_report_evidence",
        "sec_employment_event": "sec_employment_event",
    }
    counts: dict[str, int] = {}
    capture_specs = default_capture_spec_factory()
    for export_name, source_name in export_map.items():
        table = tables.get(source_name)
        if table is None:
            continue
        export_spec = capture_specs.serving_export_table(
            table_path=export_name,
            business_date=business_date,
            run_id=run_id,
        )
        _write_parquet(table, export_root, export_spec.relative_path)
        counts[export_name] = table.num_rows
    return counts


write_ticker_reference_to_snowflake_export = write_ticker_reference_to_serving_export
write_gold_to_snowflake_export = write_gold_to_serving_export
