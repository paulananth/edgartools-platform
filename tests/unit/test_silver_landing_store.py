"""SilverLandingStore (silver-merge-engine-migration Ticket 14) is the write
path with no database behind it: writers record to the landing export, and
same-run reads of the in-run lookup tables (ADR 0011) come from those rows.
SilverDatabase subclasses it only to keep DuckDB alive until Ticket 17.
"""

from __future__ import annotations

import pytest

from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.silver_landing_store import SilverLandingStore
from edgar_warehouse.silver_store import SilverDatabase


@pytest.fixture()
def store():
    store = SilverLandingStore(landing_export=LandingExportBuffer())
    try:
        yield store
    finally:
        store.close()


def test_writer_records_to_the_landing_export_without_a_database(store):
    n = store.merge_company([{"cik": 320193, "entity_name": "Apple Inc"}], "run-1")
    assert n == 1
    recorded = store.landing_export.tables()["sec_company"]
    assert recorded[0]["cik"] == 320193
    assert recorded[0]["last_sync_run_id"] == "run-1"
    assert not hasattr(store, "_conn")


def test_same_run_filing_read_answers_from_recorded_rows(store):
    store.merge_filings([{"accession_number": "0001-25-000001", "cik": 1, "form": "10-K"}], "r")
    row = store.get_filing("0001-25-000001")
    assert row["cik"] == 1 and row["form"] == "10-K"
    assert store.get_filing("0001-25-000002") is None


def test_missing_not_null_column_raises_before_recording(store):
    with pytest.raises(ValueError, match="NOT NULL"):
        store.merge_filings([{"cik": 1}], "r")
    assert store.landing_export.total_row_count() == 0


def test_no_landing_export_records_nothing():
    store = SilverLandingStore()
    assert store.merge_company([{"cik": 1, "entity_name": "x"}], "r") == 1
    assert store.landing_export is None


def test_silver_database_is_a_silver_landing_store(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=LandingExportBuffer())
    try:
        assert isinstance(db, SilverLandingStore)
        db.merge_company([{"cik": 1, "entity_name": "x"}], "r")
        assert db.landing_export.row_count("sec_company") == 1
    finally:
        db.close()
