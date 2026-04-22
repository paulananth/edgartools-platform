"""Snowflake serving publishers for Gold outputs."""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory
from edgar_warehouse.serving.gold_models import _write_parquet


def write_ticker_reference_to_snowflake_export(
    table: pa.Table,
    export_root: Any,
    run_id: str,
    business_date: str,
) -> int:
    export_spec = default_capture_spec_factory().snowflake_export_table(
        table_path="ticker_reference",
        business_date=business_date,
        run_id=run_id,
    )
    _write_parquet(table, export_root, export_spec.relative_path)
    return table.num_rows


def write_gold_to_snowflake_export(
    tables: dict[str, pa.Table],
    export_root: Any,
    run_id: str,
    business_date: str,
) -> dict[str, int]:
    export_map = {
        "company": "dim_company",
        "filing_activity": "fact_filing_activity",
        "ownership_activity": "fact_ownership_transaction",
        "ownership_holdings": "fact_ownership_holding_snapshot",
        "adviser_offices": "fact_adv_office",
        "adviser_disclosures": "fact_adv_disclosure",
        "private_funds": "fact_adv_private_fund",
        "filing_detail": "dim_filing",
    }
    counts: dict[str, int] = {}
    capture_specs = default_capture_spec_factory()
    for export_name, source_name in export_map.items():
        table = tables.get(source_name)
        if table is None:
            continue
        export_spec = capture_specs.snowflake_export_table(
            table_path=export_name,
            business_date=business_date,
            run_id=run_id,
        )
        _write_parquet(table, export_root, export_spec.relative_path)
        counts[export_name] = table.num_rows
    return counts
