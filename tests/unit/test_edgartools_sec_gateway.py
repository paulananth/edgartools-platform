"""Ticket 07 — edgartools gateway for catalogs and companyfacts."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import Mock, patch

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure import edgartools_sec_gateway as gateway


def _parse_debug_events(stderr_text: str) -> list[dict]:
    events = []
    for line in stderr_text.splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events


class GatewayRegistryTests(unittest.TestCase):
    def test_cutover_classes_include_catalogs_facts_and_filings(self) -> None:
        for name in (
            "filing_document",
            "company_tickers",
            "company_tickers_exchange",
            "submissions_main",
            "submissions_pagination",
            "daily_index",
            "companyfacts",
        ):
            self.assertTrue(gateway.is_edgartools_gateway_class(name), name)

    def test_non_edgartools_sources_are_explicit_and_not_claimed(self) -> None:
        self.assertTrue(gateway.is_non_edgartools_source("iapd_adv_bulk"))
        self.assertFalse(gateway.is_edgartools_gateway_class("iapd_adv_bulk"))
        self.assertTrue(gateway.is_non_edgartools_source("pcaob_auditorsearch_bulk"))
        # Registry sets must be disjoint
        overlap = (
            gateway.EDGARTOOLS_GATEWAY_OBJECT_CLASSES
            & gateway.NON_EDGARTOOLS_OBJECT_CLASSES
        )
        self.assertEqual(overlap, frozenset())

    def test_gateway_marker_is_edgartools(self) -> None:
        self.assertEqual(gateway.CATALOG_AND_FACTS_NETWORK_GATEWAY, "edgartools")


class GatewayDownloadTests(unittest.TestCase):
    def test_download_bytes_uses_edgartools_not_sec_client(self) -> None:
        download_file = Mock(return_value=b'{"ok": true}')
        with patch(
            "edgar_warehouse.infrastructure.sec_client.download_sec_bytes",
            side_effect=AssertionError("parallel sec_client must not be used"),
        ):
            payload = gateway.download_bytes(
                "https://www.sec.gov/files/company_tickers.json",
                "Tester test@example.com",
                download_file_fn=download_file,
            )
        download_file.assert_called_once()
        self.assertEqual(payload, b'{"ok": true}')

    def test_download_bytes_encodes_text_response(self) -> None:
        download_file = Mock(return_value="form.idx line")
        payload = gateway.download_bytes(
            "https://www.sec.gov/Archives/edgar/daily-index/form.idx",
            "Tester test@example.com",
            download_file_fn=download_file,
        )
        self.assertEqual(payload, b"form.idx line")

    def test_fetch_companyfacts_json_uses_edgartools_url_and_http(self) -> None:
        download_json = Mock(return_value={"cik": 320193, "facts": {}})
        with patch.object(gateway, "ensure_identity") as identity:
            result = gateway.fetch_companyfacts_json(
                320193,
                "Tester test@example.com",
                download_json_fn=download_json,
            )
        identity.assert_called_once_with("Tester test@example.com")
        download_json.assert_called_once()
        url = download_json.call_args[0][0]
        self.assertIn("companyfacts", url)
        self.assertIn("CIK0000320193", url)
        self.assertEqual(result["cik"], 320193)

    def test_empty_download_fails_closed(self) -> None:
        with self.assertRaises(WarehouseRuntimeError):
            gateway.download_bytes(
                "https://www.sec.gov/x",
                "Tester test@example.com",
                download_file_fn=Mock(return_value=None),
            )

    def test_non_sec_host_is_rejected(self) -> None:
        with self.assertRaises(WarehouseRuntimeError):
            gateway.download_bytes(
                "https://evil.example/steal",
                "Tester test@example.com",
                download_file_fn=Mock(side_effect=AssertionError("must not fetch")),
            )


class OrchestratorRoutesThroughGatewayTests(unittest.TestCase):
    def test_download_sec_bytes_shim_uses_gateway(self) -> None:
        from edgar_warehouse.application import warehouse_orchestrator as wo

        # Bound at import as _gateway_download_bytes — patch the orchestrator symbol.
        with patch.object(
            wo, "_gateway_download_bytes", return_value=b"via-gateway"
        ) as gw:
            with patch(
                "edgar_warehouse.infrastructure.sec_client.download_sec_bytes",
                side_effect=AssertionError("sec_client parallel path"),
            ):
                out = wo._download_sec_bytes(
                    "https://data.sec.gov/submissions/CIK0000320193.json",
                    "Tester test@example.com",
                )
        gw.assert_called_once()
        self.assertEqual(out, b"via-gateway")

class EntityFactsUsesGatewayTests(unittest.TestCase):
    def test_entity_facts_network_path_uses_gateway_not_sec_client(self) -> None:
        from edgar_warehouse.application.workflows import fundamentals_ingest as fi

        class _Db:
            def fetch(self, query, params=None):
                return []

            def merge_financial_facts(self, rows, sync_run_id):
                return len(rows)

            def merge_accounting_flags(self, rows, sync_run_id):
                return len(rows)

            def merge_financial_derived(self, rows, sync_run_id):
                return len(rows)

        facts = {"cik": 320193, "facts": {}}
        with patch(
            "edgar_warehouse.infrastructure.edgartools_sec_gateway.fetch_companyfacts_json",
            return_value=facts,
        ) as gw:
            with patch(
                "edgar_warehouse.infrastructure.sec_client.download_sec_bytes",
                side_effect=AssertionError("parallel sec_client"),
            ):
                with patch(
                    "edgar_warehouse.parsers.financials.parse_entity_facts",
                    return_value={
                        "sec_financial_fact": [],
                        "sec_accounting_flag": [],
                    },
                ):
                    metrics = fi.run_bootstrap_entity_facts(
                        cik_list=[320193],
                        db=_Db(),
                        identity="Tester test@example.com",
                        sync_run_id="run1",
                        force=True,
                    )
        gw.assert_called_once()
        self.assertEqual(metrics["network_fetches"], 1)
        self.assertEqual(metrics["silver_skips"], 0)

    def test_entity_facts_silver_skip_still_avoids_gateway(self) -> None:
        from edgar_warehouse.application.workflows import fundamentals_ingest as fi

        class _Db:
            def fetch(self, query, params=None):
                return [{"ok": 1}]

            def merge_financial_facts(self, *a, **k):
                raise AssertionError("skip")

            def merge_accounting_flags(self, *a, **k):
                raise AssertionError("skip")

            def merge_financial_derived(self, *a, **k):
                raise AssertionError("skip")

        with patch(
            "edgar_warehouse.infrastructure.edgartools_sec_gateway.fetch_companyfacts_json",
            side_effect=AssertionError("gateway must not run on silver skip"),
        ):
            metrics = fi.run_bootstrap_entity_facts(
                cik_list=[320193],
                db=_Db(),
                identity="Tester test@example.com",
                sync_run_id="run1",
                force=False,
            )
        self.assertEqual(metrics["silver_skips"], 1)
        self.assertEqual(metrics["network_fetches"], 0)


class DebugEventLoggingTests(unittest.TestCase):
    """Regression: this gateway had no per-call debug visibility -- callers
    only saw the aggregate result, not which URL was actually fetched over
    the network. Each call now emits a structured JSON-line event (matching
    sec_client.py's _emit_sec_pull_event shape)."""

    def test_download_bytes_emits_sec_call_events(self) -> None:
        url = "https://www.sec.gov/files/company_tickers.json"
        download_file = Mock(return_value=b'{"ok": true}')
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            gateway.download_bytes(url, "Tester test@example.com", download_file_fn=download_file)

        events = _parse_debug_events(stderr.getvalue())
        event_names = [e["event"] for e in events]
        self.assertEqual(event_names, ["sec_call_started", "sec_call_completed"])
        self.assertEqual(events[0]["url"], url)
        self.assertEqual(events[1]["bytes"], len(b'{"ok": true}'))

    def test_download_bytes_emits_failure_event_on_error(self) -> None:
        url = "https://www.sec.gov/files/company_tickers.json"
        download_file = Mock(side_effect=RuntimeError("boom"))
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(WarehouseRuntimeError):
                gateway.download_bytes(
                    url, "Tester test@example.com", download_file_fn=download_file
                )

        events = _parse_debug_events(stderr.getvalue())
        event_names = [e["event"] for e in events]
        self.assertEqual(event_names, ["sec_call_started", "sec_call_failed"])
        self.assertEqual(events[1]["error"], "RuntimeError")

    def test_download_json_fn_path_emits_sec_call_events(self) -> None:
        url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
        download_json = Mock(return_value={"cik": 320193})
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            gateway.download_json(url, "Tester test@example.com", download_json_fn=download_json)

        events = _parse_debug_events(stderr.getvalue())
        event_names = [e["event"] for e in events]
        self.assertEqual(event_names, ["sec_call_started", "sec_call_completed"])
        self.assertEqual(events[0]["url"], url)


if __name__ == "__main__":
    unittest.main()
