"""Snowflake serving publishers for Gold outputs."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory
from edgar_warehouse.serving.source_dimensional_export import _write_parquet
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


# The mapping is:
#   <export_name in S3 path>  ←  <build_gold()/iter_gold_tables() table name>
#
# The current serving package is consumed by Snowflake native pull. Existing
# entries are dimension/fact tables for the ownership graph. PR-2 adds 6
# entries for Branch B fundamentals:
#   - 3 passthrough tables (SEC_FINANCIAL_FACT etc.) — keep silver-table
#     snake_case names matching the export bucket prefix structure.
#   - 3 dimensional tables (EARNINGS_RELEASE etc.) — same shape as the
#     existing 8 facts: surrogate fact_key + dim FKs.
GOLD_EXPORT_MAP: dict[str, str] = {
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
    "guidance_facts": "fact_guidance",
    "executive_record": "fact_executive_record",
    "accounting_flag": "fact_accounting_flag",
    # Agent neighborhood evidence (ticket 08)
    "sec_subsidiary_evidence": "sec_subsidiary_evidence",
    "sec_auditor_report_evidence": "sec_auditor_report_evidence",
    "sec_employment_event": "sec_employment_event",
    # Firm Roster completeness cross-check (ticket 03)
    "sec_adv_firm_roster": "sec_adv_firm_roster",
    "sec_adv_private_fund": "sec_adv_private_fund",
    # ERDP-03 Explore calendar (built outside silver gold_refresh path)
    "earnings_calendar": "fact_earnings_calendar",
}

_SOURCE_TO_EXPORT_NAME: dict[str, str] = {
    source_name: export_name for export_name, source_name in GOLD_EXPORT_MAP.items()
}


def write_gold_table_to_serving_export(
    source_name: str,
    table: pa.Table,
    export_root: Any,
    run_id: str,
    business_date: str,
) -> tuple[str, int] | None:
    """Write a single gold table to its serving-export Parquet path, if it
    has an export mapping. Returns (export_name, row_count), or None if
    source_name isn't in GOLD_EXPORT_MAP.

    Extracted from write_gold_to_serving_export so memory-critical callers
    (paired with iter_gold_tables()) can write and discard one table at a
    time instead of writing the whole dict at once.
    """
    export_name = _SOURCE_TO_EXPORT_NAME.get(source_name)
    if export_name is None:
        return None
    export_spec = default_capture_spec_factory().serving_export_table(
        table_path=export_name,
        business_date=business_date,
        run_id=run_id,
    )
    _write_parquet(table, export_root, export_spec.relative_path)
    return export_name, table.num_rows


def write_gold_to_serving_export(
    tables: dict[str, pa.Table],
    export_root: Any,
    run_id: str,
    business_date: str,
) -> dict[str, int]:
    """Write each gold table to its serving-export Parquet path.

    See GOLD_EXPORT_MAP for the export-name/source-name mapping.
    """
    counts: dict[str, int] = {}
    for source_name, table in tables.items():
        result = write_gold_table_to_serving_export(
            source_name, table, export_root, run_id, business_date
        )
        if result is not None:
            export_name, row_count = result
            counts[export_name] = row_count
    return counts


def write_earnings_calendar_to_serving_export(
    table: pa.Table,
    export_root: Any,
    run_id: str,
    business_date: str,
) -> int:
    """Write ERDP-03 EARNINGS_CALENDAR Explore table to serving export path."""
    export_spec = default_capture_spec_factory().serving_export_table(
        table_path="earnings_calendar",
        business_date=business_date,
        run_id=run_id,
    )
    _write_parquet(table, export_root, export_spec.relative_path)
    return table.num_rows


def write_consensus_estimates_to_serving_export(
    table: pa.Table,
    export_root: Any,
    run_id: str,
    business_date: str,
) -> int:
    """Write ERDP-01 CONSENSUS_ESTIMATES Explore table to serving export path."""
    export_spec = default_capture_spec_factory().serving_export_table(
        table_path="consensus_estimates",
        business_date=business_date,
        run_id=run_id,
    )
    _write_parquet(table, export_root, export_spec.relative_path)
    return table.num_rows


def write_transcript_events_to_serving_export(
    table: pa.Table,
    export_root: Any,
    run_id: str,
    business_date: str,
) -> int:
    """Write ERDP-04 TRANSCRIPT_EVENTS Explore table to serving export path."""
    export_spec = default_capture_spec_factory().serving_export_table(
        table_path="transcript_events",
        business_date=business_date,
        run_id=run_id,
    )
    _write_parquet(table, export_root, export_spec.relative_path)
    return table.num_rows


write_ticker_reference_to_snowflake_export = write_ticker_reference_to_serving_export
write_gold_to_snowflake_export = write_gold_to_serving_export
write_earnings_calendar_to_snowflake_export = write_earnings_calendar_to_serving_export
write_consensus_estimates_to_snowflake_export = write_consensus_estimates_to_serving_export
write_transcript_events_to_snowflake_export = write_transcript_events_to_serving_export
