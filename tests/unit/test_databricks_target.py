from __future__ import annotations

import unittest
import importlib
import sys
import types
from unittest.mock import patch


class _Table:
    def __init__(self, rows: int) -> None:
        self.num_rows = rows


def _load_databricks_target():
    fake_pyarrow = types.ModuleType("pyarrow")
    fake_pyarrow.Table = type("Table", (), {})
    fake_gold_models = types.ModuleType("edgar_warehouse.serving.gold_models")
    fake_gold_models._write_parquet = lambda table, root, relative_path: None
    sys.modules.pop("edgar_warehouse.serving.targets.databricks", None)
    with patch.dict(
        sys.modules,
        {
            "pyarrow": fake_pyarrow,
            "edgar_warehouse.serving.gold_models": fake_gold_models,
        },
        clear=False,
    ):
        return importlib.import_module("edgar_warehouse.serving.targets.databricks")


class DatabricksTargetTests(unittest.TestCase):
    def test_write_gold_to_databricks_export_uses_existing_parquet_export_layout(self) -> None:
        databricks = _load_databricks_target()
        writes: list[str] = []

        with patch.object(
            databricks,
            "_write_parquet",
            side_effect=lambda _table, _root, relative_path: writes.append(relative_path),
        ):
            counts = databricks.write_gold_to_databricks_export(
                {
                    "dim_company": _Table(2),
                    "fact_filing_activity": _Table(3),
                },
                export_root=object(),
                run_id="run-123",
                business_date="2026-04-22",
            )

        self.assertEqual(counts, {"company": 2, "filing_activity": 3})
        self.assertEqual(
            writes,
            [
                "company/business_date=2026-04-22/run_id=run-123/company.parquet",
                "filing_activity/business_date=2026-04-22/run_id=run-123/filing_activity.parquet",
            ],
        )

    def test_write_ticker_reference_to_databricks_export_returns_row_count(self) -> None:
        databricks = _load_databricks_target()
        writes: list[str] = []

        with patch.object(
            databricks,
            "_write_parquet",
            side_effect=lambda _table, _root, relative_path: writes.append(relative_path),
        ):
            row_count = databricks.write_ticker_reference_to_databricks_export(
                _Table(4),
                export_root=object(),
                run_id="run-123",
                business_date="2026-04-22",
            )

        self.assertEqual(row_count, 4)
        self.assertEqual(
            writes,
            ["ticker_reference/business_date=2026-04-22/run_id=run-123/ticker_reference.parquet"],
        )


if __name__ == "__main__":
    unittest.main()
