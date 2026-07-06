from __future__ import annotations

import importlib.util

import pyarrow as pa


class _FakeStorage:
    def __init__(self) -> None:
        self.writes: dict[str, int] = {}

    def write_bytes(self, relative_path: str, payload: bytes) -> str:
        self.writes[relative_path] = len(payload)
        return relative_path


def test_snowflake_target_implements_serving_target_protocol() -> None:
    from edgar_warehouse.serving.targets.base import ServingTarget
    from edgar_warehouse.serving.targets.snowflake import SnowflakeTarget

    target = SnowflakeTarget()

    assert isinstance(target, ServingTarget)


def test_snowflake_target_writes_gold_tables_via_serving_interface() -> None:
    from edgar_warehouse.serving.targets.snowflake import SnowflakeTarget

    storage = _FakeStorage()
    table = pa.table({"company_key": ["company-1"], "cik": [320193]})

    counts = SnowflakeTarget().write_gold(
        {"dim_company": table},
        storage,
        run_id="run-7",
        business_date="2026-07-06",
    )

    assert counts == {"company": 1}
    assert storage.writes.keys() == {
        "company/business_date=2026-07-06/run_id=run-7/company.parquet"
    }


def test_serving_named_functions_write_snowflake_export_paths() -> None:
    from edgar_warehouse.serving.targets.snowflake import (
        write_gold_to_serving_export,
        write_ticker_reference_to_serving_export,
    )

    storage = _FakeStorage()
    gold_table = pa.table({"company_key": ["company-1"], "cik": [320193]})
    ticker_table = pa.table({"cik": [320193], "ticker": ["AAPL"], "exchange": ["Nasdaq"]})

    counts = write_gold_to_serving_export(
        {"dim_company": gold_table},
        storage,
        run_id="run-8",
        business_date="2026-07-06",
    )
    ticker_count = write_ticker_reference_to_serving_export(
        ticker_table,
        storage,
        run_id="run-8",
        business_date="2026-07-06",
    )

    assert counts == {"company": 1}
    assert ticker_count == 1
    assert storage.writes.keys() == {
        "company/business_date=2026-07-06/run_id=run-8/company.parquet",
        "ticker_reference/business_date=2026-07-06/run_id=run-8/ticker_reference.parquet",
    }


def test_serving_targets_do_not_recreate_databricks_module() -> None:
    assert importlib.util.find_spec("edgar_warehouse.serving.targets.databricks") is None
