from __future__ import annotations

import time
from datetime import date

from edgar_warehouse.silver_store import SilverDatabase


def _row(*, business_date: date, accession: str, form: str = "8-K", cik: int = 1) -> dict[str, object]:
    return {
        "sync_run_id": "test-run",
        "raw_object_id": "raw-1",
        "source_name": "daily_form_index",
        "source_url": "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260728.idx",
        "business_date": business_date,
        "source_year": business_date.year,
        "source_quarter": ((business_date.month - 1) // 3) + 1,
        "row_ordinal": 1,
        "form": form,
        "company_name": "Test Co",
        "cik": cik,
        "filing_date": business_date,
        "file_name": f"edgar/data/{cik}/{accession}.txt",
        "accession_number": accession,
        "filing_txt_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt",
        "record_hash": f"hash-{accession}",
    }


def test_merge_daily_index_filings_upsert_updates_existing_row(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        business_date = date(2026, 7, 28)
        row = _row(business_date=business_date, accession="0000000001-26-000001", form="8-K")
        assert db.merge_daily_index_filings([row], "run-1") == 1

        updated_row = dict(row)
        updated_row["form"] = "8-K/A"
        assert db.merge_daily_index_filings([updated_row], "run-2") == 1

        rows = db.get_daily_index_filings(business_date.isoformat())
        assert len(rows) == 1
        assert rows[0]["form"] == "8-K/A"
        assert rows[0]["sync_run_id"] == "run-2"
    finally:
        db.close()


def test_merge_daily_index_filings_batches_thousands_of_rows_in_one_transaction(tmp_path) -> None:
    """Regression guard for the unbatched-per-row bug: a real SEC daily
    index file commonly holds ~6,000 rows. Before this fix, each row was a
    separately-executed, separately-autocommitted INSERT (measured 53s for
    6,028 rows live in prod). Staged via a registered Arrow table and
    applied as one set-based upsert (measured ~0.02-0.12s for 3,000 rows
    locally), this should complete in well under a second regardless of
    row count.
    """
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        business_date = date(2026, 7, 28)
        row_count = 3000
        rows = [
            _row(business_date=business_date, accession=f"0000000001-26-{i:06d}", cik=i)
            for i in range(row_count)
        ]

        started_at = time.monotonic()
        result = db.merge_daily_index_filings(rows, "run-1")
        elapsed = time.monotonic() - started_at

        assert result == row_count
        assert len(db.get_daily_index_filings(business_date.isoformat())) == row_count
        # Unbatched autocommit would take ~15-25s for this many rows; batched
        # should be well under 1s. 5s leaves generous CI headroom while still
        # failing hard if the transaction wrap regresses.
        assert elapsed < 5.0, f"merge_daily_index_filings took {elapsed:.2f}s for {row_count} rows"
    finally:
        db.close()
