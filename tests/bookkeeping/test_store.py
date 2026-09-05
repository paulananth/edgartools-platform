"""Tests for BookkeepingStore (DuckDB Retirement Cutover Ticket 02).

Uses an in-memory SQLite store (schema via Base.metadata.create_all),
matching the existing MDM test convention (tests/mdm/test_relationship_coverage.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from edgar_warehouse.bookkeeping.models import PipelineRun
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

    def test_get_bulk_returns_by_cik(self, store: BookkeepingStore) -> None:
        store.upsert_source_checkpoint(
            {"source_name": "submissions_main", "source_key": "cik:1", "raw_object_id": "obj-1"}
        )
        store.upsert_source_checkpoint(
            {"source_name": "submissions_main", "source_key": "cik:2", "raw_object_id": "obj-2"}
        )
        result = store.get_source_checkpoints_bulk("submissions_main", [1, 2, 3])
        assert set(result) == {1, 2}
        assert result[1]["raw_object_id"] == "obj-1"
        assert result[2]["raw_object_id"] == "obj-2"

    def test_get_bulk_empty_input(self, store: BookkeepingStore) -> None:
        assert store.get_source_checkpoints_bulk("submissions_main", []) == {}

    def test_upsert_bulk_then_get(self, store: BookkeepingStore) -> None:
        store.upsert_source_checkpoints_bulk(
            [
                {"source_name": "submissions_main", "source_key": "cik:1", "raw_object_id": "obj-1"},
                {"source_name": "submissions_main", "source_key": "cik:2", "raw_object_id": "obj-2"},
            ]
        )
        assert store.get_source_checkpoint("submissions_main", "cik:1")["raw_object_id"] == "obj-1"
        assert store.get_source_checkpoint("submissions_main", "cik:2")["raw_object_id"] == "obj-2"

    def test_upsert_bulk_overwrites_on_conflict(self, store: BookkeepingStore) -> None:
        store.upsert_source_checkpoints_bulk(
            [{"source_name": "s", "source_key": "k", "raw_object_id": "first"}]
        )
        store.upsert_source_checkpoints_bulk(
            [{"source_name": "s", "source_key": "k", "raw_object_id": "second"}]
        )
        assert store.get_source_checkpoint("s", "k")["raw_object_id"] == "second"

    def test_upsert_bulk_empty_input(self, store: BookkeepingStore) -> None:
        store.upsert_source_checkpoints_bulk([])  # must not raise

    def test_bulk_batches_round_trips_not_one_per_cik(
        self, store: BookkeepingStore, session: Session, monkeypatch
    ) -> None:
        """Regression guard for the live 2026-09-04 finding (change-
        propagation "diff processing design" follow-up): the original
        get_source_checkpoint/upsert_source_checkpoint pair, called once per
        CIK inside _apply_submission_snapshot_to_silver with no batching,
        measured 2640.99s (44m01s) of pure round-trip latency for 8,699
        CIKs where nothing had changed -- same shape as
        claim_discovery_ciks'/seed_company_sync_state_bulk_if_missing's own
        prior fixes, just a third, previously-unbatched pair."""
        from sqlalchemy import event

        monkeypatch.setattr(BookkeepingStore, "_COMPANY_SYNC_STATE_BULK_CHUNK_SIZE", 10)
        engine = session.get_bind()
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _capture)
        try:
            ciks = list(range(1, 251))  # 250 CIKs, chunk size 10 -> 25 chunks
            store.upsert_source_checkpoints_bulk(
                [
                    {"source_name": "submissions_main", "source_key": f"cik:{cik}", "raw_object_id": "x"}
                    for cik in ciks
                ]
            )
            statements.clear()
            result = store.get_source_checkpoints_bulk("submissions_main", ciks)
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

        assert len(result) == 250
        # 25 chunked SELECTs -- not 250 (one round trip per CIK, what the
        # original get_source_checkpoint-per-call loop cost).
        assert len(statements) <= 30, (
            f"expected ~25 batched SELECTs (25 read chunks for 250 CIKs at "
            f"chunk size 10), got {len(statements)} -- get_source_checkpoints_bulk "
            "may have regressed to one round trip per CIK"
        )
        assert len(statements) < len(ciks)


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

    def test_get_states_bulk_returns_by_cik(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        store.upsert_company_sync_state({"cik": 2, "tracking_status": "paused"})
        result = store.get_company_sync_states_bulk([1, 2, 3])
        assert set(result) == {1, 2}
        assert result[1]["tracking_status"] == "active"
        assert result[2]["tracking_status"] == "paused"

    def test_get_states_bulk_empty_input(self, store: BookkeepingStore) -> None:
        assert store.get_company_sync_states_bulk([]) == {}

    def test_upsert_states_bulk_then_get(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_states_bulk(
            [
                {"cik": 1, "tracking_status": "active"},
                {"cik": 2, "tracking_status": "paused"},
            ]
        )
        assert store.get_company_sync_state(1)["tracking_status"] == "active"
        assert store.get_company_sync_state(2)["tracking_status"] == "paused"

    def test_upsert_states_bulk_coalesces_non_status_fields(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_states_bulk(
            [{"cik": 1, "tracking_status": "active", "last_main_sha256": "abc"}]
        )
        # Same COALESCE contract as the single-row upsert_company_sync_state:
        # an omitted field on a later upsert must not wipe the existing value.
        store.upsert_company_sync_states_bulk([{"cik": 1, "tracking_status": "paused"}])
        row = store.get_company_sync_state(1)
        assert row["last_main_sha256"] == "abc"
        assert row["tracking_status"] == "paused"

    def test_upsert_states_bulk_empty_input(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_states_bulk([])  # must not raise

    def test_states_bulk_batches_round_trips_not_one_per_cik(
        self, store: BookkeepingStore, session: Session, monkeypatch
    ) -> None:
        """Sibling regression guard to TestSourceCheckpoint's own bulk test
        above -- same 2026-09-04 finding, the other half of the same
        4-round-trip-per-CIK cost inside _apply_submission_snapshot_to_silver."""
        from sqlalchemy import event

        monkeypatch.setattr(BookkeepingStore, "_COMPANY_SYNC_STATE_BULK_CHUNK_SIZE", 10)
        engine = session.get_bind()
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _capture)
        try:
            ciks = list(range(1, 251))
            store.upsert_company_sync_states_bulk(
                [{"cik": cik, "tracking_status": "active"} for cik in ciks]
            )
            statements.clear()
            result = store.get_company_sync_states_bulk(ciks)
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

        assert len(result) == 250
        assert len(statements) <= 30
        assert len(statements) < len(ciks)

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

    def test_seed_if_missing_new_ciks_get_caller_supplied_status(
        self, store: BookkeepingStore
    ) -> None:
        n = store.seed_company_sync_state_bulk_if_missing([1, 2, 3], tracking_status="active")
        assert n == 3
        for cik in (1, 2, 3):
            assert store.get_company_sync_state(cik)["tracking_status"] == "active"

    def test_seed_if_missing_leaves_existing_row_completely_untouched(
        self, store: BookkeepingStore
    ) -> None:
        """Unlike seed_company_sync_state_bulk (which always clears
        last_error_message on conflict), seed_company_sync_state_bulk_if_missing
        must leave an already-tracked CIK's row byte-for-byte alone --
        including last_error_message -- since it exists to preserve
        _seed_silver_tracking_status's original per-row loop's exact
        "existing rows keep their current status" behavior."""
        store.upsert_company_sync_state(
            {"cik": 1, "tracking_status": "paused", "last_error_message": "boom"}
        )
        store.seed_company_sync_state_bulk_if_missing([1, 2], tracking_status="active")
        row1 = store.get_company_sync_state(1)
        assert row1["tracking_status"] == "paused"
        assert row1["last_error_message"] == "boom"
        assert store.get_company_sync_state(2)["tracking_status"] == "active"

    def test_seed_if_missing_dedupes_input(self, store: BookkeepingStore) -> None:
        n = store.seed_company_sync_state_bulk_if_missing([1, 1, 2], tracking_status="active")
        assert n == 2

    def test_seed_if_missing_empty_input(self, store: BookkeepingStore) -> None:
        assert store.seed_company_sync_state_bulk_if_missing([], tracking_status="active") == 0

    def test_seed_if_missing_batches_round_trips_not_one_per_cik(
        self, store: BookkeepingStore, session: Session, monkeypatch
    ) -> None:
        """Regression guard for the live 2026-09-03 incident (found alongside
        the claim_discovery_ciks fix in the same daily_incremental
        investigation): the original _seed_silver_tracking_status issued one
        SELECT + one conditional INSERT per CIK, with no batching -- its own
        multi-minute stall sitting immediately before claim_discovery_ciks in
        the same call chain, at the same ~9,205-CIK real prod scale."""
        from sqlalchemy import event

        monkeypatch.setattr(BookkeepingStore, "_COMPANY_SYNC_STATE_BULK_CHUNK_SIZE", 10)
        engine = session.get_bind()
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _capture)
        try:
            ciks = list(range(1, 251))  # 250 CIKs, chunk size 10 -> 25 chunks
            n = store.seed_company_sync_state_bulk_if_missing(ciks, tracking_status="active")
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

        assert n == 250
        # 25 chunked INSERT...ON CONFLICT DO NOTHING statements -- not 250
        # (one SELECT + one INSERT per CIK, what the original per-row loop cost).
        assert len(statements) <= 30, (
            f"expected ~25 batched statements (25 insert chunks for 250 CIKs "
            f"at chunk size 10), got {len(statements)} -- "
            "seed_company_sync_state_bulk_if_missing may have regressed to "
            "one round trip per CIK"
        )
        assert len(statements) < len(ciks)

    def test_demote_bulk_overwrites_status(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        n = store.demote_company_sync_state_bulk([1, 2], demoted_at=_now())
        assert n == 2
        assert store.get_company_sync_state(1)["tracking_status"] == "deregistered"
        assert store.get_company_sync_state(2)["tracking_status"] == "deregistered"

    def test_demote_bulk_dedupes_input(self, store: BookkeepingStore) -> None:
        n = store.demote_company_sync_state_bulk([1, 1, 2], demoted_at=_now())
        assert n == 2

    def test_demote_bulk_empty_input(self, store: BookkeepingStore) -> None:
        assert store.demote_company_sync_state_bulk([], demoted_at=_now()) == 0

    def test_demote_bulk_batches_round_trips_not_one_per_cik(
        self, store: BookkeepingStore, session: Session, monkeypatch
    ) -> None:
        from sqlalchemy import event

        monkeypatch.setattr(BookkeepingStore, "_COMPANY_SYNC_STATE_BULK_CHUNK_SIZE", 10)
        engine = session.get_bind()
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _capture)
        try:
            ciks = list(range(1, 251))
            n = store.demote_company_sync_state_bulk(ciks, demoted_at=_now())
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

        assert n == 250
        assert len(statements) <= 30
        assert len(statements) < len(ciks)

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

    def test_claim_preserves_input_order_and_skips_only_blocked_ciks(
        self, store: BookkeepingStore
    ) -> None:
        """A mixed batch (some CIKs blocked by a concurrent different run,
        most free) must claim exactly the free ones, in their original
        relative order -- proving the batched SELECT-then-filter-then-bulk-
        upsert rewrite preserves the original per-row loop's exact claim
        semantics, not just its net claimed-count."""
        store.claim_discovery_ciks([2, 4], discovery_source="daily", run_id="run-1", claimed_at=_now())
        claimed = store.claim_discovery_ciks(
            [1, 2, 3, 4, 5], discovery_source="daily", run_id="run-2", claimed_at=_now()
        )
        assert claimed == [1, 3, 5]
        assert store.get_discovery_checkpoint("cik", "2")["run_id"] == "run-1"
        assert store.get_discovery_checkpoint("cik", "4")["run_id"] == "run-1"
        for cik in (1, 3, 5):
            assert store.get_discovery_checkpoint("cik", str(cik))["run_id"] == "run-2"

    def test_claim_batches_round_trips_not_one_per_cik(
        self, store: BookkeepingStore, session: Session, monkeypatch
    ) -> None:
        """Regression guard for the live 2026-09-03 incident: the original
        claim_discovery_ciks issued one SELECT + one INSERT per CIK, with no
        batching at all -- confirmed live as a ~36-minute silent stall on a
        9,205-CIK daily_incremental run (CloudWatch: zero log output between
        the last SEC daily-index download and the first bronze_capture_progress
        line). Chunk size is monkeypatched small so this test proves the
        chunking behavior itself without needing thousands of rows."""
        from sqlalchemy import event

        monkeypatch.setattr(BookkeepingStore, "_DISCOVERY_CLAIM_CHUNK_SIZE", 10)
        engine = session.get_bind()
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _capture)
        try:
            ciks = list(range(1, 251))  # 250 CIKs, chunk size 10 -> 25 chunks
            claimed = store.claim_discovery_ciks(
                ciks, discovery_source="daily", run_id="run-1", claimed_at=_now()
            )
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

        assert claimed == ciks
        # 25 SELECT chunks + 25 upsert chunks = 50 statements -- not 500
        # (2 round trips per CIK, what the original per-row loop cost).
        assert len(statements) <= 55, (
            f"expected ~50 batched statements (25 SELECT + 25 upsert chunks "
            f"for 250 CIKs at chunk size 10), got {len(statements)} -- "
            "claim_discovery_ciks may have regressed to one round trip per CIK"
        )
        assert len(statements) < len(ciks)

    def test_claim_skips_cik_already_succeeded_same_day_for_same_source(
        self, store: BookkeepingStore
    ) -> None:
        """Live evidence (change-propagation daily_incremental follow-up,
        2026-09-04): claim_discovery_ciks only ever blocked a CIK that was
        'in_progress' under a *different* run -- once finish_discovery_ciks
        marked a CIK 'succeeded', the very next run (even minutes later, same
        calendar day) re-claimed and fully reprocessed it. Confirmed live:
        two same-day daily_incremental runs both claimed the identical 8,699
        CIKs. This narrows Ticket 45's deliberate 'force-recheck the trailing
        seven calendar days on every run' design (still fully intact for
        anything not already succeeded *today*) without touching it -- see
        the two tests below for that boundary explicitly preserved."""
        first_run_time = datetime(2026, 8, 28, 6, 30, 0, tzinfo=timezone.utc)
        store.claim_discovery_ciks(
            [1, 2], discovery_source="daily_incremental", run_id="run-1", claimed_at=first_run_time
        )
        store.finish_discovery_ciks(
            [1, 2],
            discovery_source="daily_incremental",
            run_id="run-1",
            status="succeeded",
            finished_at=first_run_time,
        )

        second_run_time = datetime(2026, 8, 28, 15, 11, 0, tzinfo=timezone.utc)
        claimed = store.claim_discovery_ciks(
            [1, 2], discovery_source="daily_incremental", run_id="run-2", claimed_at=second_run_time
        )
        assert claimed == []
        assert store.get_discovery_checkpoint("cik", "1")["run_id"] == "run-1"

    def test_claim_skips_cik_already_succeeded_same_business_day_across_utc_midnight(
        self, store: BookkeepingStore
    ) -> None:
        """Second bug found live the same evening (2026-09-04): the fix
        above compared same-*UTC*-calendar-day, but a daily_incremental run
        at 20:41 ET is already 00:41 UTC the *next* UTC calendar date --
        confirmed live, this reclaimed and fully reprocessed the identical
        8,699 CIKs a 06:36 ET run had already succeeded on hours earlier,
        same ET business day, because the UTC-date comparison saw Sept 4 vs.
        Sept 5 and found no match. Reproduces that exact shape: a morning ET
        success (06:30 ET) and an evening ET claim (20:30 ET, same ET day)
        that crosses a UTC calendar-day boundary (Aug 28 -> Aug 29 UTC) --
        must still be blocked."""
        morning_et = datetime(2026, 8, 28, 10, 30, 0, tzinfo=timezone.utc)  # 06:30 ET
        store.claim_discovery_ciks(
            [1], discovery_source="daily_incremental", run_id="run-1", claimed_at=morning_et
        )
        store.finish_discovery_ciks(
            [1],
            discovery_source="daily_incremental",
            run_id="run-1",
            status="succeeded",
            finished_at=morning_et,
        )

        evening_et_next_utc_day = datetime(2026, 8, 29, 0, 30, 0, tzinfo=timezone.utc)  # 20:30 ET, same ET day
        claimed = store.claim_discovery_ciks(
            [1], discovery_source="daily_incremental", run_id="run-2", claimed_at=evening_et_next_utc_day
        )
        assert claimed == []
        assert store.get_discovery_checkpoint("cik", "1")["run_id"] == "run-1"

    def test_claim_reclaims_cik_succeeded_on_a_prior_calendar_day(
        self, store: BookkeepingStore
    ) -> None:
        """The 7-day recheck window (Ticket 45) must keep working: a CIK
        whose last success was a prior *business* day (US/Eastern -- see
        _as_business_date) is reclaimed normally, so a late SEC daily-index
        republish is still caught on the next day's run.

        Deliberately spans a UTC midnight *without* crossing one in ET
        (2026-08-28 02:30 UTC = Aug 27 22:30 ET; 2026-08-28 05:00 UTC = Aug
        28 01:00 ET -- both UTC Aug 28, but different ET business days) --
        this is the exact shape of the live 2026-09-04 bug (a same *UTC* day
        that should have been blocked wasn't; here, proving the reverse
        still works: a same UTC day that legitimately differs by ET business
        day still reclaims)."""
        yesterday = datetime(2026, 8, 28, 2, 30, 0, tzinfo=timezone.utc)
        store.claim_discovery_ciks(
            [1], discovery_source="daily_incremental", run_id="run-1", claimed_at=yesterday
        )
        store.finish_discovery_ciks(
            [1],
            discovery_source="daily_incremental",
            run_id="run-1",
            status="succeeded",
            finished_at=yesterday,
        )

        today = datetime(2026, 8, 28, 5, 0, 0, tzinfo=timezone.utc)
        claimed = store.claim_discovery_ciks(
            [1], discovery_source="daily_incremental", run_id="run-2", claimed_at=today
        )
        assert claimed == [1]

    def test_claim_same_day_success_only_blocks_the_same_discovery_source(
        self, store: BookkeepingStore
    ) -> None:
        """A same-day success under one discovery_source (e.g.
        daily_incremental) must not silently suppress a different source
        (e.g. bootstrap_next) from claiming the same CIK -- matches the
        existing cross-source in_progress semantics
        (test_claim_skips_cik_in_progress_under_different_run has no
        source-scoping either, so this preserves that same shape for the
        new same-day-succeeded check)."""
        run_time = _now()
        store.claim_discovery_ciks(
            [1], discovery_source="daily_incremental", run_id="run-1", claimed_at=run_time
        )
        store.finish_discovery_ciks(
            [1],
            discovery_source="daily_incremental",
            run_id="run-1",
            status="succeeded",
            finished_at=run_time,
        )

        claimed = store.claim_discovery_ciks(
            [1], discovery_source="bootstrap_next", run_id="run-2", claimed_at=run_time
        )
        assert claimed == [1]

    def test_claim_allows_the_same_run_id_to_reclaim_its_own_same_day_success(
        self, store: BookkeepingStore
    ) -> None:
        """Regression guard (found by /code-review's Spec axis): the
        class-level comment above this method has always documented 'allow
        the same run_id to reclaim' as an invariant. The same-day-succeeded
        block added for the cross-run bug above must not silently drop that
        invariant -- a run resuming or retrying under its own run_id must
        never be blocked by its own prior success, only a *different* run's
        same-day success should suppress a reclaim."""
        run_time = _now()
        store.claim_discovery_ciks(
            [1], discovery_source="daily_incremental", run_id="run-1", claimed_at=run_time
        )
        store.finish_discovery_ciks(
            [1],
            discovery_source="daily_incremental",
            run_id="run-1",
            status="succeeded",
            finished_at=run_time,
        )

        later_same_day = run_time + timedelta(hours=1)
        claimed = store.claim_discovery_ciks(
            [1], discovery_source="daily_incremental", run_id="run-1", claimed_at=later_same_day
        )
        assert claimed == [1]

    def test_claim_reclaims_a_same_day_failed_cik_normally(
        self, store: BookkeepingStore
    ) -> None:
        """The same-day-succeeded block must only ever gate status=='succeeded'
        -- a CIK a prior same-day run marked 'failed' must remain immediately
        reclaimable, same as before this fix."""
        run_time = _now()
        store.claim_discovery_ciks(
            [1], discovery_source="daily_incremental", run_id="run-1", claimed_at=run_time
        )
        store.finish_discovery_ciks(
            [1],
            discovery_source="daily_incremental",
            run_id="run-1",
            status="failed",
            finished_at=run_time,
        )

        later_same_day = run_time + timedelta(hours=1)
        claimed = store.claim_discovery_ciks(
            [1], discovery_source="daily_incremental", run_id="run-2", claimed_at=later_same_day
        )
        assert claimed == [1]


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


# -- get_table_counts (narrow, 10-table version) -------------------------------


class TestTableCounts:
    def test_counts_all_10_tables(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        counts = store.get_table_counts()
        assert len(counts) == 10
        assert counts["sec_company_sync_state"] == 1


# -- get_all_company_sync_states (Ticket 03) -----------------------------------


class TestGetAllCompanySyncStates:
    def test_returns_every_row_no_filter(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        store.upsert_company_sync_state({"cik": 2, "tracking_status": "paused"})
        store.upsert_company_sync_state({"cik": 3, "tracking_status": "bootstrap_pending"})
        rows = store.get_all_company_sync_states()
        by_cik = {row["cik"]: row["tracking_status"] for row in rows}
        assert by_cik == {1: "active", 2: "paused", 3: "bootstrap_pending"}

    def test_returns_empty_list_when_no_rows(self, store: BookkeepingStore) -> None:
        assert store.get_all_company_sync_states() == []

    def test_ordered_by_cik(self, store: BookkeepingStore) -> None:
        store.upsert_company_sync_state({"cik": 3, "tracking_status": "active"})
        store.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        store.upsert_company_sync_state({"cik": 2, "tracking_status": "active"})
        rows = store.get_all_company_sync_states()
        assert [row["cik"] for row in rows] == [1, 2, 3]


# -- get_recent_successful_pipeline_runs (Ticket 03) ---------------------------


class TestGetRecentSuccessfulPipelineRuns:
    def _start(self, store: BookkeepingStore, run_id: str, *, started_at: datetime, status: str = "running") -> None:
        store.start_pipeline_run(
            {
                "pipeline_run_id": run_id,
                "command_name": "daily_incremental",
                "runtime_mode": "bronze_capture",
                "started_at": started_at,
                "status": status,
            }
        )

    def test_filters_to_succeeded_and_ok_status_only(self, store: BookkeepingStore) -> None:
        self._start(store, "pr-succeeded", started_at=_now())
        store.complete_pipeline_run(
            "pr-succeeded", status="succeeded", writes=[], raw_writes=[],
            metrics={"silver_table_counts": {"sec_company": 5}},
        )
        self._start(store, "pr-ok", started_at=_now())
        store.complete_pipeline_run(
            "pr-ok", status="ok", writes=[], raw_writes=[],
            metrics={"silver_table_counts": {"sec_company": 6}},
        )
        self._start(store, "pr-failed", started_at=_now())
        store.complete_pipeline_run(
            "pr-failed", status="failed", writes=[], raw_writes=[],
            metrics={"silver_table_counts": {"sec_company": 7}},
        )
        rows = store.get_recent_successful_pipeline_runs()
        run_ids = {row["pipeline_run_id"] for row in rows}
        assert run_ids == {"pr-succeeded", "pr-ok"}

    def test_excludes_null_metrics_json(self, store: BookkeepingStore) -> None:
        self._start(store, "pr-no-metrics", started_at=_now())
        store.complete_pipeline_run(
            "pr-no-metrics", status="succeeded", writes=[], raw_writes=[], metrics=None
        )
        rows = store.get_recent_successful_pipeline_runs()
        assert rows == []

    def _force_completed_at(self, session: Session, run_id: str, completed_at: datetime | None) -> None:
        # complete_pipeline_run always sets completed_at and metrics_json
        # together, so "metrics_json set, completed_at NULL (or tied with
        # another row)" can't arise through the store's own write API today
        # -- but the raw SQL this method replaces defensively handles both
        # (ORDER BY completed_at DESC NULLS LAST), so construct these states
        # directly via the shared session fixture (same underlying Session
        # as `store`, per conftest.py) to prove the read side still honors
        # them, without reaching into BookkeepingStore's private _session.
        session.execute(
            update(PipelineRun).where(PipelineRun.pipeline_run_id == run_id).values(completed_at=completed_at)
        )

    def test_null_completed_at_sorts_last(self, store: BookkeepingStore, session: Session) -> None:
        self._start(store, "pr-null-completed", started_at=_now())
        store.complete_pipeline_run(
            "pr-null-completed", status="succeeded", writes=[], raw_writes=[],
            metrics={"silver_table_counts": {}},
        )
        self._force_completed_at(session, "pr-null-completed", None)

        self._start(store, "pr-with-completed", started_at=_now())
        store.complete_pipeline_run(
            "pr-with-completed", status="succeeded", writes=[], raw_writes=[],
            metrics={"silver_table_counts": {}},
        )

        rows = store.get_recent_successful_pipeline_runs()
        assert [row["pipeline_run_id"] for row in rows] == ["pr-with-completed", "pr-null-completed"]

    def test_started_at_desc_breaks_ties_when_completed_at_matches(
        self, store: BookkeepingStore, session: Session
    ) -> None:
        tied_completed_at = _now() + timedelta(hours=1)
        self._start(store, "pr-earlier", started_at=_now())
        store.complete_pipeline_run(
            "pr-earlier", status="succeeded", writes=[], raw_writes=[], metrics={"silver_table_counts": {}}
        )
        self._force_completed_at(session, "pr-earlier", tied_completed_at)

        self._start(store, "pr-later", started_at=_now() + timedelta(minutes=5))
        store.complete_pipeline_run(
            "pr-later", status="succeeded", writes=[], raw_writes=[], metrics={"silver_table_counts": {}}
        )
        self._force_completed_at(session, "pr-later", tied_completed_at)

        rows = store.get_recent_successful_pipeline_runs()
        assert [row["pipeline_run_id"] for row in rows] == ["pr-later", "pr-earlier"]

    def test_limit_is_respected(self, store: BookkeepingStore) -> None:
        for i in range(15):
            run_id = f"pr-{i}"
            self._start(store, run_id, started_at=_now() + timedelta(minutes=i))
            store.complete_pipeline_run(
                run_id, status="succeeded", writes=[], raw_writes=[],
                metrics={"silver_table_counts": {}},
            )
        rows = store.get_recent_successful_pipeline_runs(limit=5)
        assert len(rows) == 5

    def test_default_limit_is_10(self, store: BookkeepingStore) -> None:
        for i in range(15):
            run_id = f"pr-{i}"
            self._start(store, run_id, started_at=_now() + timedelta(minutes=i))
            store.complete_pipeline_run(
                run_id, status="succeeded", writes=[], raw_writes=[],
                metrics={"silver_table_counts": {}},
            )
        rows = store.get_recent_successful_pipeline_runs()
        assert len(rows) == 10


# -- has_successful_parse_run (Ticket 03) --------------------------------------


class TestHasSuccessfulParseRun:
    def _start_and_complete(
        self,
        store: BookkeepingStore,
        *,
        parse_run_id: str,
        accession_number: str,
        parser_name: str,
        parser_version: str,
        status: str,
    ) -> None:
        store.start_parse_run(
            {
                "parse_run_id": parse_run_id,
                "accession_number": accession_number,
                "parser_name": parser_name,
                "parser_version": parser_version,
                "target_form_family": "3-4-5",
            }
        )
        store.complete_parse_run(parse_run_id, status=status)

    def test_true_when_succeeded_row_matches_all_three_keys(self, store: BookkeepingStore) -> None:
        self._start_and_complete(
            store,
            parse_run_id="p1",
            accession_number="0001",
            parser_name="ownership",
            parser_version="1.0",
            status="succeeded",
        )
        assert store.has_successful_parse_run(
            accession_number="0001", parser_name="ownership", parser_version="1.0"
        ) is True

    def test_false_when_status_is_not_succeeded(self, store: BookkeepingStore) -> None:
        self._start_and_complete(
            store,
            parse_run_id="p1",
            accession_number="0001",
            parser_name="ownership",
            parser_version="1.0",
            status="failed",
        )
        assert store.has_successful_parse_run(
            accession_number="0001", parser_name="ownership", parser_version="1.0"
        ) is False

    def test_false_when_accession_number_differs(self, store: BookkeepingStore) -> None:
        self._start_and_complete(
            store,
            parse_run_id="p1",
            accession_number="0001",
            parser_name="ownership",
            parser_version="1.0",
            status="succeeded",
        )
        assert store.has_successful_parse_run(
            accession_number="0002", parser_name="ownership", parser_version="1.0"
        ) is False

    def test_false_when_parser_version_differs(self, store: BookkeepingStore) -> None:
        self._start_and_complete(
            store,
            parse_run_id="p1",
            accession_number="0001",
            parser_name="ownership",
            parser_version="1.0",
            status="succeeded",
        )
        assert store.has_successful_parse_run(
            accession_number="0001", parser_name="ownership", parser_version="2.0"
        ) is False

    def test_false_when_no_rows_at_all(self, store: BookkeepingStore) -> None:
        assert store.has_successful_parse_run(
            accession_number="0001", parser_name="ownership", parser_version="1.0"
        ) is False
