from __future__ import annotations

import unittest
from pathlib import Path


class CompatibilityShimTests(unittest.TestCase):
    def test_runtime_is_thin_compatibility_shim(self) -> None:
        runtime_path = Path(__file__).resolve().parents[2] / "edgar_warehouse" / "runtime.py"
        content = runtime_path.read_text()
        self.assertIn("application.command_router", content)
        self.assertNotIn("def _execute_warehouse", content)
        self.assertNotIn("if command_name", content)

    def test_silver_is_thin_compatibility_shim(self) -> None:
        silver_path = Path(__file__).resolve().parents[2] / "edgar_warehouse" / "silver.py"
        content = silver_path.read_text()
        self.assertIn("silver_store", content)
        self.assertNotIn("class SilverDatabase", content)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS", content)

    def test_gold_is_thin_compatibility_shim(self) -> None:
        gold_path = Path(__file__).resolve().parents[2] / "edgar_warehouse" / "gold.py"
        content = gold_path.read_text()
        self.assertIn("serving.gold_models", content)
        self.assertIn("serving.targets.snowflake", content)
        self.assertNotIn("def build_gold", content)
        self.assertNotIn("pq.write_table", content)
