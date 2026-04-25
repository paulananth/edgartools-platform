"""Submission workflow phase-order tests."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from edgar_warehouse.application import warehouse_orchestrator


class SubmissionPhaseOrderTests(unittest.TestCase):
    def test_bulk_submission_flow_captures_all_bronze_before_silver(self) -> None:
        events: list[str] = []

        def capture(**kwargs):
            cik = kwargs["cik"]
            events.append(f"bronze:{cik}")
            return {
                "cik": cik,
                "raw_writes": [{"source_name": "submissions_main", "cik": cik}],
            }

        def apply(**kwargs):
            cik = kwargs["snapshot"]["cik"]
            events.append(f"silver:{cik}")
            return {
                "rows_written": 1,
                "rows_skipped": 0,
                "recent_accessions": [f"{cik}-accession"],
                "pagination_accessions": [],
            }

        with (
            patch.object(warehouse_orchestrator, "_capture_submission_bronze_snapshot", side_effect=capture),
            patch.object(warehouse_orchestrator, "_apply_submission_snapshot_to_silver", side_effect=apply),
        ):
            result = warehouse_orchestrator._run_submissions_bronze_then_silver(
                context=object(),
                db=object(),
                sync_run_id="run-1",
                ciks=[1001, 1002, 1003],
                include_pagination=False,
                fetch_date=date(2026, 4, 25),
                force=False,
                load_mode="bootstrap_recent_10",
            )

        self.assertEqual(
            events,
            [
                "bronze:1001",
                "bronze:1002",
                "bronze:1003",
                "silver:1001",
                "silver:1002",
                "silver:1003",
            ],
        )
        self.assertEqual(result["rows_written"], 3)
        self.assertEqual(len(result["raw_writes"]), 3)


if __name__ == "__main__":
    unittest.main()
