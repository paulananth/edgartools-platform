"""Submission workflow phase-order tests."""

from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from edgar_warehouse import cli
from edgar_warehouse.application import warehouse_orchestrator


class _CachedSubmissionDb:
    def __init__(self) -> None:
        self.source_checkpoints = []
        self.company_states = []

    def get_company_sync_state(self, cik: int):
        return {"tracking_status": "active"}

    def get_source_checkpoint(self, source_name: str, source_key: str):
        return {"last_sha256": "sha-main" if source_name == "submissions_main" else "sha-page"}

    def upsert_source_checkpoint(self, row: dict) -> None:
        self.source_checkpoints.append(row)

    def upsert_company_sync_state(self, row: dict) -> None:
        self.company_states.append(row)

    def stage_submission(self, **kwargs):
        raise AssertionError("cached submissions should not restage silver")


class _ConfiguredFormDb:
    def __init__(self) -> None:
        self.filings = {
            "ownership-1": {"accession_number": "ownership-1", "form": "4"},
            "generic-1": {"accession_number": "generic-1", "form": "10-K"},
            "adv-1": {"accession_number": "adv-1", "form": "ADV"},
        }

    def get_filing(self, accession_number: str):
        return self.filings.get(accession_number)


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
                load_mode="bootstrap",
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

    def test_bootstrap_artifact_policy_runs_after_silver_for_selected_accessions(self) -> None:
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
                "recent_accessions": [f"{cik}-recent"],
                "pagination_accessions": [f"{cik}-historical"],
            }

        def artifacts(**kwargs):
            events.append("artifacts")
            return {
                "raw_writes": [{"source_name": "filing_document"}],
                "rows_written": 2,
                "rows_skipped": 0,
            }

        with (
            patch.object(warehouse_orchestrator, "_capture_submission_bronze_snapshot", side_effect=capture),
            patch.object(warehouse_orchestrator, "_apply_submission_snapshot_to_silver", side_effect=apply),
            patch.object(
                warehouse_orchestrator,
                "_run_configured_form_artifact_pipeline",
                side_effect=artifacts,
                create=True,
            ) as artifact_pipeline,
        ):
            result = warehouse_orchestrator._run_submissions_bronze_then_silver(
                context=object(),
                db=object(),
                sync_run_id="run-1",
                ciks=[1001],
                include_pagination=True,
                fetch_date=date(2026, 4, 25),
                force=False,
                load_mode="bootstrap_batch",
                artifact_policy="all_attachments",
                parser_policy="configured_forms",
            )

        self.assertEqual(events, ["bronze:1001", "silver:1001", "artifacts"])
        artifact_pipeline.assert_called_once()
        self.assertEqual(
            artifact_pipeline.call_args.kwargs["accession_numbers"],
            ["1001-recent", "1001-historical"],
        )
        self.assertEqual(result["rows_written"], 3)
        self.assertEqual(len(result["raw_writes"]), 2)

    def test_cached_submission_still_returns_pagination_accessions(self) -> None:
        db = _CachedSubmissionDb()
        snapshot = {
            "cik": 1001,
            "include_pagination": True,
            "main_payload": {
                "filings": {
                    "recent": {
                        "accessionNumber": ["recent-1"],
                        "form": ["4"],
                        "filingDate": ["2026-04-25"],
                        "reportDate": ["2026-04-24"],
                        "acceptanceDateTime": ["20260425120000"],
                        "primaryDocument": ["recent.xml"],
                    }
                }
            },
            "main_write_record": {
                "sha256": "sha-main",
                "source_name": "submissions_main",
                "relative_path": "submissions/main.json",
            },
            "manifest_file_names": ["CIK0000001001-submissions-001.json"],
            "pagination_snapshots": [
                {
                    "file_name": "CIK0000001001-submissions-001.json",
                    "payload": {
                        "filings": {
                            "accessionNumber": ["historical-1"],
                            "form": ["4"],
                            "filingDate": ["2025-01-02"],
                            "reportDate": ["2025-01-01"],
                            "acceptanceDateTime": ["20250102120000"],
                            "primaryDocument": ["historical.xml"],
                        }
                    },
                    "write_record": {
                        "sha256": "sha-page",
                        "source_name": "submissions_pagination",
                        "relative_path": "submissions/001.json",
                    },
                }
            ],
        }

        with patch.object(warehouse_orchestrator, "_sync_mdm_tracking_status"):
            result = warehouse_orchestrator._apply_submission_snapshot_to_silver(
                db=db,
                sync_run_id="run-1",
                snapshot=snapshot,
                force=False,
                load_mode="bootstrap_batch",
                recent_limit=None,
                now=date(2026, 4, 25),
            )

        self.assertEqual(result["recent_accessions"], ["recent-1"])
        self.assertEqual(result["pagination_accessions"], ["historical-1"])

    def test_configured_form_artifact_pipeline_filters_to_parser_forms(self) -> None:
        calls: list[tuple[str, str]] = []

        def refresh(**kwargs):
            calls.append(("artifact", kwargs["accession_number"]))
            return {"raw_writes": [{"source_name": "filing_document"}], "attachment_count": 1}

        def parse(**kwargs):
            calls.append(("parser", kwargs["accession_number"]))
            return 3

        with (
            patch("edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts", side_effect=refresh),
            patch.object(warehouse_orchestrator, "_run_parse_pipeline", side_effect=parse),
        ):
            result = warehouse_orchestrator._run_configured_form_artifact_pipeline(
                context=SimpleNamespace(identity="tester@example.com"),
                db=_ConfiguredFormDb(),
                sync_run_id="run-1",
                accession_numbers=["ownership-1", "generic-1", "adv-1", "ownership-1"],
                artifact_policy="all_attachments",
                parser_policy="configured_forms",
                force=False,
            )

        self.assertEqual(
            calls,
            [
                ("artifact", "ownership-1"),
                ("parser", "ownership-1"),
                ("artifact", "adv-1"),
                ("parser", "adv-1"),
            ],
        )
        self.assertEqual(result["rows_written"], 8)
        self.assertEqual(len(result["raw_writes"]), 2)

    def test_bootstrap_batch_cli_defaults_to_artifact_and_parser_policies(self) -> None:
        args = cli.build_parser().parse_args(["bootstrap-batch", "--cik-list", "1001"])

        self.assertEqual(args.artifact_policy, "all_attachments")
        self.assertEqual(args.parser_policy, "configured_forms")


if __name__ == "__main__":
    unittest.main()
