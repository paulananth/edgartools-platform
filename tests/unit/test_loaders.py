from __future__ import annotations

from datetime import date
import unittest

from edgar_warehouse.loaders import stage_company_loader, stage_daily_index_filing_loader


class LoaderTests(unittest.TestCase):
    def test_stage_company_loader_extracts_top_level_fields(self) -> None:
        rows = stage_company_loader(
            payload={"name": "Acme Corp", "entityType": "operating", "sic": "1234"},
            cik=123456,
            sync_run_id="sync-1",
            raw_object_id="raw-1",
            load_mode="bootstrap_full",
        )

        self.assertEqual(
            rows,
            [
                {
                    "cik": 123456,
                    "entity_name": "Acme Corp",
                    "entity_type": "operating",
                    "sic": "1234",
                    "sic_description": None,
                    "state_of_incorporation": None,
                    "state_of_incorporation_desc": None,
                    "fiscal_year_end": None,
                    "ein": None,
                    "description": None,
                    "category": None,
                    "sync_run_id": "sync-1",
                    "raw_object_id": "raw-1",
                    "load_mode": "bootstrap_full",
                }
            ],
        )

    def test_stage_daily_index_filing_loader_extracts_filing_rows(self) -> None:
        payload = (
            b"-----\n"
            b"4  ACME CORP  123456  20240102  edgar/data/123456/0000123456-24-000001-index.htm\n"
        )

        rows = stage_daily_index_filing_loader(
            payload=payload,
            business_date=date(2024, 1, 2),
            sync_run_id="sync-1",
            raw_object_id="raw-1",
            source_url="https://www.sec.gov/Archives/edgar/daily-index/2024/QTR1/form.20240102.idx",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cik"], 123456)
        self.assertEqual(rows[0]["accession_number"], "0000123456-24-000001")
        self.assertEqual(rows[0]["row_ordinal"], 1)
