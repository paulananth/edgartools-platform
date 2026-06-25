"""Regression tests for merge_filings' bulk-upsert conversion.

merge_filings used to run one execute() per row in a Python loop -- the
dominant cost (~93% of per-batch time, measured live) of bronze_seed_silver_gold's
BatchSilver stage when staging a CIK's full filing history. Converted to use
the same staged-bulk pattern already proven by merge_financial_facts. These
tests pin down the exact upsert semantics the row-by-row version had: mutable
columns take the last occurrence's value, "first-insert-wins" columns
(cik, act, file_number, film_number, items) are set only on first insert and
never overwritten, and rows are deduped correctly even when the same
accession_number appears more than once within a single call.
"""

from __future__ import annotations

from edgar_warehouse.silver_store import SilverDatabase


def _row(**overrides):
    base = {
        "accession_number": "0000320193-25-000050",
        "cik": 320193,
        "form": "10-K",
        "filing_date": "2025-01-01",
        "report_date": "2024-12-31",
        "acceptance_datetime": "2025-01-01T12:00:00",
        "act": "34",
        "file_number": "001-12345",
        "film_number": "25000001",
        "items": None,
        "size": 1000,
        "is_xbrl": True,
        "is_inline_xbrl": True,
        "primary_document": "doc.htm",
        "primary_doc_desc": "10-K",
    }
    base.update(overrides)
    return base


def test_merge_filings_inserts_new_rows(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        rows = [
            _row(accession_number="acc-1", cik=1),
            _row(accession_number="acc-2", cik=1, form="10-Q"),
        ]
        count = db.merge_filings(rows, sync_run_id="run-1")
        assert count == 2

        stored = db.fetch(
            "SELECT accession_number, form FROM sec_company_filing ORDER BY accession_number"
        )
        assert [r["accession_number"] for r in stored] == ["acc-1", "acc-2"]
        assert [r["form"] for r in stored] == ["10-K", "10-Q"]
    finally:
        db.close()


def test_merge_filings_updates_mutable_columns_on_second_call(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.merge_filings([_row(accession_number="acc-1", form="10-K", size=1000)], sync_run_id="run-1")
        db.merge_filings([_row(accession_number="acc-1", form="10-K/A", size=2000)], sync_run_id="run-2")

        stored = db.fetch(
            "SELECT form, size, last_sync_run_id FROM sec_company_filing WHERE accession_number = 'acc-1'"
        )
        assert stored[0]["form"] == "10-K/A"
        assert stored[0]["size"] == 2000
        assert stored[0]["last_sync_run_id"] == "run-2"
    finally:
        db.close()


def test_merge_filings_never_overwrites_first_insert_wins_columns(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.merge_filings(
            [_row(accession_number="acc-1", act="34", file_number="001-AAA", film_number="111", items="1.01")],
            sync_run_id="run-1",
        )
        # A later sync sees different act/file_number/film_number/items for the
        # same accession -- the row-by-row version never updated these columns
        # after first insert (they're excluded from ON CONFLICT DO UPDATE SET).
        db.merge_filings(
            [_row(accession_number="acc-1", act="33", file_number="002-BBB", film_number="222", items="9.99")],
            sync_run_id="run-2",
        )

        stored = db.fetch(
            "SELECT act, file_number, film_number, items FROM sec_company_filing WHERE accession_number = 'acc-1'"
        )
        assert stored[0]["act"] == "34"
        assert stored[0]["file_number"] == "001-AAA"
        assert stored[0]["film_number"] == "111"
        assert stored[0]["items"] == "1.01"
    finally:
        db.close()


def test_merge_filings_dedupes_same_accession_within_one_call(tmp_path):
    """A CIK's 'recent' filings and a pagination file can both reference the
    same accession_number in a single merge_filings call -- the bulk QUALIFY
    dedup must keep this correct (last occurrence wins for mutable columns),
    not raise a duplicate-key error or silently drop data."""
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        rows = [
            _row(accession_number="acc-1", form="10-K", size=1000),
            _row(accession_number="acc-1", form="10-K/A", size=2000),
        ]
        count = db.merge_filings(rows, sync_run_id="run-1")
        assert count == 2

        stored = db.fetch(
            "SELECT form, size FROM sec_company_filing WHERE accession_number = 'acc-1'"
        )
        assert len(stored) == 1
        assert stored[0]["form"] == "10-K/A"
        assert stored[0]["size"] == 2000
    finally:
        db.close()


def test_merge_filings_empty_rows_is_noop(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        count = db.merge_filings([], sync_run_id="run-1")
        assert count == 0
    finally:
        db.close()
