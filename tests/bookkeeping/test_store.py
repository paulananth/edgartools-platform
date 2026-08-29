"""Tests for BookkeepingStore (DuckDB Retirement Cutover Ticket 02).

Uses an in-memory SQLite store (schema via Base.metadata.create_all),
matching the existing MDM test convention (tests/mdm/test_relationship_coverage.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from edgar_warehouse.bookkeeping.store import BookkeepingStore


def _now() -> datetime:
    return datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)


# -- sec_source_checkpoint --------------------------------------------------


class TestSourceCheckpoint:
    def test_upsert_then_get(self, store: BookkeepingStore) -> None:
        store.upsert_source_checkpoint(
            {
                "source_name": "submissions_main",
                "source_key": "cik:320193",
                "raw_object_id": "obj-1",
                "bronze_path": "s3://bucket/obj-1",
            }
        )
        row = store.get_source_checkpoint("submissions_main", "cik:320193")
        assert row is not None
        assert row["raw_object_id"] == "obj-1"
        assert row["bronze_path"] == "s3://bucket/obj-1"

    def test_upsert_overwrites_on_conflict(self, store: BookkeepingStore) -> None:
        store.upsert_source_checkpoint(
            {"source_name": "s", "source_key": "k", "raw_object_id": "first"}
        )
        store.upsert_source_checkpoint(
            {"source_name": "s", "source_key": "k", "raw_object_id": "second"}
        )
        row = store.get_source_checkpoint("s", "k")
        assert row["raw_object_id"] == "second"

    def test_get_missing_returns_none(self, store: BookkeepingStore) -> None:
        assert store.get_source_checkpoint("nope", "nope") is None


# -- sec_company_sync_state --------------------------------------------------


class TestCompanySyncState:
    def test_upsert_then_get(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 320193, "tracking_status": "active"})
        row = store.get_company_sync_state(320193)
        assert row["tracking_status"] == "active"

    def test_upsert_coalesces_non_status_fields(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state(
            {"cik": 1, "tracking_status": "active", "last_main_sha256": "abc"}
        )
        # A subsequent upsert with last_main_sha256 omitted must NOT wipe it --
        # COALESCE keeps the existing value when the new one is NULL.
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "paused"})
        row = store.get_company_sync_state(1)
        assert row["last_main_sha256"] == "abc"
        assert row["tracking_status"] == "paused"  # status is a hard overwrite

    def test_upsert_hard_overwrites_last_error_message(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state(
            {"cik": 1, "tracking_status": "active", "last_error_message": "boom"}
        )
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        row = store.get_company_sync_state(1)
        assert row["last_error_message"] is None

    def test_seed_bulk_new_ciks_get_bootstrap_pending(self, store: BookkeepingStore) -> None:
        n = store.seed_company_sync_state_bulk([1, 2, 3])
        assert n == 3
        for cik in (1, 2, 3):
            row = store.get_company_sync_state(cik)
            assert row["tracking_status"] == "bootstrap_pending"

    def test_seed_bulk_dedupes_and_preserves_existing_status(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        n = store.seed_company_sync_state_bulk([1, 1, 2])
        assert n == 2  # deduped input count
        assert store.get_company_sync_state(1)["tracking_status"] == "active"
        assert store.get_company_sync_state(2)["tracking_status"] == "bootstrap_pending"

    def test_seed_bulk_clears_last_error_message_on_existing_row(
        self, store: BookkeepingStore
    ) -> None:
        store.upsert_company_sync_state(
            {"cik": 1, "tracking_status": "active", "last_error_message": "boom"}
        )
        store.seed_company_sync_state_bulk([1])
        assert store.get_company_sync_state(1)["last_error_message"] is None

    def test_seed_bulk_empty_input(self, store: BookkeepingStore) -> None:
        assert store.seed_company_sync_state_bulk([]) == 0

    def test_get_tracked_ciks_default_active(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        store.upsert_company_sync_state({"cik": 2, "tracking_status": "paused"})
        assert store.get_tracked_ciks("active") == [1]

    def test_get_tracked_ciks_comma_separated(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        store.upsert_company_sync_state({"cik": 2, "tracking_status": "bootstrap_pending"})
        store.upsert_company_sync_state({"cik": 3, "tracking_status": "paused"})
        assert store.get_tracked_ciks("active,bootstrap_pending") == [1, 2]

    def test_get_tracked_ciks_all(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        store.upsert_company_sync_state({"cik": 2, "tracking_status": "paused"})
        assert store.get_tracked_ciks("all") == [1, 2]

    def test_get_ciks_with_bronze(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        store.upsert_company_sync_state({"cik": 2, "tracking_status": "active"})
        store.upsert_source_checkpoint(
            {"source_name": "submissions_main", "source_key": "cik:1"}
        )
        rows = store.get_ciks_with_bronze("all")
        assert rows == [{"cik": 1}]

    def test_get_ciks_with_bronze_filtered_by_status(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        store.upsert_company_sync_state({"cik": 2, "tracking_status": "paused"})
        store.upsert_source_checkpoint({"source_name": "submissions_main", "source_key": "cik:1"})
        store.upsert_source_checkpoint({"source_name": "submissions_main", "source_key": "cik:2"})
        assert store.get_ciks_with_bronze("active") == [{"cik": 1}]


# -- discovery_checkpoint -----------------------------------------------------


class TestDiscoveryCheckpoint:
    def test_claim_then_get(self, store: BookkeepingStore) -> None:
        claimed = store.claim_discovery_ciks(
            [1, 2], discovery_source="daily", run_id="run-1", claimed_at=_now()
        )
        assert claimed == [1, 2]
        row = store.get_discovery_checkpoint("cik", "1")
        assert row["status"] == "in_progress"
        assert row["run_id"] == "run-1"

    def test_claim_dedupes_input(self, store: BookkeepingStore) -> None:
        claimed = store.claim_discovery_ciks(
            [1, 1, 2], discovery_source="daily", run_id="run-1", claimed_at=_now()
        )
        assert claimed == [1, 2]

    def test_claim_skips_cik_in_progress_under_different_run(self, store: BookkeepingStore) -> None:
        store.claim_discovery_ciks([1], discovery_source="daily", run_id="run-1", claimed_at=_now())
        claimed = store.claim_discovery_ciks(
            [1], discovery_source="daily", run_id="run-2", claimed_at=_now()
        )
        assert claimed == []
        assert store.get_discovery_checkpoint("cik", "1")["run_id"] == "run-1"

    def test_claim_allows_same_run_to_reclaim(self, store: BookkeepingStore) -> None:
        store.claim_discovery_ciks([1], discovery_source="daily", run_id="run-1", claimed_at=_now())
        claimed = store.claim_discovery_ciks(
            [1], discovery_source="daily", run_id="run-1", claimed_at=_now()
        )
        assert claimed == [1]

    def test_finish_marks_status(self, store: BookkeepingStore) -> None:
        store.claim_discovery_ciks([1], discovery_source="daily", run_id="run-1", claimed_at=_now())
        store.finish_discovery_ciks(
            [1], discovery_source="daily", run_id="run-1", status="succeeded", finished_at=_now()
        )
        row = store.get_discovery_checkpoint("cik", "1")
        assert row["status"] == "succeeded"
        assert row["finished_at"] is not None

    def test_get_missing_returns_none(self, store: BookkeepingStore) -> None:
        assert store.get_discovery_checkpoint("cik", "999") is None


# -- pipeline_run_lease -------------------------------------------------------


class TestPipelineRunLease:
    def test_acquire_fresh_lease_succeeds(self, store: BookkeepingStore) -> None:
        won = store.acquire_pipeline_run_lease(
            lease_name="daily_identity_refresh", run_id="run-1", mode="daily", acquired_at=_now()
        )
        assert won is True
        row = store.get_pipeline_run_lease("daily_identity_refresh")
        assert row["status"] == "held"
        assert row["run_id"] == "run-1"

    def test_acquire_already_held_by_other_run_fails(self, store: BookkeepingStore) -> None:
        store.acquire_pipeline_run_lease(
            lease_name="L", run_id="run-1", mode="daily", acquired_at=_now()
        )
        won = store.acquire_pipeline_run_lease(
            lease_name="L", run_id="run-2", mode="daily", acquired_at=_now()
        )
        assert won is False
        row = store.get_pipeline_run_lease("L")
        assert row["run_id"] == "run-1"  # unchanged -- run-2 did not win

    def test_acquire_reclaims_stale_lease(self, store: BookkeepingStore) -> None:
        old_time = _now()
        store.acquire_pipeline_run_lease(
            lease_name="L", run_id="run-1", mode="daily", acquired_at=old_time, stale_after_seconds=10
        )
        later = old_time + timedelta(seconds=20)
        won = store.acquire_pipeline_run_lease(
            lease_name="L", run_id="run-2", mode="daily", acquired_at=later, stale_after_seconds=10
        )
        assert won is True
        assert store.get_pipeline_run_lease("L")["run_id"] == "run-2"

    def test_release_only_by_holder(self, store: BookkeepingStore) -> None:
        store.acquire_pipeline_run_lease(
            lease_name="L", run_id="run-1", mode="daily", acquired_at=_now()
        )
        # A non-holder's release is a no-op.
        store.release_pipeline_run_lease(lease_name="L", run_id="run-2", released_at=_now())
        assert store.get_pipeline_run_lease("L")["status"] == "held"

        store.release_pipeline_run_lease(lease_name="L", run_id="run-1", released_at=_now())
        row = store.get_pipeline_run_lease("L")
        assert row["status"] == "idle"
        assert row["released_at"] is not None

    def test_release_backstop_mode_clears_overdue(self, store: BookkeepingStore) -> None:
        store.acquire_pipeline_run_lease(
            lease_name="L", run_id="run-1", mode="backstop", acquired_at=_now()
        )
        store.mark_pipeline_run_lease_backstop_overdue(lease_name="L")
        assert store.get_pipeline_run_lease("L")["backstop_overdue"] is True
        store.release_pipeline_run_lease(lease_name="L", run_id="run-1", released_at=_now())
        assert store.get_pipeline_run_lease("L")["backstop_overdue"] is False

    def test_release_daily_mode_never_clears_overdue(self, store: BookkeepingStore) -> None:
        store.acquire_pipeline_run_lease(
            lease_name="L", run_id="run-1", mode="daily", acquired_at=_now()
        )
        store.mark_pipeline_run_lease_backstop_overdue(lease_name="L")
        store.release_pipeline_run_lease(lease_name="L", run_id="run-1", released_at=_now())
        assert store.get_pipeline_run_lease("L")["backstop_overdue"] is True

    def test_get_missing_returns_none(self, store: BookkeepingStore) -> None:
        assert store.get_pipeline_run_lease("nope") is None


# -- sec_parse_run --------------------------------------------------------


class TestParseRun:
    def test_start_then_get(self, store: BookkeepingStore) -> None:
        store.start_parse_run(
            {
                "parse_run_id": "p1",
                "parser_name": "ownership",
                "parser_version": "1.0",
                "target_form_family": "3-4-5",
            }
        )
        row = store.get_parse_run("p1")
        assert row["status"] == "running"
        assert row["parser_name"] == "ownership"

    def test_start_requires_fields(self, store: BookkeepingStore) -> None:
        import pytest

        with pytest.raises(ValueError):
            store.start_parse_run({"parse_run_id": "p1"})

    def test_complete_sets_terminal_status(self, store: BookkeepingStore) -> None:
        store.start_parse_run(
            {
                "parse_run_id": "p1",
                "parser_name": "ownership",
                "parser_version": "1.0",
                "target_form_family": "3-4-5",
            }
        )
        store.complete_parse_run("p1", status="succeeded", rows_written=42)
        row = store.get_parse_run("p1")
        assert row["status"] == "succeeded"
        assert row["rows_written"] == 42
        assert row["completed_at"] is not None

    def test_complete_coalesces_rows_written_when_omitted(self, store: BookkeepingStore) -> None:
        store.start_parse_run(
            {
                "parse_run_id": "p1",
                "parser_name": "ownership",
                "parser_version": "1.0",
                "target_form_family": "3-4-5",
                "rows_written": 10,
            }
        )
        store.complete_parse_run("p1", status="failed")
        assert store.get_parse_run("p1")["rows_written"] == 10

    def test_complete_requires_parse_run_id(self, store: BookkeepingStore) -> None:
        import pytest

        with pytest.raises(ValueError):
            store.complete_parse_run("")


# -- sec_sync_run ------------------------------------------------------------


class TestSyncRun:
    def test_start_then_get(self, store: BookkeepingStore) -> None:
        store.start_sync_run({"sync_run_id": "s1", "sync_mode": "daily", "scope_type": "full"})
        row = store.get_sync_run("s1")
        assert row["status"] == "running"

    def test_complete_hard_overwrites_row_counts(self, store: BookkeepingStore) -> None:
        store.start_sync_run({"sync_run_id": "s1", "sync_mode": "daily", "scope_type": "full"})
        store.complete_sync_run("s1", status="succeeded", rows_inserted=5)
        store.complete_sync_run("s1", status="succeeded")  # omits rows_inserted this time
        row = store.get_sync_run("s1")
        assert row["rows_inserted"] is None  # hard overwrite, no COALESCE


# -- pipeline_run --------------------------------------------------------------


class TestPipelineRun:
    def test_start_then_get(self, store: BookkeepingStore) -> None:
        store.start_pipeline_run(
            {
                "pipeline_run_id": "pr1",
                "command_name": "daily_incremental",
                "runtime_mode": "bronze_capture",
                "started_at": _now(),
                "status": "running",
                "arguments": {"x": 1},
            }
        )
        row = store.get_pipeline_run("pr1")
        assert row["command_name"] == "daily_incremental"
        assert row["arguments_json"] == '{"x": 1}'

    def test_restart_resets_completion_fields(self, store: BookkeepingStore) -> None:
        store.start_pipeline_run(
            {
                "pipeline_run_id": "pr1",
                "command_name": "daily_incremental",
                "runtime_mode": "bronze_capture",
                "started_at": _now(),
                "status": "running",
            }
        )
        store.complete_pipeline_run(
            "pr1", status="succeeded", writes=[{"a": 1}], raw_writes=[], metrics={"n": 1}
        )
        assert store.get_pipeline_run("pr1")["status"] == "succeeded"

        # Restarting the same pipeline_run_id must wipe completion state.
        store.start_pipeline_run(
            {
                "pipeline_run_id": "pr1",
                "command_name": "daily_incremental",
                "runtime_mode": "bronze_capture",
                "started_at": _now(),
                "status": "running",
            }
        )
        row = store.get_pipeline_run("pr1")
        assert row["status"] == "running"
        assert row["completed_at"] is None
        assert row["writes_json"] is None
        assert row["metrics_json"] is None

    def test_record_pipeline_verification(self, store: BookkeepingStore) -> None:
        store.start_pipeline_run(
            {
                "pipeline_run_id": "pr1",
                "command_name": "daily_incremental",
                "runtime_mode": "bronze_capture",
                "started_at": _now(),
                "status": "running",
            }
        )
        store.record_pipeline_verification(
            "pr1", verification_status="passed", report={"ok": True}
        )
        row = store.get_pipeline_run("pr1")
        assert row["verification_status"] == "passed"
        assert row["last_verified_at"] is not None


# -- gold_manifest --------------------------------------------------------------


class TestGoldManifest:
    def test_first_entry_reports_parquet_changed_true(self, store: BookkeepingStore) -> None:
        store.record_gold_manifest(
            run_id="run-1",
            command_name="gold-refresh",
            entries=[
                {
                    "table_name": "company",
                    "storage_layer": "gold",
                    "relative_path": "company.parquet",
                    "row_count": 100,
                    "parquet_sha256": "abc",
                }
            ],
        )
        rows = store.get_gold_manifest("run-1")
        assert len(rows) == 1
        assert rows[0]["parquet_changed"] is True
        assert rows[0]["row_count_delta"] is None
        assert rows[0]["previous_run_id"] is None

    def test_second_run_computes_delta_against_previous(self, store: BookkeepingStore) -> None:
        store.record_gold_manifest(
            run_id="run-1",
            command_name="gold-refresh",
            entries=[
                {
                    "table_name": "company",
                    "storage_layer": "gold",
                    "relative_path": "company.parquet",
                    "row_count": 100,
                    "parquet_sha256": "abc",
                }
            ],
        )
        store.record_gold_manifest(
            run_id="run-2",
            command_name="gold-refresh",
            entries=[
                {
                    "table_name": "company",
                    "storage_layer": "gold",
                    "relative_path": "company.parquet",
                    "row_count": 150,
                    "parquet_sha256": "def",
                }
            ],
        )
        rows = store.get_gold_manifest("run-2")
        assert rows[0]["row_count_delta"] == 50
        assert rows[0]["parquet_changed"] is True
        assert rows[0]["previous_run_id"] == "run-1"

    def test_unchanged_parquet_reports_parquet_changed_false(self, store: BookkeepingStore) -> None:
        entry = {
            "table_name": "company",
            "storage_layer": "gold",
            "relative_path": "company.parquet",
            "row_count": 100,
            "parquet_sha256": "abc",
        }
        store.record_gold_manifest(run_id="run-1", command_name="gold-refresh", entries=[entry])
        store.record_gold_manifest(run_id="run-2", command_name="gold-refresh", entries=[entry])
        rows = store.get_gold_manifest("run-2")
        assert rows[0]["parquet_changed"] is False
        assert rows[0]["row_count_delta"] == 0

    def test_get_all_manifests_when_run_id_none(self, store: BookkeepingStore) -> None:
        store.record_gold_manifest(
            run_id="run-1",
            command_name="gold-refresh",
            entries=[
                {
                    "table_name": "company",
                    "storage_layer": "gold",
                    "relative_path": "company.parquet",
                    "row_count": 1,
                    "parquet_sha256": "a",
                }
            ],
        )
        assert len(store.get_gold_manifest()) == 1


# -- stg_daily_index_filing / sec_daily_index_checkpoint ----------------------


class TestDailyIndexFiling:
    def test_merge_inserts_rows(self, store: BookkeepingStore) -> None:
        rows = [
            {
                "business_date": "2026-08-28",
                "accession_number": "0001-1",
                "form": "10-K",
                "cik": 1,
                "row_ordinal": 1,
            },
            {
                "business_date": "2026-08-28",
                "accession_number": "0001-2",
                "form": "8-K",
                "cik": 2,
                "row_ordinal": 2,
            },
        ]
        n = store.merge_daily_index_filings(rows, sync_run_id="sync-1")
        assert n == 2
        fetched = store.get_daily_index_filings("2026-08-28")
        assert len(fetched) == 2
        assert fetched[0]["accession_number"] == "0001-1"

    def test_merge_dedupes_same_key_keeping_last_occurrence(self, store: BookkeepingStore) -> None:
        rows = [
            {"business_date": "2026-08-28", "accession_number": "0001-1", "form": "10-K"},
            {"business_date": "2026-08-28", "accession_number": "0001-1", "form": "10-K/A"},
        ]
        store.merge_daily_index_filings(rows, sync_run_id="sync-1")
        fetched = store.get_daily_index_filings("2026-08-28")
        assert len(fetched) == 1
        assert fetched[0]["form"] == "10-K/A"  # last occurrence (highest seq) wins

    def test_merge_upserts_across_calls(self, store: BookkeepingStore) -> None:
        row = {"business_date": "2026-08-28", "accession_number": "0001-1", "form": "10-K"}
        store.merge_daily_index_filings([row], sync_run_id="sync-1")
        updated = {"business_date": "2026-08-28", "accession_number": "0001-1", "form": "10-K/A"}
        store.merge_daily_index_filings([updated], sync_run_id="sync-2")
        fetched = store.get_daily_index_filings("2026-08-28")
        assert len(fetched) == 1
        assert fetched[0]["form"] == "10-K/A"
        assert fetched[0]["sync_run_id"] == "sync-2"

    def test_merge_empty_rows(self, store: BookkeepingStore) -> None:
        assert store.merge_daily_index_filings([], sync_run_id="sync-1") == 0

    def test_upsert_checkpoint_then_get(self, store: BookkeepingStore) -> None:
        store.upsert_daily_index_checkpoint(
            {
                "business_date": "2026-08-28",
                "source_key": "k",
                "source_url": "https://example.com",
                "expected_available_at": _now(),
            }
        )
        row = store.get_daily_index_checkpoint("2026-08-28")
        assert row["status"] == "pending"
        assert row["attempt_count"] == 1

    def test_upsert_checkpoint_increments_attempt_count(self, store: BookkeepingStore) -> None:
        base = {
            "business_date": "2026-08-28",
            "source_key": "k",
            "source_url": "https://example.com",
            "expected_available_at": _now(),
        }
        store.upsert_daily_index_checkpoint(base)
        store.upsert_daily_index_checkpoint(base)
        row = store.get_daily_index_checkpoint("2026-08-28")
        assert row["attempt_count"] == 2

    def test_upsert_checkpoint_first_attempt_at_is_sticky(self, store: BookkeepingStore) -> None:
        first_attempt = _now()
        store.upsert_daily_index_checkpoint(
            {
                "business_date": "2026-08-28",
                "source_key": "k",
                "source_url": "https://example.com",
                "expected_available_at": _now(),
                "first_attempt_at": first_attempt,
            }
        )
        later_attempt = first_attempt + timedelta(hours=1)
        store.upsert_daily_index_checkpoint(
            {
                "business_date": "2026-08-28",
                "source_key": "k",
                "source_url": "https://example.com",
                "expected_available_at": _now(),
                "first_attempt_at": later_attempt,
            }
        )
        row = store.get_daily_index_checkpoint("2026-08-28")
        # SQLite's TIMESTAMP storage doesn't round-trip tzinfo (a test-fixture
        # limitation of SQLite, not the store's COALESCE logic -- Postgres's
        # real timestamptz preserves it) -- compare naive values.
        assert row["first_attempt_at"].replace(tzinfo=None) == first_attempt.replace(
            tzinfo=None
        )  # stays the original, not the later_attempt value

    def test_get_last_successful_checkpoint_date(self, store: BookkeepingStore) -> None:
        store.upsert_daily_index_checkpoint(
            {
                "business_date": "2026-08-26",
                "source_key": "k",
                "source_url": "u",
                "expected_available_at": _now(),
                "status": "succeeded",
            }
        )
        store.upsert_daily_index_checkpoint(
            {
                "business_date": "2026-08-27",
                "source_key": "k",
                "source_url": "u",
                "expected_available_at": _now(),
                "status": "succeeded",
            }
        )
        store.upsert_daily_index_checkpoint(
            {
                "business_date": "2026-08-28",
                "source_key": "k",
                "source_url": "u",
                "expected_available_at": _now(),
                "status": "pending",
            }
        )
        assert store.get_last_successful_checkpoint_date() == "2026-08-27"

    def test_get_last_successful_checkpoint_date_none(self, store: BookkeepingStore) -> None:
        assert store.get_last_successful_checkpoint_date() is None

    def test_get_pending_checkpoint_dates(self, store: BookkeepingStore) -> None:
        for d, status in [
            ("2026-08-25", "pending"),
            ("2026-08-26", "failed_retryable"),
            ("2026-08-27", "succeeded"),
            ("2026-08-29", "pending"),
        ]:
            store.upsert_daily_index_checkpoint(
                {
                    "business_date": d,
                    "source_key": "k",
                    "source_url": "u",
                    "expected_available_at": _now(),
                    "status": status,
                }
            )
        assert store.get_pending_checkpoint_dates("2026-08-28") == ["2026-08-25", "2026-08-26"]


# -- sec_reconcile_finding -----------------------------------------------------


class TestReconcileFinding:
    def test_insert_then_get(self, store: BookkeepingStore) -> None:
        n = store.insert_reconcile_findings(
            [
                {
                    "reconcile_run_id": "r1",
                    "cik": 1,
                    "scope_type": "full",
                    "object_type": "filing",
                    "object_key": "0001",
                    "drift_type": "hash_mismatch",
                }
            ]
        )
        assert n == 1
        rows = store.get_reconcile_findings("r1")
        assert len(rows) == 1
        assert rows[0]["severity"] == "medium"
        assert rows[0]["status"] == "detected"

    def test_upsert_overwrites_on_conflict(self, store: BookkeepingStore) -> None:
        base = {
            "reconcile_run_id": "r1",
            "cik": 1,
            "scope_type": "full",
            "object_type": "filing",
            "object_key": "0001",
            "drift_type": "hash_mismatch",
        }
        store.insert_reconcile_findings([base])
        store.insert_reconcile_findings([{**base, "status": "resolved"}])
        rows = store.get_reconcile_findings("r1")
        assert len(rows) == 1
        assert rows[0]["status"] == "resolved"


# -- get_table_counts (narrow, 11-table version) -------------------------------


class TestTableCounts:
    def test_counts_all_11_tables(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        counts = store.get_table_counts()
        assert len(counts) == 11
        assert counts["sec_company_sync_state"] == 1
        assert counts["sec_reconcile_finding"] == 0
