"""Regression tests for merge_adv_filings/merge_adv_private_funds' bulk-upsert conversion.

Both used to run one execute() per row in a Python loop -- the same known-slow
pattern already fixed for sec_company_filing in merge_filings (~93% of
per-batch time there). Discovered here when a real production
ingest-relationship-sources run over a 13-month advFilingData rolling window
(~55K filing rows, ~384K fund rows) took many minutes with zero progress.
Converted to the same staged-bulk pattern. Unlike merge_filings, every
non-PK column in both ADV tables is mutable (last-write-wins) -- there are no
"first-insert-wins" columns to pin down here.
"""

from __future__ import annotations

from edgar_warehouse.silver_store import SilverDatabase


def _filing_row(**overrides):
    base = {
        "accession_number": "iapd-adv:2115188",
        "cik": None,
        "form": "ADV",
        "adviser_name": "PNC WEALTH",
        "sec_file_number": "801-66195",
        "crd_number": "129052",
        "effective_date": "2026-06-24",
        "filing_status": "effective",
        "filing_action": "current_compilation",
        "source_format": "iapd_bulk_csv",
        "parser_version": "iapd_bulk_v1",
    }
    base.update(overrides)
    return base


def _fund_row(**overrides):
    base = {
        "accession_number": "iapd-adv:2115188",
        "fund_index": 1,
        "filing_id": "2115188",
        "adviser_crd_number": "129052",
        "private_fund_id": "805-123",
        "reference_id": "518607",
        "schedule_section": "7B1",
        "reporting_role": "detailed_reporter",
        "filing_action": "current_compilation",
        "fund_name": "ALPHA FUND",
        "fund_type": "Private Equity Fund",
        "jurisdiction": "Delaware / United States",
        "aum_amount": None,
        "effective_date": "2026-06-24",
        "source_dataset_period": "2026-06",
        "source_sha256": "abc123",
        "parser_version": "iapd_bulk_v1",
    }
    base.update(overrides)
    return base


def test_merge_adv_filings_inserts_new_rows(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        rows = [
            _filing_row(accession_number="iapd-adv:1", crd_number="111"),
            _filing_row(accession_number="iapd-adv:2", crd_number="222"),
        ]
        count = db.merge_adv_filings(rows, sync_run_id="run-1")
        assert count == 2

        stored = db.fetch(
            "SELECT accession_number, crd_number FROM sec_adv_filing ORDER BY accession_number"
        )
        assert [r["accession_number"] for r in stored] == ["iapd-adv:1", "iapd-adv:2"]
        assert [r["crd_number"] for r in stored] == ["111", "222"]
    finally:
        db.close()


def test_merge_adv_filings_updates_mutable_columns_on_second_call(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.merge_adv_filings(
            [_filing_row(accession_number="iapd-adv:1", adviser_name="OLD NAME")],
            sync_run_id="run-1",
        )
        db.merge_adv_filings(
            [_filing_row(accession_number="iapd-adv:1", adviser_name="NEW NAME")],
            sync_run_id="run-2",
        )

        stored = db.fetch(
            "SELECT adviser_name, last_sync_run_id FROM sec_adv_filing WHERE accession_number = 'iapd-adv:1'"
        )
        assert stored[0]["adviser_name"] == "NEW NAME"
        assert stored[0]["last_sync_run_id"] == "run-2"
    finally:
        db.close()


def test_merge_adv_filings_dedupes_same_accession_within_one_call(tmp_path):
    """A firm's amendment within the same monthly archive can produce two rows
    for the same FilingID -- the bulk QUALIFY dedup must keep this correct
    (last occurrence wins), not raise a duplicate-key error or drop data."""
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        rows = [
            _filing_row(accession_number="iapd-adv:1", adviser_name="FIRST"),
            _filing_row(accession_number="iapd-adv:1", adviser_name="SECOND"),
        ]
        count = db.merge_adv_filings(rows, sync_run_id="run-1")
        assert count == 2

        stored = db.fetch(
            "SELECT adviser_name FROM sec_adv_filing WHERE accession_number = 'iapd-adv:1'"
        )
        assert len(stored) == 1
        assert stored[0]["adviser_name"] == "SECOND"
    finally:
        db.close()


def test_merge_adv_filings_empty_rows_is_noop(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        count = db.merge_adv_filings([], sync_run_id="run-1")
        assert count == 0
    finally:
        db.close()


def test_merge_adv_private_funds_inserts_new_rows(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        rows = [
            _fund_row(accession_number="iapd-adv:1", fund_index=1, private_fund_id="805-1"),
            _fund_row(accession_number="iapd-adv:1", fund_index=2, private_fund_id="805-2"),
        ]
        count = db.merge_adv_private_funds(rows, sync_run_id="run-1")
        assert count == 2

        stored = db.fetch(
            "SELECT fund_index, private_fund_id FROM sec_adv_private_fund "
            "WHERE accession_number = 'iapd-adv:1' ORDER BY fund_index"
        )
        assert [r["fund_index"] for r in stored] == [1, 2]
        assert [r["private_fund_id"] for r in stored] == ["805-1", "805-2"]
    finally:
        db.close()


def test_merge_adv_private_funds_updates_mutable_columns_on_second_call(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.merge_adv_private_funds(
            [_fund_row(accession_number="iapd-adv:1", fund_index=1, fund_name="OLD FUND")],
            sync_run_id="run-1",
        )
        db.merge_adv_private_funds(
            [_fund_row(accession_number="iapd-adv:1", fund_index=1, fund_name="NEW FUND")],
            sync_run_id="run-2",
        )

        stored = db.fetch(
            "SELECT fund_name, last_sync_run_id FROM sec_adv_private_fund "
            "WHERE accession_number = 'iapd-adv:1' AND fund_index = 1"
        )
        assert stored[0]["fund_name"] == "NEW FUND"
        assert stored[0]["last_sync_run_id"] == "run-2"
    finally:
        db.close()


def test_merge_adv_private_funds_dedupes_same_key_within_one_call(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        rows = [
            _fund_row(accession_number="iapd-adv:1", fund_index=1, fund_name="FIRST"),
            _fund_row(accession_number="iapd-adv:1", fund_index=1, fund_name="SECOND"),
        ]
        count = db.merge_adv_private_funds(rows, sync_run_id="run-1")
        assert count == 2

        stored = db.fetch(
            "SELECT fund_name FROM sec_adv_private_fund "
            "WHERE accession_number = 'iapd-adv:1' AND fund_index = 1"
        )
        assert len(stored) == 1
        assert stored[0]["fund_name"] == "SECOND"
    finally:
        db.close()


def test_merge_adv_private_funds_empty_rows_is_noop(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        count = db.merge_adv_private_funds([], sync_run_id="run-1")
        assert count == 0
    finally:
        db.close()
