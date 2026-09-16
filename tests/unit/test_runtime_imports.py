from __future__ import annotations

import importlib
import unittest


class RuntimeImportTests(unittest.TestCase):
    def test_runtime_imports_without_optional_warehouse_dependencies(self) -> None:
        runtime = importlib.import_module("edgar_warehouse.runtime")
        self.assertTrue(callable(runtime.run_command))
        self.assertTrue(callable(runtime.run_seed_universe_command))

    def test_command_registry_contains_all_cli_commands(self) -> None:
        cli = importlib.import_module("edgar_warehouse.cli")
        commands = importlib.import_module("edgar_warehouse.application.commands")
        parser = cli.build_parser()
        subparsers_action = next(
            action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
        )
        # gold-verify-live (like mdm) bypasses the warehouse orchestrator entirely --
        # it's a standalone direct-Snowflake row-count check (edgar_warehouse.serving.
        # gold_verify), never registered in COMMAND_REGISTRY. resolve-snowflake-env is
        # the same shape: a standalone credential resolver, never registered either.
        # compare-filing-artifact-capture (Ticket 51) is observe-only Decision 2
        # snapshot compare, same exclusion.
        warehouse_cli_commands = set(subparsers_action.choices) - {
            "mdm",
            "gold-verify-live",
            "resolve-snowflake-env",
            "reconcile-decision-watermark",
            "compare-filing-artifact-capture",
        }
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
        # gold-verify-live never calls _planned_writes -- it doesn't go through
        # _execute_warehouse_bronze_capture at all (see the skip comment below).
        # resolve-snowflake-env and compare-filing-artifact-capture are the same shape.
        all_commands = set(subparsers_action.choices) - {
            "mdm",
            "gold-verify-live",
            "resolve-snowflake-env",
            "reconcile-decision-watermark",
            "compare-filing-artifact-capture",
        }

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

    def test_all_commands_have_resolve_scope(self) -> None:
        """Every CLI command must have a case in _resolve_scope.

        5-why root cause: seed-silver-batches was missing from _resolve_scope,
        causing 'Unsupported warehouse command' at runtime despite being registered
        in COMMAND_REGISTRY and having a planned_manifest_paths entry.
        """
        cli = importlib.import_module("edgar_warehouse.cli")
        orchestrator = importlib.import_module("edgar_warehouse.application.warehouse_orchestrator")
        errors_module = importlib.import_module("edgar_warehouse.application.errors")

        parser = cli.build_parser()
        subparsers_action = next(
            action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
        )
        # Commands that legitimately bypass _resolve_scope:
        # - mdm delegates elsewhere
        # - gold-verify-live is a standalone direct-Snowflake row-count check
        #   (edgar_warehouse.serving.gold_verify) -- never touches the warehouse
        #   orchestrator, bronze/silver roots, or manifest machinery at all
        # - resolve-snowflake-env is a standalone credential resolver, same shape
        # - compare-filing-artifact-capture is Ticket 51 observe-only snapshot
        #   compare (Ticket 10 Decision 2), never goes through the orchestrator
        skip = {
            "mdm",
            "gold-verify-live",
            "resolve-snowflake-env",
            "reconcile-decision-watermark",
            "compare-filing-artifact-capture",
        }
        all_commands = set(subparsers_action.choices) - skip

        missing = []
        for command in sorted(all_commands):
            try:
                orchestrator._resolve_scope(
                    command_name=command,
                    arguments={},
                    now=__import__("datetime").datetime(2024, 1, 1),
                )
            except errors_module.WarehouseRuntimeError as e:
                if "Unsupported warehouse command" in str(e):
                    missing.append(command)
            except Exception:
                pass  # other errors are fine — most commands raise on empty arguments

        self.assertEqual(
            missing,
            [],
            f"Commands missing from _resolve_scope (will fail at runtime with 'Unsupported'): {missing}",
        )
