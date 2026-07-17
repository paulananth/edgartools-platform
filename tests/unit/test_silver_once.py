"""Tickets 03–05: silver-once skip helpers."""

from __future__ import annotations

import unittest
import unittest.mock

from edgar_warehouse.infrastructure.silver_once import (
    daily_index_is_finalized,
    has_companyfacts_at_version,
    has_successful_ownership_parse,
)
from edgar_warehouse.parsers.financials import PARSER_VERSION as FACTS_PARSER_VERSION
from edgar_warehouse.parsers.ownership import PARSER_NAME, PARSER_VERSION


class _FakeDb:
    def __init__(self, rows_by_query: dict[str, list] | None = None, daily=None):
        self.rows_by_query = rows_by_query or {}
        self.daily = daily
        self.last_query = ""

    def fetch(self, query: str, params=None):
        self.last_query = " ".join(query.split())
        key = "parse_run" if "sec_parse_run" in query else "owners" if "sec_ownership" in query else "facts"
        return list(self.rows_by_query.get(key, []))

    def get_daily_index_checkpoint(self, business_date: str):
        return self.daily


class SilverOnceTests(unittest.TestCase):
    def test_ownership_parse_run_hit(self) -> None:
        db = _FakeDb({"parse_run": [{"ok": 1}]})
        self.assertTrue(
            has_successful_ownership_parse(
                db,
                accession_number="0001",
                parser_name=PARSER_NAME,
                parser_version=PARSER_VERSION,
            )
        )

    def test_ownership_fallback_to_owner_rows(self) -> None:
        db = _FakeDb({"parse_run": [], "owners": [{"ok": 1}]})
        self.assertTrue(
            has_successful_ownership_parse(
                db,
                accession_number="0001",
                parser_name=PARSER_NAME,
                parser_version=PARSER_VERSION,
            )
        )

    def test_ownership_miss(self) -> None:
        db = _FakeDb({})
        self.assertFalse(
            has_successful_ownership_parse(
                db,
                accession_number="0001",
                parser_name=PARSER_NAME,
                parser_version=PARSER_VERSION,
            )
        )

    def test_companyfacts_version_hit(self) -> None:
        db = _FakeDb({"facts": [{"ok": 1}]})
        self.assertTrue(
            has_companyfacts_at_version(db, cik=320193, facts_parser_version=FACTS_PARSER_VERSION)
        )

    def test_companyfacts_miss(self) -> None:
        db = _FakeDb({})
        self.assertFalse(
            has_companyfacts_at_version(db, cik=320193, facts_parser_version=FACTS_PARSER_VERSION)
        )

    def test_daily_index_finalized(self) -> None:
        db = _FakeDb(daily={"status": "succeeded"})
        self.assertTrue(daily_index_is_finalized(db, business_date="2024-01-02"))
        db2 = _FakeDb(daily={"status": "running"})
        self.assertFalse(daily_index_is_finalized(db2, business_date="2024-01-02"))


class EntityFactsSkipTests(unittest.TestCase):
    def test_run_bootstrap_skips_network_when_silver_has_version(self) -> None:
        from edgar_warehouse.application.workflows import fundamentals_ingest as fi

        class _Db:
            def fetch(self, query, params=None):
                return [{"ok": 1}]

            def merge_financial_facts(self, *a, **k):
                raise AssertionError("should not merge on skip")

            def merge_accounting_flags(self, *a, **k):
                raise AssertionError("should not merge on skip")

            def merge_financial_derived(self, *a, **k):
                raise AssertionError("should not merge on skip")

        with unittest.mock.patch(
            "edgar_warehouse.infrastructure.edgartools_sec_gateway.fetch_companyfacts_json",
            side_effect=AssertionError("gateway must not run on silver skip"),
        ):
            metrics = fi.run_bootstrap_entity_facts(
                cik_list=[320193],
                db=_Db(),
                identity="Test test@example.com",
                sync_run_id="run1",
                force=False,
            )
        self.assertEqual(metrics["silver_skips"], 1)
        self.assertEqual(metrics["network_fetches"], 0)
        self.assertEqual(metrics["ciks_skipped"], 1)

    def test_force_bypasses_skip(self) -> None:
        from edgar_warehouse.application.workflows import fundamentals_ingest as fi

        class _Db:
            def fetch(self, query, params=None):
                return [{"ok": 1}]

            def merge_financial_facts(self, rows, sync_run_id):
                return len(rows)

            def merge_accounting_flags(self, rows, sync_run_id):
                return len(rows)

            def merge_financial_derived(self, rows, sync_run_id):
                return len(rows)

        facts = {"cik": 320193, "facts": {}}
        with unittest.mock.patch(
            "edgar_warehouse.infrastructure.edgartools_sec_gateway.fetch_companyfacts_json",
            return_value=facts,
        ) as gw:
            with unittest.mock.patch(
                "edgar_warehouse.parsers.financials.parse_entity_facts",
                return_value={
                    "sec_financial_fact": [],
                    "sec_accounting_flag": [],
                },
            ):
                metrics = fi.run_bootstrap_entity_facts(
                    cik_list=[320193],
                    db=_Db(),
                    identity="Test test@example.com",
                    sync_run_id="run1",
                    force=True,
                )
                gw.assert_called_once()
        self.assertEqual(metrics["network_fetches"], 1)
        self.assertEqual(metrics["silver_skips"], 0)


if __name__ == "__main__":
    unittest.main()
