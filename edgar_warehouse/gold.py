"""Compatibility shim for the warehouse gold-serving public surface."""

from __future__ import annotations

from edgar_warehouse.serving.gold_models import (
    build_gold,
    build_ticker_reference_table,
    write_gold_to_storage,
)
from edgar_warehouse.serving.targets.databricks import (
    write_gold_to_databricks_export,
    write_ticker_reference_to_databricks_export,
)
from edgar_warehouse.serving.targets.snowflake import (
    write_gold_to_snowflake_export,
    write_ticker_reference_to_snowflake_export,
)

__all__ = [
    "build_gold",
    "build_ticker_reference_table",
    "write_gold_to_databricks_export",
    "write_gold_to_snowflake_export",
    "write_gold_to_storage",
    "write_ticker_reference_to_databricks_export",
    "write_ticker_reference_to_snowflake_export",
]
