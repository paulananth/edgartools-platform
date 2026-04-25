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

    def test_storage_location_accepts_azure_uri_schemes(self) -> None:
        for root in [
            "abfs://bronze@acct.dfs.core.windows.net/warehouse/bronze",
            "abfss://warehouse@acct.dfs.core.windows.net/warehouse",
            "az://serving/warehouse/serving_exports",
            "https://acct.blob.core.windows.net/serving/warehouse/serving_exports",
            "https://acct.dfs.core.windows.net/warehouse/bronze",
        ]:
            self.assertTrue(StorageLocation(root).is_remote)

    def test_storage_location_rejects_unsupported_remote_protocol(self) -> None:
        with self.assertRaises(WarehouseRuntimeError):
            StorageLocation("gs://bucket/path")

    def test_azure_storage_write_passes_account_name_and_credential(self) -> None:
        handle = Mock()
        handle.__enter__ = Mock(return_value=handle)
        handle.__exit__ = Mock(return_value=None)
        fs = Mock()
        fs.open.return_value = handle
        credential = object()

        fsspec = types.SimpleNamespace(filesystem=Mock(return_value=fs))
        with (
            patch.dict(sys.modules, {"fsspec": fsspec}),
            patch("edgar_warehouse.infrastructure.object_storage._default_azure_credential", return_value=credential),
        ):
            destination = StorageLocation(
                "abfss://warehouse@acct.dfs.core.windows.net/warehouse"
            ).write_text("runs/test/manifest.json", "{}")

        fsspec.filesystem.assert_called_once_with("abfss", account_name="acct", credential=credential)
        fs.open.assert_called_once_with(destination, "wb")
        handle.write.assert_called_once_with(b"{}")
