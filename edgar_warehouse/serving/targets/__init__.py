"""Serving target publishers for Gold outputs."""

from edgar_warehouse.serving.targets.base import ServingTarget
from edgar_warehouse.serving.targets.snowflake import (
    SnowflakeTarget,
    default_serving_target,
    write_gold_to_serving_export,
    write_gold_to_snowflake_export,
    write_ticker_reference_to_serving_export,
    write_ticker_reference_to_snowflake_export,
)

__all__ = [
    "ServingTarget",
    "SnowflakeTarget",
    "default_serving_target",
    "write_gold_to_serving_export",
    "write_gold_to_snowflake_export",
    "write_ticker_reference_to_serving_export",
    "write_ticker_reference_to_snowflake_export",
]
