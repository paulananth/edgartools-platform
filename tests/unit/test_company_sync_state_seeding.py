from __future__ import annotations

import time

from edgar_warehouse.silver_store import SilverDatabase


def test_seed_company_sync_state_bulk_creates_new_ciks_as_bootstrap_pending(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        count = db.seed_company_sync_state_bulk([100, 200, 300])
        assert count == 3
        for cik in (100, 200, 300):
            state = db.get_company_sync_state(cik)
            assert state is not None
            assert state["tracking_status"] == "bootstrap_pending"
            assert state["last_error_message"] is None
    finally:
        db.close()


def test_seed_company_sync_state_bulk_preserves_existing_tracking_status(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.upsert_company_sync_state({"cik": 100, "tracking_status": "active"})

        db.seed_company_sync_state_bulk([100, 200])

        assert db.get_company_sync_state(100)["tracking_status"] == "active"
        assert db.get_company_sync_state(200)["tracking_status"] == "bootstrap_pending"
    finally:
        db.close()


def test_seed_company_sync_state_bulk_clears_last_error_message(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.upsert_company_sync_state(
            {"cik": 100, "tracking_status": "active", "last_error_message": "boom"}
        )

        db.seed_company_sync_state_bulk([100])

        state = db.get_company_sync_state(100)
        assert state["tracking_status"] == "active"
        assert state["last_error_message"] is None
    finally:
        db.close()


def test_seed_company_sync_state_bulk_preserves_other_columns_on_existing_rows(tmp_path) -> None:
    """Columns the per-row loop never touched (e.g. bootstrap_completed_at)
    must survive being re-seeded, matching the original loop's behavior of
    only ever writing cik/tracking_status/last_error_message."""
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.upsert_company_sync_state(
            {
                "cik": 100,
                "tracking_status": "active",
                "bootstrap_completed_at": "2026-01-01T00:00:00+00:00",
            }
        )

        db.seed_company_sync_state_bulk([100])

        state = db.get_company_sync_state(100)
        assert state["bootstrap_completed_at"] is not None
    finally:
        db.close()


def test_seed_company_sync_state_bulk_handles_duplicate_ciks_in_input(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        count = db.seed_company_sync_state_bulk([100, 100, 200])
        assert count == 2
        assert db.get_company_sync_state(100) is not None
        assert db.get_company_sync_state(200) is not None
    finally:
        db.close()


def test_seed_company_sync_state_bulk_empty_input_is_a_noop(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        assert db.seed_company_sync_state_bulk([]) == 0
    finally:
        db.close()


def test_seed_company_sync_state_bulk_is_fast_at_realistic_ticker_snapshot_volume(tmp_path) -> None:
    """Regression guard: company_tickers.json commonly holds ~10-20K rows.
    Before this fix, seeding sec_company_sync_state was a per-CIK read +
    write loop -- measured live as a silent ~2m20s gap in _sync_reference_data.
    Bulk-staged, this should complete in well under a second regardless of
    CIK count.
    """
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        ciks = list(range(1, 15001))
        started_at = time.monotonic()
        count = db.seed_company_sync_state_bulk(ciks)
        elapsed = time.monotonic() - started_at

        assert count == 15000
        assert elapsed < 5.0, f"seed_company_sync_state_bulk took {elapsed:.2f}s for {count} CIKs"
    finally:
        db.close()
