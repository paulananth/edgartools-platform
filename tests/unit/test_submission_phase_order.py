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
            "proxy-1": {"accession_number": "proxy-1", "form": "DEF 14A"},
            "item-502": {"accession_number": "item-502", "form": "8-K", "items": "5.02"},
            "ambiguous-8k": {"accession_number": "ambiguous-8k", "form": "8-K", "items": None},
            "earnings-8k": {"accession_number": "earnings-8k", "form": "8-K", "items": "2.02"},
            "13f-1": {"accession_number": "13f-1", "form": "13F-HR"},
        }

    def get_filing(self, accession_number: str):
        return self.filings.get(accession_number)

    def get_filing_attachments(self, accession_number: str):
        return [{"raw_object_id": f"raw-{accession_number}"}]

    def get_raw_object(self, raw_object_id: str):
        return {"sha256": f"sha-{raw_object_id}"}


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

    def test_release_submission_flow_sends_only_manifest_required_accessions(self) -> None:
        def capture(**kwargs):
            return {"cik": kwargs["cik"], "raw_writes": []}

        def apply(**kwargs):
            return {
                "rows_written": 0,
                "rows_skipped": 0,
                "recent_accessions": ["required-proxy", "unrelated-8k"],
                "pagination_accessions": ["required-13f"],
            }

        with (
            patch.object(warehouse_orchestrator, "_capture_submission_bronze_snapshot", side_effect=capture),
            patch.object(warehouse_orchestrator, "_apply_submission_snapshot_to_silver", side_effect=apply),
            patch.object(
                warehouse_orchestrator,
                "_run_configured_form_artifact_pipeline",
                return_value={"raw_writes": [], "rows_written": 0, "rows_skipped": 0},
            ) as artifact_pipeline,
        ):
            warehouse_orchestrator._run_submissions_bronze_then_silver(
                context=object(), db=object(), sync_run_id="release", ciks=[1001],
                include_pagination=True, fetch_date=date(2026, 4, 25), force=False,
                load_mode="bootstrap_batch", artifact_policy="all_attachments",
                parser_policy="configured_forms", release_mode=True,
                required_accessions={"required-proxy", "required-13f"},
            )

        self.assertEqual(
            artifact_pipeline.call_args.kwargs["accession_numbers"],
            ["required-proxy", "required-13f"],
        )
        self.assertTrue(artifact_pipeline.call_args.kwargs["release_mode"])

    def test_release_submission_flow_seeds_index_only_candidate_for_direct_accession_fetch(self) -> None:
        class IndexOnlyDb:
            def __init__(self) -> None:
                self.filings: dict[str, dict] = {}
                self.merged: list[dict] = []

            def get_filing(self, accession_number: str):
                return self.filings.get(accession_number)

            def merge_filings(self, rows: list[dict], sync_run_id: str) -> int:
                self.merged.extend(rows)
                self.filings.update({row["accession_number"]: row for row in rows})
                return len(rows)

        db = IndexOnlyDb()

        with (
            patch.object(
                warehouse_orchestrator,
                "_capture_submission_bronze_snapshot",
                return_value={"cik": 1001, "raw_writes": []},
            ),
            patch.object(
                warehouse_orchestrator,
                "_apply_submission_snapshot_to_silver",
                return_value={
                    "rows_written": 0,
                    "rows_skipped": 0,
                    "recent_accessions": [],
                    "pagination_accessions": [],
                },
            ),
            patch.object(
                warehouse_orchestrator,
                "_run_configured_form_artifact_pipeline",
                return_value={"raw_writes": [], "rows_written": 0, "rows_skipped": 0},
            ) as artifact_pipeline,
        ):
            warehouse_orchestrator._run_submissions_bronze_then_silver(
                context=object(),
                db=db,
                sync_run_id="release",
                ciks=[1001],
                include_pagination=True,
                fetch_date=date(2026, 4, 25),
                force=False,
                load_mode="bootstrap_batch",
                artifact_policy="all_attachments",
                parser_policy="branch_b_deferred",
                release_mode=True,
                required_accessions={"index-only-13f"},
                required_candidate_rows={
                    "index-only-13f": {
                        "accession_number": "index-only-13f",
                        "cik": 1001,
                        "form": "13F-HR",
                        "filing_date": date(2013, 8, 14),
                        "report_date": None,
                        "items": None,
                    }
                },
            )

        self.assertEqual(db.merged[0]["accession_number"], "index-only-13f")
        self.assertEqual(db.merged[0]["form"], "13F-HR")
        self.assertEqual(
            artifact_pipeline.call_args.kwargs["accession_numbers"],
            ["index-only-13f"],
        )

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
                accession_numbers=["ownership-1", "generic-1", "adv-1", "proxy-1",
                                   "item-502", "ambiguous-8k", "earnings-8k", "13f-1",
                                   "ownership-1"],
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
                ("artifact", "proxy-1"),
                ("parser", "proxy-1"),
                ("artifact", "item-502"),
                ("parser", "item-502"),
                ("artifact", "ambiguous-8k"),
                ("parser", "ambiguous-8k"),
                ("artifact", "13f-1"),
                ("parser", "13f-1"),
            ],
        )
        self.assertEqual(result["rows_written"], 24)
        self.assertEqual(len(result["raw_writes"]), 6)

    def test_release_artifact_pipeline_fails_closed(self) -> None:
        with patch(
            "edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts",
            side_effect=RuntimeError("missing artifact"),
        ):
            with self.assertRaisesRegex(Exception, "ownership-1"):
                warehouse_orchestrator._run_configured_form_artifact_pipeline(
                    context=SimpleNamespace(identity="tester@example.com"),
                    db=_ConfiguredFormDb(), sync_run_id="release",
                    accession_numbers=["ownership-1"],
                    artifact_policy="all_attachments", parser_policy="configured_forms",
                    force=False, release_mode=True,
                )

    def test_release_artifact_pipeline_retries_transient_timeout_per_accession(self) -> None:
        refresh_result = {
            "raw_writes": [{"source_name": "filing_document"}],
            "attachment_count": 1,
            "network_fetches": 0,
        }
        with (
            patch(
                "edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts",
                side_effect=[TimeoutError(), refresh_result],
            ) as refresh,
            patch("time.sleep") as sleep,
        ):
            result = warehouse_orchestrator._run_configured_form_artifact_pipeline(
                context=SimpleNamespace(identity="tester@example.com"),
                db=_ConfiguredFormDb(),
                sync_run_id="release",
                accession_numbers=["13f-1"],
                artifact_policy="all_attachments",
                parser_policy="branch_b_deferred",
                force=False,
                release_mode=True,
            )

        self.assertEqual(refresh.call_count, 2)
        sleep.assert_called_once_with(1.0)
        self.assertEqual(result["candidate_outcomes"][0]["accession_number"], "13f-1")

    def test_release_artifact_pipeline_retries_http_client_pool_timeout(self) -> None:
        class PoolTimeout(Exception):
            pass

        refresh_result = {
            "raw_writes": [{"source_name": "filing_document"}],
            "attachment_count": 1,
            "network_fetches": 0,
        }
        with (
            patch(
                "edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts",
                side_effect=[PoolTimeout(), refresh_result],
            ) as refresh,
            patch("edgar.httpclient.close_clients") as close_clients,
            patch("time.sleep") as sleep,
        ):
            result = warehouse_orchestrator._run_configured_form_artifact_pipeline(
                context=SimpleNamespace(identity="tester@example.com"),
                db=_ConfiguredFormDb(),
                sync_run_id="release",
                accession_numbers=["13f-1"],
                artifact_policy="all_attachments",
                parser_policy="branch_b_deferred",
                force=False,
                release_mode=True,
            )

        self.assertEqual(refresh.call_count, 2)
        close_clients.assert_called_once_with()
        sleep.assert_called_once_with(1.0)
        self.assertEqual(result["candidate_outcomes"][0]["accession_number"], "13f-1")

    def test_release_artifact_pipeline_busts_edgartools_filing_cache_on_content_error(self) -> None:
        """Production regression: accession 0000009631-13-000012.

        `edgar.get_by_accession_number` resolves via `get_filing_by_accession`, which
        is `@cache_except_none`-wrapped -- once it returns a Filing whose SGML fetch
        degraded to the homepage fallback (TransientFilingContentError), that *same*
        cached Filing instance is replayed on every retry within the process, so all
        3 attempts failed identically in production even though a fresh process
        fetching the same accession moments later succeeded cleanly. The retry loop
        must evict this cache (`get_filing_by_accession.cache_clear()`) before
        retrying, not just sleep and hope for a different result from the same object.
        """
        from edgar_warehouse.bronze_filing_artifacts import TransientFilingContentError

        refresh_result = {
            "raw_writes": [{"source_name": "filing_document"}],
            "attachment_count": 1,
            "network_fetches": 0,
        }
        with (
            patch(
                "edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts",
                side_effect=[TransientFilingContentError("no document_type"), refresh_result],
            ) as refresh,
            patch("edgar._filings.get_filing_by_accession.cache_clear") as cache_clear,
            patch("time.sleep") as sleep,
        ):
            result = warehouse_orchestrator._run_configured_form_artifact_pipeline(
                context=SimpleNamespace(identity="tester@example.com"),
                db=_ConfiguredFormDb(),
                sync_run_id="release",
                accession_numbers=["13f-1"],
                artifact_policy="all_attachments",
                parser_policy="branch_b_deferred",
                force=False,
                release_mode=True,
            )

        self.assertEqual(refresh.call_count, 2)
        cache_clear.assert_called_once_with()
        sleep.assert_called_once_with(1.0)
        self.assertEqual(result["candidate_outcomes"][0]["accession_number"], "13f-1")

    def test_release_artifact_pipeline_retries_transient_filing_content_error(self) -> None:
        """Production regression: accession 0000950123-19-003980.

        edgartools' SGML fetch got HTML/XML back from SEC and silently degraded to a
        single "complete submission text file" pseudo-attachment with no document_type
        instead of raising -- `_map_edgartools_attachments` now raises
        `TransientFilingContentError` for that shape, which must be classified as
        retryable the same way ReadTimeout/PoolTimeout are, rather than reaching
        `merge_filing_attachments`'s required-field check as a fatal ValueError.
        """
        from edgar_warehouse.bronze_filing_artifacts import TransientFilingContentError

        refresh_result = {
            "raw_writes": [{"source_name": "filing_document"}],
            "attachment_count": 1,
            "network_fetches": 0,
        }
        with (
            patch(
                "edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts",
                side_effect=[TransientFilingContentError("no document_type"), refresh_result],
            ) as refresh,
            patch("time.sleep") as sleep,
        ):
            result = warehouse_orchestrator._run_configured_form_artifact_pipeline(
                context=SimpleNamespace(identity="tester@example.com"),
                db=_ConfiguredFormDb(),
                sync_run_id="release",
                accession_numbers=["13f-1"],
                artifact_policy="all_attachments",
                parser_policy="branch_b_deferred",
                force=False,
                release_mode=True,
            )

        self.assertEqual(refresh.call_count, 2)
        sleep.assert_called_once_with(1.0)
        self.assertEqual(result["candidate_outcomes"][0]["accession_number"], "13f-1")

    def test_release_artifact_pipeline_does_not_retry_deterministic_failure(self) -> None:
        with patch(
            "edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts",
            side_effect=ValueError("invalid filing metadata"),
        ) as refresh:
            with self.assertRaisesRegex(Exception, "13f-1"):
                warehouse_orchestrator._run_configured_form_artifact_pipeline(
                    context=SimpleNamespace(identity="tester@example.com"),
                    db=_ConfiguredFormDb(),
                    sync_run_id="release",
                    accession_numbers=["13f-1"],
                    artifact_policy="all_attachments",
                    parser_policy="branch_b_deferred",
                    force=False,
                    release_mode=True,
                )

        self.assertEqual(refresh.call_count, 1)

    def test_release_artifact_pipeline_rejects_disabled_fetch_or_parser_policy(self) -> None:
        for artifact_policy, parser_policy in (
            ("none", "configured_forms"),
            ("all_attachments", "none"),
        ):
            with self.subTest(
                artifact_policy=artifact_policy, parser_policy=parser_policy
            ):
                with self.assertRaisesRegex(Exception, "requires artifact fetch and parser"):
                    warehouse_orchestrator._run_configured_form_artifact_pipeline(
                        context=SimpleNamespace(identity="tester@example.com"),
                        db=_ConfiguredFormDb(),
                        sync_run_id="release",
                        accession_numbers=["ownership-1"],
                        artifact_policy=artifact_policy,
                        parser_policy=parser_policy,
                        force=False,
                        release_mode=True,
                    )

    def test_release_artifact_pipeline_can_defer_branch_b_parser_after_hash_capture(self) -> None:
        with (
            patch(
                "edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts",
                return_value={"raw_writes": [], "attachment_count": 1, "network_fetches": 0},
            ),
            patch.object(
                warehouse_orchestrator,
                "_run_parse_pipeline",
                side_effect=AssertionError("generic parser must not handle Branch B release forms"),
            ),
        ):
            result = warehouse_orchestrator._run_configured_form_artifact_pipeline(
                context=SimpleNamespace(identity="tester@example.com"),
                db=_ConfiguredFormDb(),
                sync_run_id="release",
                accession_numbers=["proxy-1"],
                artifact_policy="all_attachments",
                parser_policy="branch_b_deferred",
                force=False,
                release_mode=True,
            )

        self.assertEqual(result["candidate_outcomes"][0]["status"], "artifacts_loaded")

    def test_release_parse_pipeline_rejects_generic_skip(self) -> None:
        db = SimpleNamespace(
            get_filing=lambda accession: {
                "accession_number": accession, "form": "DEF 14A", "cik": 1001
            },
            start_parse_run=lambda row: None,
            complete_parse_run=lambda *args, **kwargs: None,
        )

        with self.assertRaisesRegex(Exception, "no release parser"):
            warehouse_orchestrator._run_parse_pipeline(
                db=db,
                accession_number="proxy-1",
                sync_run_id="release",
                fail_closed=True,
            )

    def test_release_batch_routes_branch_b_forms_to_their_strict_parsers(self) -> None:
        candidates = [
            SimpleNamespace(accession_number="proxy", form="DEF 14A", artifact_required=True),
            SimpleNamespace(accession_number="13f", form="13F-HR", artifact_required=True),
        ]
        with (
            patch(
                "edgar_warehouse.application.workflows.fundamentals_ingest."
                "run_bootstrap_fundamentals_per_filing",
                return_value={"candidate_outcomes": [{
                    "accession_number": "proxy", "status": "not_applicable",
                    "reason": "no_relationship_rows",
                }]},
            ),
            patch(
                "edgar_warehouse.application.workflows.fundamentals_ingest."
                "run_bootstrap_thirteenf",
                return_value={"candidate_outcomes": [{
                    "accession_number": "13f", "status": "applicable_loaded",
                    "reason": "effective_holdings_loaded",
                }]},
            ),
        ):
            outcomes = warehouse_orchestrator._run_release_branch_b_parsers(
                db=object(), ciks=[1, 9], candidates=candidates, sync_run_id="release",
            )

        self.assertEqual(outcomes["proxy"]["status"], "not_applicable")
        self.assertEqual(outcomes["13f"]["status"], "applicable_loaded")

    def test_release_force_requires_explicit_repair_manifest(self) -> None:
        with self.assertRaisesRegex(Exception, "repair manifest"):
            warehouse_orchestrator._run_configured_form_artifact_pipeline(
                context=SimpleNamespace(identity="tester@example.com"),
                db=_ConfiguredFormDb(), sync_run_id="release",
                accession_numbers=["ownership-1"],
                artifact_policy="all_attachments", parser_policy="configured_forms",
                force=True, release_mode=True,
            )

    def test_bootstrap_batch_cli_defaults_to_artifact_and_parser_policies(self) -> None:
        args = cli.build_parser().parse_args(["bootstrap-batch", "--cik-list", "1001"])

        self.assertEqual(args.artifact_policy, "all_attachments")
        self.assertEqual(args.parser_policy, "configured_forms")

    def test_bootstrap_batch_cli_accepts_bounded_release_manifests(self) -> None:
        args = cli.build_parser().parse_args([
            "bootstrap-batch",
            "--cik-list", "1001",
            "--release-mode",
            "--candidate-manifest", "s3://bucket/candidates.json",
            "--repair-manifest", "s3://bucket/repairs.json",
        ])

        self.assertTrue(args.release_mode)
        self.assertEqual(args.candidate_manifest, "s3://bucket/candidates.json")
        self.assertEqual(args.repair_manifest, "s3://bucket/repairs.json")

    def test_release_relationship_source_import_is_a_deployed_cli_command(self) -> None:
        args = cli.build_parser().parse_args([
            "ingest-relationship-sources",
            "--source-manifest", "s3://bucket/sources.json",
            "--run-id", "release-1",
        ])
        self.assertEqual(args.source_manifest, "s3://bucket/sources.json")
        self.assertEqual(args.run_id, "release-1")


if __name__ == "__main__":
    unittest.main()
