from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.sec_client import SecEndpointConfig, _SEC_RATE_LIMITER, _validate_sec_url, download_sec_bytes


class _FakeResponse:
    status_code = 200
    url = "https://data.sec.gov/submissions/CIK0000000001.json"
    content = b'{"ok":true}'

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str) -> _FakeResponse:
        return _FakeResponse()




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

    def test_download_sec_bytes_logs_each_sec_pull(self) -> None:
        stderr = io.StringIO()
        with patch("httpx.Client", _FakeClient), contextlib.redirect_stderr(stderr):
            payload = download_sec_bytes(
                "https://data.sec.gov/submissions/CIK0000000001.json",
                "edgartools-platform test@example.com",
            )

        self.assertEqual(payload, b'{"ok":true}')
        events = [json.loads(line) for line in stderr.getvalue().splitlines()]
        self.assertEqual([event["event"] for event in events], ["sec_pull_started", "sec_pull_completed"])
        self.assertEqual(events[1]["bytes"], 11)
        self.assertEqual(events[1]["status_code"], 200)

    def test_rate_limiter_called_once_per_request(self) -> None:
        import httpx

        mock_try_acquire = MagicMock(return_value=True)
        with patch.object(_SEC_RATE_LIMITER, "try_acquire", mock_try_acquire):
            # Success case: one logical request → one token acquisition.
            with patch("httpx.Client", _FakeClient), contextlib.redirect_stderr(io.StringIO()):
                download_sec_bytes(
                    "https://data.sec.gov/submissions/CIK0000000001.json",
                    "edgartools-platform test@example.com",
                )
            self.assertEqual(mock_try_acquire.call_count, 1)

        mock_try_acquire.reset_mock()

        # Retry case: first get() raises httpx.RequestError, second succeeds.
        # Use a shared mock instance so state persists across the two loop iterations
        # (each iteration enters a new httpx.Client context).
        fake_client_instance = MagicMock()
        fake_client_instance.__enter__ = MagicMock(return_value=fake_client_instance)
        fake_client_instance.__exit__ = MagicMock(return_value=None)
        fake_client_instance.get = MagicMock(
            side_effect=[httpx.RequestError("transient"), _FakeResponse()]
        )
        MockClient = MagicMock(return_value=fake_client_instance)

        with patch.object(_SEC_RATE_LIMITER, "try_acquire", mock_try_acquire):
            with patch("httpx.Client", MockClient), patch("time.sleep"), contextlib.redirect_stderr(io.StringIO()):
                download_sec_bytes(
                    "https://data.sec.gov/submissions/CIK0000000001.json",
                    "edgartools-platform test@example.com",
                )
            # Token consumed once per logical request, not once per retry.
            self.assertEqual(mock_try_acquire.call_count, 1)
