"""Compatibility shim for the warehouse gold-serving public surface."""

from __future__ import annotations

from edgar_warehouse.serving.source_dimensional_export import (
    build_source_export,
    build_ticker_reference_table,
    write_source_export_to_storage,
    write_source_export_to_storage_manifest,
)
from edgar_warehouse.serving.targets.snowflake import (
    write_source_dimensional_export_to_serving,
    write_source_dimensional_export_to_snowflake,
    write_ticker_reference_to_serving_export,
    write_ticker_reference_to_snowflake_export,
)

__all__ = [
    "build_source_export",
    "build_ticker_reference_table",
    "write_source_dimensional_export_to_serving",
    "write_source_dimensional_export_to_snowflake",
    "write_source_export_to_storage",
    "write_source_export_to_storage_manifest",
    "write_ticker_reference_to_serving_export",
    "write_ticker_reference_to_snowflake_export",
]
