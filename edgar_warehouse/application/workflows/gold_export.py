"""Gold-export helpers."""

from __future__ import annotations

from typing import Any


def build_gold(*args: Any, **kwargs: Any):
    from edgar_warehouse.gold import build_gold as _build_gold

    return _build_gold(*args, **kwargs)


def build_ticker_reference_table(*args: Any, **kwargs: Any):
    from edgar_warehouse.gold import build_ticker_reference_table as _build_ticker_reference_table

    return _build_ticker_reference_table(*args, **kwargs)


def write_gold_to_snowflake_export(*args: Any, **kwargs: Any):
    from edgar_warehouse.gold import write_gold_to_snowflake_export as _write_gold_to_snowflake_export

    return _write_gold_to_snowflake_export(*args, **kwargs)


def write_gold_to_storage(*args: Any, **kwargs: Any):
    from edgar_warehouse.gold import write_gold_to_storage as _write_gold_to_storage

    return _write_gold_to_storage(*args, **kwargs)


def write_ticker_reference_to_snowflake_export(*args: Any, **kwargs: Any):
    from edgar_warehouse.gold import (
        write_ticker_reference_to_snowflake_export as _write_ticker_reference_to_snowflake_export,
    )

    return _write_ticker_reference_to_snowflake_export(*args, **kwargs)
