from __future__ import annotations

import unittest
from pathlib import Path


class RuntimeShimTests(unittest.TestCase):
    def test_runtime_is_thin_compatibility_shim(self) -> None:
        runtime_path = Path(__file__).resolve().parents[2] / "edgar_warehouse" / "runtime.py"
        content = runtime_path.read_text()
        self.assertIn("application.runtime_facade", content)
        self.assertNotIn("def _execute_warehouse", content)
        self.assertNotIn("if command_name", content)
