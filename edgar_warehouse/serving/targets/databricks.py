"""Databricks serving publishers for Gold outputs.

The first Databricks migration phase uses the same Parquet export layout as the
Snowflake native-pull path. Unity Catalog external tables or Databricks jobs can
register/read these files from ADLS without changing the warehouse runtime.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory
from edgar_warehouse.serving.gold_models import _write_parquet

_GOLD_EXPORT_MAP = {
    "company": "dim_company",
    "filing_activity": "fact_filing_activity",
    "ownership_activity": "fact_ownership_transaction",
    "ownership_holdings": "fact_ownership_holding_snapshot",
    "adviser_offices": "fact_adv_office",
    "adviser_disclosures": "fact_adv_disclosure",
    "private_funds": "fact_adv_private_fund",
    "filing_detail": "dim_filing",
}


def write_ticker_reference_to_databricks_export(
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


def write_gold_to_databricks_export(
    tables: dict[str, pa.Table],
    export_root: Any,
    run_id: str,
    business_date: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    capture_specs = default_capture_spec_factory()
    for export_name, source_name in _GOLD_EXPORT_MAP.items():
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
