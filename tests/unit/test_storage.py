from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import StorageLocation, sanitize_filename, sanitize_relative_path


class StorageTests(unittest.TestCase):
    def test_sanitize_relative_path_rejects_traversal(self) -> None:
        with self.assertRaises(WarehouseRuntimeError):
            sanitize_relative_path("../secrets.txt")

    def test_sanitize_filename_strips_directories(self) -> None:
        self.assertEqual(sanitize_filename("nested/path/document.htm"), "document.htm")

    def test_storage_location_writes_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            location = StorageLocation(tmp)
            destination = location.write_json("runs/test/manifest.json", {"ok": True})
            payload = json.loads((Path(tmp) / "runs" / "test" / "manifest.json").read_text())
            self.assertEqual(payload, {"ok": True})
            self.assertTrue(destination.endswith("runs/test/manifest.json"))
