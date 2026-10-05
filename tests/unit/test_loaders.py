from __future__ import annotations

import unittest

from tests.support.retired_submission_loaders import (
    stage_company_loader,
)


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
