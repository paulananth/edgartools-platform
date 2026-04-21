from __future__ import annotations

import importlib
import unittest


class RuntimeImportTests(unittest.TestCase):
    def test_runtime_imports_without_optional_warehouse_dependencies(self) -> None:
        runtime = importlib.import_module("edgar_warehouse.runtime")
        self.assertTrue(callable(runtime.run_command))

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
