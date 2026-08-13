from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from edgar_warehouse.application.command_context_factory import build_warehouse_context
from edgar_warehouse.application.errors import WarehouseRuntimeError


class CommandContextFactoryTests(unittest.TestCase):
    def test_build_warehouse_context_uses_explicit_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "EDGAR_IDENTITY": "dev@example.com",
                "WAREHOUSE_RUNTIME_MODE": "infrastructure_validation",
                "WAREHOUSE_BRONZE_ROOT": os.path.join(tmp, "bronze"),
                "WAREHOUSE_STORAGE_ROOT": os.path.join(tmp, "warehouse"),
                "WAREHOUSE_SILVER_ROOT": os.path.join(tmp, "silver"),
                "SERVING_EXPORT_ROOT": os.path.join(tmp, "serving"),
                "MDM_DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            }
            with patch.dict(os.environ, env, clear=False):
                context = build_warehouse_context("bootstrap-full")

            self.assertEqual(context.identity, "dev@example.com")
            self.assertTrue(context.bronze_root.root.endswith("bronze"))
            self.assertTrue(context.storage_root.root.endswith("warehouse"))
            self.assertTrue(context.silver_root.root.endswith("silver"))
            self.assertIsNotNone(context.serving_export_root)

    def test_build_warehouse_context_accepts_legacy_snowflake_export_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "EDGAR_IDENTITY": "dev@example.com",
                "WAREHOUSE_RUNTIME_MODE": "infrastructure_validation",
                "WAREHOUSE_BRONZE_ROOT": os.path.join(tmp, "bronze"),
                "WAREHOUSE_STORAGE_ROOT": os.path.join(tmp, "warehouse"),
                "SNOWFLAKE_EXPORT_ROOT": os.path.join(tmp, "snowflake"),
                "MDM_DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            }
            with patch.dict(os.environ, env, clear=False):
                context = build_warehouse_context("bootstrap-full")

            self.assertIsNotNone(context.snowflake_export_root)
            self.assertEqual(context.serving_export_root, context.snowflake_export_root)

    def test_bootstrap_next_uses_serving_export_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "EDGAR_IDENTITY": "dev@example.com",
                "WAREHOUSE_RUNTIME_MODE": "bronze_capture",
                "WAREHOUSE_BRONZE_ROOT": os.path.join(tmp, "bronze"),
                "WAREHOUSE_STORAGE_ROOT": os.path.join(tmp, "warehouse"),
                "SERVING_EXPORT_ROOT": os.path.join(tmp, "serving"),
                "MDM_DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            }
            with patch.dict(os.environ, env, clear=False):
                context = build_warehouse_context("bootstrap-next")

            self.assertIsNotNone(context.snowflake_export_root)
            self.assertTrue(context.snowflake_export_root.root.endswith("serving"))

    def test_build_warehouse_context_requires_distinct_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shared = os.path.join(tmp, "shared")
            env = {
                "EDGAR_IDENTITY": "dev@example.com",
                "WAREHOUSE_RUNTIME_MODE": "infrastructure_validation",
                "WAREHOUSE_BRONZE_ROOT": shared,
                "WAREHOUSE_STORAGE_ROOT": shared,
            }
            with patch.dict(os.environ, env, clear=False):
                with self.assertRaises(WarehouseRuntimeError):
                    build_warehouse_context("daily-incremental")

    def test_silver_landing_export_root_defaults_to_none(self) -> None:
        """Opt-in, default-off: no SILVER_LANDING_EXPORT_ROOT means no landing export,
        for any command -- unlike serving_export_root this isn't gated to a command
        allowlist, so absence alone must be enough to prove the no-op default."""
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "EDGAR_IDENTITY": "dev@example.com",
                "WAREHOUSE_RUNTIME_MODE": "bronze_capture",
                "WAREHOUSE_BRONZE_ROOT": os.path.join(tmp, "bronze"),
                "WAREHOUSE_STORAGE_ROOT": os.path.join(tmp, "warehouse"),
                "MDM_DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            }
            with patch.dict(os.environ, env, clear=False):
                context = build_warehouse_context("bootstrap-batch")

            self.assertIsNone(context.silver_landing_export_root)

    def test_silver_landing_export_root_opts_in_via_env_var(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "EDGAR_IDENTITY": "dev@example.com",
                "WAREHOUSE_RUNTIME_MODE": "bronze_capture",
                "WAREHOUSE_BRONZE_ROOT": os.path.join(tmp, "bronze"),
                "WAREHOUSE_STORAGE_ROOT": os.path.join(tmp, "warehouse"),
                "SILVER_LANDING_EXPORT_ROOT": os.path.join(tmp, "silver-landing"),
                "MDM_DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            }
            with patch.dict(os.environ, env, clear=False):
                context = build_warehouse_context("bootstrap-batch")

            self.assertIsNotNone(context.silver_landing_export_root)
            self.assertTrue(context.silver_landing_export_root.root.endswith("silver-landing"))

    def test_silver_landing_export_root_must_be_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bronze = os.path.join(tmp, "bronze")
            env = {
                "EDGAR_IDENTITY": "dev@example.com",
                "WAREHOUSE_RUNTIME_MODE": "bronze_capture",
                "WAREHOUSE_BRONZE_ROOT": bronze,
                "WAREHOUSE_STORAGE_ROOT": os.path.join(tmp, "warehouse"),
                "SILVER_LANDING_EXPORT_ROOT": bronze,
                "MDM_DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            }
            with patch.dict(os.environ, env, clear=False):
                with self.assertRaises(WarehouseRuntimeError):
                    build_warehouse_context("bootstrap-batch")
