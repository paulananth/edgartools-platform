"""silver-merge-engine-migration Ticket 06e: company tickers and filing text
are landing-only.

No production code reads either table back from the local store in the same
run: `seed-universe`'s later readers, MDM and the filing-text sweep all read
Snowflake silver. The dbt silver models collapse the landing rows on the old
keys, `(cik, ticker, source_name)` and `(accession_number, text_version)`.
The local per-`source_name` DELETE never reached landing; a ticker dropping
out of a snapshot is a Silver Landing Retirement Record's job.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from edgar_warehouse.silver_store import SilverDatabase
from tests.support.silver_rows import open_landing_db


@pytest.fixture()
def db(tmp_path):
    database = open_landing_db(tmp_path)
    try:
        yield database
    finally:
        database.close()


def _local_count(database: SilverDatabase, table: str) -> int:
    return database.fetch(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]


# ------------------------------------------------------------------
# sec_company_ticker
# ------------------------------------------------------------------


def test_tickers_land_with_sync_stamp_and_never_touch_local_duckdb(db):
    count = db.replace_company_tickers(
        [{"cik": 320193, "ticker": "AAPL", "exchange": "Nasdaq"}],
        "run-1",
        source_name="company_tickers",
    )

    assert count == 1
    (recorded,) = db.landing_export.tables()["sec_company_ticker"]
    assert isinstance(recorded.pop("last_synced_at"), datetime)
    assert recorded == {
        "cik": 320193,
        "ticker": "AAPL",
        "exchange": "Nasdaq",
        "source_name": "company_tickers",
        "source_rank": 1,
        "last_sync_run_id": "run-1",
    }
    assert _local_count(db, "sec_company_ticker") == 0


def test_tickers_skip_rows_without_cik_or_ticker_and_rank_counts_every_input_row(db):
    count = db.replace_company_tickers(
        [
            {"cik": None, "ticker": "AAPL"},
            {"cik": 320193, "ticker": ""},
            {"cik": 1, "exchange": "NYSE"},
            {"cik": 789019, "ticker": "MSFT", "exchange": "Nasdaq"},
        ],
        "run-1",
    )

    assert count == 1
    recorded = db.landing_export.tables()["sec_company_ticker"]
    assert [(row["cik"], row["ticker"], row["source_rank"]) for row in recorded] == [(789019, "MSFT", 4)]
    assert recorded[0]["source_name"] == "company_tickers_exchange"


def test_tickers_in_one_call_share_one_last_synced_at(db):
    db.replace_company_tickers(
        [{"cik": 1, "ticker": "A"}, {"cik": 2, "ticker": "B"}],
        "run-1",
    )

    recorded = db.landing_export.tables()["sec_company_ticker"]
    assert recorded[0]["last_synced_at"] == recorded[1]["last_synced_at"]


def test_tickers_carry_cause_reference_only_when_given(db):
    db.replace_company_tickers([{"cik": 1, "ticker": "A"}], "run-1", cause_reference="decision-1")
    db.replace_company_tickers([{"cik": 2, "ticker": "B"}], "run-2")

    first, second = db.landing_export.tables()["sec_company_ticker"]
    assert first["cause_reference"] == "decision-1"
    assert "cause_reference" not in second


def test_tickers_row_supplied_stamp_columns_are_overridden(db):
    db.replace_company_tickers(
        [{"cik": 1, "ticker": "A", "source_name": "stale", "source_rank": 99, "last_sync_run_id": "stale"}],
        "run-1",
        source_name="company_tickers",
    )

    recorded = db.landing_export.tables()["sec_company_ticker"][0]
    assert (recorded["source_name"], recorded["source_rank"], recorded["last_sync_run_id"]) == (
        "company_tickers",
        1,
        "run-1",
    )


def test_tickers_repeat_snapshot_records_both_and_deletes_nothing(db):
    db.replace_company_tickers(
        [{"cik": 1, "ticker": "A"}, {"cik": 2, "ticker": "B"}], "run-1", source_name="company_tickers"
    )
    db.replace_company_tickers([{"cik": 1, "ticker": "A"}], "run-2", source_name="company_tickers")

    recorded = db.landing_export.tables()["sec_company_ticker"]
    assert [(row["cik"], row["last_sync_run_id"]) for row in recorded] == [(1, "run-1"), (2, "run-1"), (1, "run-2")]
    assert _local_count(db, "sec_company_ticker") == 0


def test_tickers_empty_input_records_nothing(db):
    assert db.replace_company_tickers([], "run-1") == 0
    assert db.landing_export.total_row_count() == 0


def test_tickers_without_a_landing_buffer_write_nothing_locally(tmp_path):
    database = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        assert database.replace_company_tickers([{"cik": 1, "ticker": "A"}], "run-1") == 1
        assert _local_count(database, "sec_company_ticker") == 0
    finally:
        database.close()


# ------------------------------------------------------------------
# sec_filing_text
# ------------------------------------------------------------------


def _filing_text(**overrides):
    base = {
        "accession_number": "0000320193-25-000050",
        "text_version": "generic_text_v1",
        "source_document_name": "doc.htm",
        "text_storage_path": "s3://warehouse/text/doc.txt",
        "text_sha256": "sha-text",
        "char_count": 42,
        "extracted_at": datetime(2025, 1, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return base


def test_filing_text_lands_as_given_and_never_touches_local_duckdb(db):
    row = _filing_text()

    db.upsert_filing_text(row)

    assert db.landing_export.tables()["sec_filing_text"] == [row]
    assert _local_count(db, "sec_filing_text") == 0


def test_filing_text_without_a_landing_buffer_writes_nothing_locally(tmp_path):
    database = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        database.upsert_filing_text(_filing_text())
        assert _local_count(database, "sec_filing_text") == 0
    finally:
        database.close()


@pytest.mark.parametrize(
    "field",
    [
        "accession_number",
        "text_version",
        "source_document_name",
        "text_storage_path",
        "text_sha256",
        "char_count",
        "extracted_at",
    ],
)
def test_filing_text_missing_required_field_raises_before_recording(db, field):
    with pytest.raises(ValueError, match=field):
        db.upsert_filing_text(_filing_text(**{field: None}))

    assert db.landing_export.total_row_count() == 0
