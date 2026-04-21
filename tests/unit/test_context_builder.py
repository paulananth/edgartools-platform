from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from edgar_warehouse.application.context_builder import build_warehouse_context
from edgar_warehouse.application.errors import WarehouseRuntimeError


class ContextBuilderTests(unittest.TestCase):
    def test_build_warehouse_context_uses_explicit_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "EDGAR_IDENTITY": "dev@example.com",
                "WAREHOUSE_RUNTIME_MODE": "infrastructure_validation",
                "WAREHOUSE_BRONZE_ROOT": os.path.join(tmp, "bronze"),
                "WAREHOUSE_STORAGE_ROOT": os.path.join(tmp, "warehouse"),
                "WAREHOUSE_SILVER_ROOT": os.path.join(tmp, "silver"),
                "SNOWFLAKE_EXPORT_ROOT": os.path.join(tmp, "snowflake"),
            }
            with patch.dict(os.environ, env, clear=False):
                context = build_warehouse_context("bootstrap-full")

            self.assertEqual(context.identity, "dev@example.com")
            self.assertTrue(context.bronze_root.root.endswith("bronze"))
            self.assertTrue(context.storage_root.root.endswith("warehouse"))
            self.assertTrue(context.silver_root.root.endswith("silver"))
            self.assertIsNotNone(context.snowflake_export_root)

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
