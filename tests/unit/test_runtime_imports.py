from __future__ import annotations

import importlib
import sys
import types
import unittest
from unittest.mock import patch


class RuntimeImportTests(unittest.TestCase):
    def test_runtime_imports_without_optional_warehouse_dependencies(self) -> None:
        runtime = importlib.import_module("edgar_warehouse.runtime")
        self.assertTrue(callable(runtime.run_command))
        self.assertTrue(callable(runtime.run_seed_universe_command))

    def test_silver_and_gold_shims_import_and_reexport_expected_symbols(self) -> None:
        fake_duckdb = types.ModuleType("duckdb")

        fake_pyarrow = types.ModuleType("pyarrow")
        fake_pyarrow.Table = type("Table", (), {})
        fake_pyarrow.BufferOutputStream = type("BufferOutputStream", (), {})
        fake_pyarrow.schema = lambda fields: ("schema", fields)
        fake_pyarrow.field = lambda name, value: (name, value)
        fake_pyarrow.int64 = lambda: "int64"
        fake_pyarrow.int32 = lambda: "int32"
        fake_pyarrow.int16 = lambda: "int16"
        fake_pyarrow.string = lambda: "string"
        fake_pyarrow.date32 = lambda: "date32"
        fake_pyarrow.bool_ = lambda: "bool"
        fake_pyarrow.float64 = lambda: "float64"

        fake_parquet = types.ModuleType("pyarrow.parquet")
        fake_parquet.write_table = lambda table, buffer: None
        fake_pyarrow.parquet = fake_parquet

        with patch.dict(
            sys.modules,
            {
                "duckdb": fake_duckdb,
                "pyarrow": fake_pyarrow,
                "pyarrow.parquet": fake_parquet,
            },
            clear=False,
        ):
            for module_name in [
                "edgar_warehouse.silver_store",
                "edgar_warehouse.silver",
                "edgar_warehouse.serving.gold_models",
                "edgar_warehouse.serving.targets.databricks",
                "edgar_warehouse.serving.targets.snowflake",
                "edgar_warehouse.gold",
            ]:
                sys.modules.pop(module_name, None)

            silver = importlib.import_module("edgar_warehouse.silver")
            gold = importlib.import_module("edgar_warehouse.gold")

        self.assertTrue(hasattr(silver, "SilverDatabase"))
        self.assertTrue(callable(gold.build_gold))
        self.assertTrue(callable(gold.write_gold_to_databricks_export))
        self.assertTrue(callable(gold.write_gold_to_snowflake_export))

    def test_command_registry_contains_all_cli_commands(self) -> None:
        commands = importlib.import_module("edgar_warehouse.application.commands")
        self.assertEqual(
            set(commands.COMMAND_REGISTRY),
            {
                "bootstrap-full",
                "bootstrap-recent-10",
                "bootstrap-batch",
                "daily-incremental",
                "load-daily-form-index-for-date",
                "catch-up-daily-form-index",
                "targeted-resync",
                "full-reconcile",
                "seed-universe",
            },
        )
