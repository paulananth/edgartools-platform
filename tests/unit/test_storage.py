from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import (
    StorageLocation,
    sanitize_filename,
    sanitize_relative_path,
)


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
            self.assertTrue(destination.replace("\\", "/").endswith("runs/test/manifest.json"))

    def test_storage_location_accepts_s3_uri_scheme(self) -> None:
        self.assertTrue(StorageLocation("s3://bucket/warehouse/bronze").is_remote)

    def test_storage_location_rejects_unsupported_remote_protocol(self) -> None:
        with self.assertRaises(WarehouseRuntimeError):
            StorageLocation("gs://bucket/path")

    def test_storage_location_writes_to_remote_filesystem(self) -> None:
        handle = Mock()
        handle.__enter__ = Mock(return_value=handle)
        handle.__exit__ = Mock(return_value=None)
        fs = Mock()
        fs.open.return_value = handle

        fsspec = types.SimpleNamespace(filesystem=Mock(return_value=fs))
        with patch.dict(sys.modules, {"fsspec": fsspec}):
            destination = StorageLocation("s3://bucket/warehouse").write_text(
                "runs/test/manifest.json", "{}"
            )

        fsspec.filesystem.assert_called_once_with("s3")
        fs.open.assert_called_once_with(destination, "wb")
        handle.write.assert_called_once_with(b"{}")
