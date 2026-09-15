"""Regression tests for fundamentals-daily-integration map Tickets 02/03.

Ticket 02: accession-level incremental scoping for the per-filing/thirteenf
bootstrap-fundamentals modes (sec_fundamentals_processed_accession).

Ticket 03: entity-facts's per-CIK refresh trigger
(sec_entity_facts_refresh_watermark), composing with the pre-existing
has_companyfacts_at_version one-time-per-parser-version gate.

Both marker writers are landing-only (silver-merge-engine-migration Ticket
12): their tests assert on the recorded landing rows. The reader SQL
(get_ciks_with_new_qualifying_filing, run against EDGARTOOLS_SILVER) lost its
schema-backed local fixture with the DuckDB engine (Ticket 17); only its
no-query guard is covered here. The orchestration-level skip/process/mark
tests follow this file's own established MagicMock convention
(tests/unit/test_fundamentals_modules.py).
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from tests.support.silver_rows import open_landing_db


# ---------------------------------------------------------------------------
# Ticket 02 -- sec_fundamentals_processed_accession marker (landing-only)
# ---------------------------------------------------------------------------

class _LandingStoreTestCase(unittest.TestCase):
    """A SilverLandingStore with a LandingExportBuffer attached."""

    def setUp(self) -> None:
        self.db = open_landing_db()

    def tearDown(self) -> None:
        self.db.close()


class FundamentalsProcessedAccessionMarkerTests(_LandingStoreTestCase):
    """silver-merge-engine-migration Ticket 12: the marker is landing-only."""

    def test_mark_records_a_landing_row(self) -> None:
        self.db.mark_fundamentals_accession_processed(
            mode="per-filing", accession_number="0001-test",
        )
        recorded = self.db.landing_export.tables()["sec_fundamentals_processed_accession"]
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["mode"], "per-filing")
        self.assertEqual(recorded[0]["accession_number"], "0001-test")
        self.assertIsNotNone(recorded[0]["processed_at"].tzinfo)

    def test_repeated_mark_appends_a_second_landing_row(self) -> None:
        # The dbt silver model keeps one row per (mode, accession_number).
        self.db.mark_fundamentals_accession_processed(mode="per-filing", accession_number="acc-1")
        self.db.mark_fundamentals_accession_processed(mode="per-filing", accession_number="acc-1")
        self.assertEqual(
            self.db.landing_export.row_count("sec_fundamentals_processed_accession"), 2,
        )

    def test_missing_accession_number_raises_before_recording(self) -> None:
        with self.assertRaises(ValueError):
            self.db.mark_fundamentals_accession_processed(mode="thirteenf", accession_number=None)
        self.assertEqual(self.db.landing_export.total_row_count(), 0)


# ---------------------------------------------------------------------------
# Ticket 02 -- run_bootstrap_fundamentals_per_filing / run_bootstrap_thirteenf
# skip-already-processed wiring (MagicMock, matches test_fundamentals_modules.py)
# ---------------------------------------------------------------------------

class PerFilingSkipsAlreadyProcessedTests(unittest.TestCase):
    def test_second_run_skips_already_processed_accession_no_new_rows(self) -> None:
        from edgar_warehouse.application.workflows.fundamentals_ingest import (
            run_bootstrap_fundamentals_per_filing,
        )

        source = MagicMock()
        source.fetch.side_effect = [
            [{"accession_number": "already-done", "cik": 1, "form": "8-K",
              "filing_date": "2025-06-01", "items": "2.02"}],
            [{"accession_number": "already-done"}],
        ]
        db = MagicMock()

        with patch("edgar_warehouse.parsers.get_parser") as mock_get_parser:
            metrics = run_bootstrap_fundamentals_per_filing(
                cik_list=[1], source=source, db=db, sync_run_id="run-1",
            )

        mock_get_parser.assert_not_called()
        db.merge_earnings_releases.assert_not_called()
        db.mark_fundamentals_accession_processed.assert_not_called()
        self.assertEqual(metrics["filings_already_processed"], 1)
        self.assertEqual(metrics["filings_parsed"], 0)

    def test_new_accession_in_same_cik_window_still_processed(self) -> None:
        from edgar_warehouse.application.workflows.fundamentals_ingest import (
            run_bootstrap_fundamentals_per_filing,
        )

        source = MagicMock()
        source.fetch.side_effect = [
            [
                {"accession_number": "already-done", "cik": 1, "form": "8-K",
                 "filing_date": "2025-06-01", "items": "2.02"},
                {"accession_number": "brand-new", "cik": 1, "form": "8-K",
                 "filing_date": "2025-06-02", "items": "2.02"},
            ],
            [{"accession_number": "already-done"}],
            [{"raw_object_id": "raw-1", "is_primary": True}],
            [{"raw_object_id": "raw-1", "storage_path": "s3://bucket/doc.htm"}],
        ]
        db = MagicMock()
        db.merge_earnings_releases.return_value = 1
        db.merge_executive_records.return_value = 0
        db.merge_guidance_facts.return_value = 0
        db.merge_guidance_fact_rejects.return_value = 0

        with patch(
            "edgar_warehouse.parsers.get_parser",
            return_value=lambda *a, **kw: {
                "sec_earnings_release": [{"x": 1}], "sec_executive_record": [],
            },
        ), patch(
            "edgar_warehouse.infrastructure.object_storage.read_bytes",
            return_value=b"<html>irrelevant</html>",
        ):
            metrics = run_bootstrap_fundamentals_per_filing(
                cik_list=[1], source=source, db=db, sync_run_id="run-1",
            )

        self.assertEqual(metrics["filings_already_processed"], 1)
        self.assertEqual(metrics["filings_parsed"], 1)
        db.mark_fundamentals_accession_processed.assert_called_once_with(
            mode="per-filing", accession_number="brand-new",
        )


class ThirteenfSkipsAlreadyProcessedTests(unittest.TestCase):
    def test_second_run_skips_already_processed_accession_no_new_rows(self) -> None:
        from edgar_warehouse.application.workflows.fundamentals_ingest import run_bootstrap_thirteenf

        source = MagicMock()
        source.fetch.side_effect = [
            [{"accession_number": "already-done", "cik": 9, "report_date": "2024-03-31",
              "filing_date": "2024-05-01", "form": "13F-HR"}],
            [{"accession_number": "already-done"}],
        ]
        db = MagicMock()

        metrics = run_bootstrap_thirteenf(
            cik_list=[9], source=source, db=db, sync_run_id="run-1",
        )

        db.merge_thirteenf_filings.assert_not_called()
        db.merge_thirteenf_holdings.assert_not_called()
        db.mark_fundamentals_accession_processed.assert_not_called()
        self.assertEqual(metrics["filings_already_processed"], 1)
        self.assertEqual(metrics["filings_parsed"], 0)

    def test_new_accession_in_same_cik_window_still_processed(self) -> None:
        from edgar_warehouse.application.workflows.fundamentals_ingest import run_bootstrap_thirteenf

        source = MagicMock()
        source.fetch.side_effect = [
            [
                {"accession_number": "already-done", "cik": 9, "report_date": "2024-03-31",
                 "filing_date": "2024-05-01", "form": "13F-HR"},
                {"accession_number": "brand-new", "cik": 9, "report_date": "2024-06-30",
                 "filing_date": "2024-08-01", "form": "13F-HR"},
            ],
            [{"accession_number": "already-done"}],
            [
                {"raw_object_id": "cover", "is_primary": True, "description": "PRIMARY"},
                {"raw_object_id": "table", "is_primary": False,
                 "description": "INFORMATION TABLE"},
            ],
            [{"raw_object_id": "table", "storage_path": "s3://bucket/table.xml"}],
            [{"raw_object_id": "cover", "storage_path": "s3://bucket/cover.xml"}],
        ]
        db = MagicMock()
        db.merge_thirteenf_filings.return_value = 1
        db.merge_thirteenf_holdings.return_value = 1

        with patch(
            "edgar_warehouse.infrastructure.object_storage.read_bytes", return_value=b"<xml/>",
        ), patch(
            "edgar_warehouse.parsers.thirteenf.parse_thirteenf",
            return_value={"sec_thirteenf_holding": [{"cusip": "123456789"}]},
        ), patch(
            "edgar_warehouse.parsers.thirteenf_cover.parse_thirteenf_cover",
            return_value={"amendment_type": "original", "confidential_omission": False},
        ):
            metrics = run_bootstrap_thirteenf(
                cik_list=[9], source=source, db=db, sync_run_id="run-1",
            )

        self.assertEqual(metrics["filings_already_processed"], 1)
        self.assertEqual(metrics["filings_parsed"], 1)
        db.mark_fundamentals_accession_processed.assert_called_once_with(
            mode="thirteenf", accession_number="brand-new",
        )


# ---------------------------------------------------------------------------
# Ticket 03 -- sec_entity_facts_refresh_watermark + get_ciks_with_new_qualifying_filing
# ---------------------------------------------------------------------------

class GetCiksWithNewQualifyingFilingTests(unittest.TestCase):
    def test_empty_cik_list_returns_empty_set_without_querying(self) -> None:
        from edgar_warehouse.infrastructure.silver_once import get_ciks_with_new_qualifying_filing
        fake_db = MagicMock()
        self.assertEqual(get_ciks_with_new_qualifying_filing(fake_db, cik_list=[]), set())
        fake_db.fetch.assert_not_called()


class EntityFactsRefreshWatermarkMarkerTests(_LandingStoreTestCase):
    """silver-merge-engine-migration Ticket 12: the watermark is landing-only."""

    def test_mark_records_a_landing_row(self) -> None:
        self.db.mark_entity_facts_refreshed(320193)
        recorded = self.db.landing_export.tables()["sec_entity_facts_refresh_watermark"]
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["cik"], 320193)
        self.assertIsNotNone(recorded[0]["entity_facts_refreshed_at"].tzinfo)

    def test_repeated_mark_appends_a_second_landing_row(self) -> None:
        # The dbt silver model keeps one row per cik.
        self.db.mark_entity_facts_refreshed(320193)
        self.db.mark_entity_facts_refreshed(320193)
        self.assertEqual(
            self.db.landing_export.row_count("sec_entity_facts_refresh_watermark"), 2,
        )


# ---------------------------------------------------------------------------
# Ticket 03 -- run_bootstrap_entity_facts refresh-trigger wiring (MagicMock)
# ---------------------------------------------------------------------------

class EntityFactsRefreshTriggerTests(unittest.TestCase):
    def test_cik_with_no_new_filing_is_skipped(self) -> None:
        from edgar_warehouse.application.workflows.fundamentals_ingest import (
            run_bootstrap_entity_facts,
        )

        db = MagicMock()
        db.fetch.side_effect = [
            [],           # get_ciks_with_new_qualifying_filing -> nobody new
            [{"ok": 1}],  # has_companyfacts_at_version(cik=1) -> already has facts
        ]

        with patch(
            "edgar_warehouse.infrastructure.edgartools_sec_gateway.fetch_companyfacts_json",
        ) as mock_fetch:
            metrics = run_bootstrap_entity_facts(
                cik_list=[1], db=db, identity="test", sync_run_id="run-1",
            )

        mock_fetch.assert_not_called()
        self.assertEqual(metrics["ciks_skipped"], 1)
        self.assertEqual(metrics["network_fetches"], 0)
        db.mark_entity_facts_refreshed.assert_not_called()

    def test_cik_with_new_qualifying_filing_is_refreshed(self) -> None:
        from edgar_warehouse.application.workflows.fundamentals_ingest import (
            run_bootstrap_entity_facts,
        )

        db = MagicMock()
        db.fetch.side_effect = [
            [{"cik": 1}],  # get_ciks_with_new_qualifying_filing -> cik 1 has a new filing
            [{"ok": 1}],   # has_companyfacts_at_version(cik=1) -> already has facts (would
                           # otherwise be skipped forever without the new trigger)
        ]
        db.merge_financial_facts.return_value = 0
        db.merge_accounting_flags.return_value = 0

        with patch(
            "edgar_warehouse.infrastructure.edgartools_sec_gateway.fetch_companyfacts_json",
            return_value={"cik": 1},
        ) as mock_fetch, patch(
            "edgar_warehouse.parsers.financials.parse_entity_facts",
            return_value={"sec_financial_fact": [], "sec_accounting_flag": []},
        ):
            metrics = run_bootstrap_entity_facts(
                cik_list=[1], db=db, identity="test", sync_run_id="run-1",
            )

        mock_fetch.assert_called_once()
        self.assertEqual(metrics["ciks_processed"], 1)
        db.mark_entity_facts_refreshed.assert_called_once_with(1)

    def test_parser_version_bump_forces_refresh_regardless_of_watermark(self) -> None:
        """Regression guard: even with no new qualifying filing (the new trigger
        alone would skip), a parser-version bump (has_companyfacts_at_version ->
        False, simulating no rows yet at the new version) must still force a
        refresh -- composes with, never replaces, the existing gate."""
        from edgar_warehouse.application.workflows.fundamentals_ingest import (
            run_bootstrap_entity_facts,
        )

        db = MagicMock()
        db.fetch.side_effect = [
            [],  # get_ciks_with_new_qualifying_filing -> nobody new
            [],  # has_companyfacts_at_version -> False (parser version just bumped)
        ]
        db.merge_financial_facts.return_value = 0
        db.merge_accounting_flags.return_value = 0

        with patch(
            "edgar_warehouse.infrastructure.edgartools_sec_gateway.fetch_companyfacts_json",
            return_value={"cik": 1},
        ) as mock_fetch, patch(
            "edgar_warehouse.parsers.financials.parse_entity_facts",
            return_value={"sec_financial_fact": [], "sec_accounting_flag": []},
        ):
            metrics = run_bootstrap_entity_facts(
                cik_list=[1], db=db, identity="test", sync_run_id="run-1",
            )

        mock_fetch.assert_called_once()
        self.assertEqual(metrics["ciks_processed"], 1)

    def test_force_bypasses_both_gates_without_querying_new_filing_set(self) -> None:
        from edgar_warehouse.application.workflows.fundamentals_ingest import (
            run_bootstrap_entity_facts,
        )

        db = MagicMock()
        db.merge_financial_facts.return_value = 0
        db.merge_accounting_flags.return_value = 0

        with patch(
            "edgar_warehouse.infrastructure.edgartools_sec_gateway.fetch_companyfacts_json",
            return_value={"cik": 1},
        ) as mock_fetch, patch(
            "edgar_warehouse.parsers.financials.parse_entity_facts",
            return_value={"sec_financial_fact": [], "sec_accounting_flag": []},
        ):
            metrics = run_bootstrap_entity_facts(
                cik_list=[1], db=db, identity="test", sync_run_id="run-1", force=True,
            )

        mock_fetch.assert_called_once()
        self.assertEqual(metrics["ciks_processed"], 1)
        db.fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
