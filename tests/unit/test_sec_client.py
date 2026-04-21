from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.sec_client import SecEndpointConfig, _validate_sec_url


class SecClientTests(unittest.TestCase):
    def test_sec_endpoint_config_blocks_prod_overrides(self) -> None:
        env = {
            "WAREHOUSE_ENVIRONMENT": "prod",
            "EDGAR_BASE_URL": "https://mirror.example.com",
            "EDGAR_DATA_URL": "https://data.sec.gov",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(WarehouseRuntimeError):
                SecEndpointConfig.from_env()

    def test_validate_sec_url_rejects_non_allowlisted_host(self) -> None:
        with self.assertRaises(WarehouseRuntimeError):
            _validate_sec_url("https://example.com/path")
