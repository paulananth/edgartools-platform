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
        cli = importlib.import_module("edgar_warehouse.cli")
        commands = importlib.import_module("edgar_warehouse.application.commands")
        parser = cli.build_parser()
        subparsers_action = next(
            action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
        )
        warehouse_cli_commands = set(subparsers_action.choices) - {"mdm"}
        self.assertEqual(
            set(commands.COMMAND_REGISTRY),
            warehouse_cli_commands,
        )

    def test_all_commands_have_planned_manifest_paths(self) -> None:
        """Every CLI command must have a case in planned_manifest_paths.

        5-why root cause: gold-refresh and seed-silver-batches were missing,
        causing exit=2 after successfully completing all work because
        _execute_warehouse_bronze_capture calls _planned_writes unconditionally.
        """
        cli = importlib.import_module("edgar_warehouse.cli")
        catalog = importlib.import_module("edgar_warehouse.infrastructure.dataset_path_catalog")
        errors_module = importlib.import_module("edgar_warehouse.application.errors")

        parser = cli.build_parser()
        subparsers_action = next(
            action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
        )
        all_commands = set(subparsers_action.choices) - {"mdm"}

        resolver = catalog.default_path_resolver()
        missing = []
        for command in sorted(all_commands):
            try:
                resolver.planned_manifest_paths(
                    command_name=command,
                    command_path=command,
                    run_id="test-run",
                    scope={},
                )
            except errors_module.WarehouseRuntimeError:
                missing.append(command)
            except Exception:
                pass  # other errors are fine — only WarehouseRuntimeError("Unsupported") matters

        self.assertEqual(
            missing,
            [],
            f"Commands missing from planned_manifest_paths (will exit=2 after completing work): {missing}",
        )
