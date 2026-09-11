"""Regression tests for fundamentals-daily-integration map Tickets 02/03.

Ticket 02: accession-level incremental scoping for the per-filing/thirteenf
bootstrap-fundamentals modes (sec_fundamentals_processed_accession).

Ticket 03: entity-facts's per-CIK refresh trigger
(sec_entity_facts_refresh_watermark), composing with the pre-existing
has_companyfacts_at_version one-time-per-parser-version gate.

Real-DuckDB tests below exercise the new tables/SQL directly (schema-backed,
not a hand-rolled stub) -- per this repo's own lesson (CLAUDE.md's
"INSTITUTIONAL_HOLDS/EMPLOYED_BY" and "MDM Postgres migration-011" 5-whys
entries) that a never-yet-run-against-real-data query needs a real schema
fixture, not just a mock. The orchestration-level skip/process/mark tests
follow this file's own established MagicMock convention
(tests/unit/test_fundamentals_modules.py).
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from edgar_warehouse.silver_store import SilverDatabase


class _RealSilverDatabaseTestCase(unittest.TestCase):
    """Shared setUp/tearDown for tests needing a real, throwaway SilverDatabase."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.mkdtemp()
        self.db = SilverDatabase(str(Path(self._tmp_dir) / "silver.duckdb"))

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Ticket 02 -- sec_fundamentals_processed_accession table + method (real DuckDB)
# ---------------------------------------------------------------------------

class FundamentalsProcessedAccessionTableTests(_RealSilverDatabaseTestCase):
    def test_mark_then_fetch_processed(self) -> None:
        self.db.mark_fundamentals_accession_processed(
            mode="per-filing", accession_number="0001-test",
        )
        rows = self.db.fetch(
            "SELECT accession_number FROM sec_fundamentals_processed_accession "
            "WHERE mode = ?",
            ["per-filing"],
        )
        self.assertEqual({r["accession_number"] for r in rows}, {"0001-test"})

    def test_different_modes_are_independent(self) -> None:
        self.db.mark_fundamentals_accession_processed(
            mode="per-filing", accession_number="acc-1",
        )
        rows = self.db.fetch(
            "SELECT accession_number FROM sec_fundamentals_processed_accession "
            "WHERE mode = ?",
            ["thirteenf"],
        )
        self.assertEqual(rows, [])

    def test_mark_is_idempotent_upsert(self) -> None:
        self.db.mark_fundamentals_accession_processed(mode="per-filing", accession_number="acc-1")
        self.db.mark_fundamentals_accession_processed(mode="per-filing", accession_number="acc-1")
        rows = self.db.fetch(
            "SELECT COUNT(*) AS n FROM sec_fundamentals_processed_accession "
            "WHERE mode = 'per-filing' AND accession_number = 'acc-1'",
        )
        self.assertEqual(rows[0]["n"], 1)


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
        ]
        db = MagicMock()
        db.fetch.return_value = [{"accession_number": "already-done"}]

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
            [{"raw_object_id": "raw-1", "is_primary": True}],
            [{"raw_object_id": "raw-1", "storage_path": "s3://bucket/doc.htm"}],
        ]
        db = MagicMock()
        db.fetch.return_value = [{"accession_number": "already-done"}]
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
        ]
        db = MagicMock()
        db.fetch.return_value = [{"accession_number": "already-done"}]

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
            [
                {"raw_object_id": "cover", "is_primary": True, "description": "PRIMARY"},
                {"raw_object_id": "table", "is_primary": False,
                 "description": "INFORMATION TABLE"},
            ],
            [{"raw_object_id": "table", "storage_path": "s3://bucket/table.xml"}],
            [{"raw_object_id": "cover", "storage_path": "s3://bucket/cover.xml"}],
        ]
        db = MagicMock()
        db.fetch.return_value = [{"accession_number": "already-done"}]
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
# (real DuckDB)
# ---------------------------------------------------------------------------

class GetCiksWithNewQualifyingFilingTests(_RealSilverDatabaseTestCase):
    def _seed_filing(self, *, accession: str, cik: int, form: str, filing_date: str) -> None:
        self.db._conn.execute(
            "INSERT INTO sec_company_filing (accession_number, cik, form, filing_date) "
            "VALUES (?, ?, ?, ?)",
            [accession, cik, form, filing_date],
        )

    def test_cik_with_no_watermark_is_new(self) -> None:
        from edgar_warehouse.infrastructure.silver_once import get_ciks_with_new_qualifying_filing
        self._seed_filing(accession="a1", cik=1, form="10-K", filing_date="2026-01-01")
        self.assertEqual(get_ciks_with_new_qualifying_filing(self.db, cik_list=[1]), {1})

    def test_cik_with_watermark_after_latest_filing_is_not_new(self) -> None:
        from edgar_warehouse.infrastructure.silver_once import get_ciks_with_new_qualifying_filing
        self._seed_filing(accession="a1", cik=1, form="10-K", filing_date="2026-01-01")
        self.db.mark_entity_facts_refreshed(1)
        self.assertEqual(get_ciks_with_new_qualifying_filing(self.db, cik_list=[1]), set())

    def test_cik_with_new_filing_after_watermark_is_new(self) -> None:
        from edgar_warehouse.infrastructure.silver_once import get_ciks_with_new_qualifying_filing
        self._seed_filing(accession="a1", cik=1, form="10-K", filing_date="2026-01-01")
        self.db.mark_entity_facts_refreshed(1)
        self._seed_filing(accession="a2", cik=1, form="10-Q", filing_date="2099-01-01")
        self.assertEqual(get_ciks_with_new_qualifying_filing(self.db, cik_list=[1]), {1})

    def test_non_qualifying_form_ignored(self) -> None:
        from edgar_warehouse.infrastructure.silver_once import get_ciks_with_new_qualifying_filing
        self._seed_filing(accession="a1", cik=1, form="8-K", filing_date="2099-01-01")
        self.assertEqual(get_ciks_with_new_qualifying_filing(self.db, cik_list=[1]), set())

    def test_empty_cik_list_returns_empty_set_without_querying(self) -> None:
        from edgar_warehouse.infrastructure.silver_once import get_ciks_with_new_qualifying_filing
        fake_db = MagicMock()
        self.assertEqual(get_ciks_with_new_qualifying_filing(fake_db, cik_list=[]), set())
        fake_db.fetch.assert_not_called()


class EntityFactsRefreshWatermarkTableTests(_RealSilverDatabaseTestCase):
    def test_mark_then_read_watermark(self) -> None:
        self.db.mark_entity_facts_refreshed(320193)
        rows = self.db.fetch(
            "SELECT cik FROM sec_entity_facts_refresh_watermark WHERE cik = ?",
            [320193],
        )
        self.assertEqual(len(rows), 1)

    def test_mark_is_idempotent_upsert(self) -> None:
        self.db.mark_entity_facts_refreshed(320193)
        self.db.mark_entity_facts_refreshed(320193)
        rows = self.db.fetch(
            "SELECT COUNT(*) AS n FROM sec_entity_facts_refresh_watermark WHERE cik = ?",
            [320193],
        )
        self.assertEqual(rows[0]["n"], 1)


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
