"""Gold-serving helpers."""

from __future__ import annotations

from typing import Any


def build_source_export(*args: Any, **kwargs: Any):
    from edgar_warehouse.serving.source_dimensional_export import build_source_export as _build_source_export

    return _build_source_export(*args, **kwargs)


def build_ticker_reference_table(*args: Any, **kwargs: Any):
    from edgar_warehouse.serving.source_dimensional_export import (
        build_ticker_reference_table as _build_ticker_reference_table,
    )

    return _build_ticker_reference_table(*args, **kwargs)


def write_source_dimensional_export_to_snowflake(*args: Any, **kwargs: Any):
    from edgar_warehouse.serving.targets.snowflake import (
        write_source_dimensional_export_to_snowflake as _write_source_dimensional_export_to_snowflake,
    )

    return _write_source_dimensional_export_to_snowflake(*args, **kwargs)


def write_source_dimensional_export_to_serving(*args: Any, **kwargs: Any):
    from edgar_warehouse.serving.targets.snowflake import (
        write_source_dimensional_export_to_serving as _write_source_dimensional_export_to_serving,
    )

    return _write_source_dimensional_export_to_serving(*args, **kwargs)


def write_source_export_to_storage(*args: Any, **kwargs: Any):
    from edgar_warehouse.serving.source_dimensional_export import write_source_export_to_storage as _write_source_export_to_storage

    return _write_source_export_to_storage(*args, **kwargs)


def write_ticker_reference_to_snowflake_export(*args: Any, **kwargs: Any):
    from edgar_warehouse.serving.targets.snowflake import (
        write_ticker_reference_to_snowflake_export as _write_ticker_reference_to_snowflake_export,
    )

    return _write_ticker_reference_to_snowflake_export(*args, **kwargs)


def write_ticker_reference_to_serving_export(*args: Any, **kwargs: Any):
    from edgar_warehouse.serving.targets.snowflake import (
        write_ticker_reference_to_serving_export as _write_ticker_reference_to_serving_export,
    )

    return _write_ticker_reference_to_serving_export(*args, **kwargs)
