"""Regression tests for Ticket 98's authority-column bug.

Root cause (found 2026-08-05, re-investigating ticket 42's F5 fix): every
table declaring ``authority_column="ingested_at"`` in
``PROTECTED_TABLE_REGISTRY`` relied on the DDL's ``DEFAULT NOW()`` to
populate ``ingested_at`` -- but ``DEFAULT`` only applies on ``INSERT``, not
``ON CONFLICT ... DO UPDATE``. None of the merge functions' ``DO UPDATE SET``
clauses listed ``ingested_at``, so re-processing an existing row (e.g. a
genuine parser bug fix) silently kept the row's original ``ingested_at``
forever. At publish time, ``_resolve_conflict`` (silver_protection.py)
compares canonical's and the candidate's ``ingested_at`` -- identical in this
case, since neither was ever bumped -- and a tie is unconditionally
ambiguous, blocking publication even for a strictly-more-correct value.
Confirmed live: re-running the F5 scale-mismatch fix (tickets 42/97) against
already-published accessions hit exactly this wall.

Each table's merge function must now advance ``ingested_at`` on every
``DO UPDATE``, so a genuine re-processing of an existing row is
authoritative over what's already published.

sec_financial_fact/sec_financial_derived/sec_accounting_flag are no longer
covered here: their local DuckDB merge is gone (silver-merge-engine-migration
Tickets 02/03) and their landing rows carry a per-write ``ingested_at`` --
see test_fundamentals_landing_passthrough.py.
"""

from __future__ import annotations

import time

from edgar_warehouse.silver_store import SilverDatabase


def _ingested_at(db: SilverDatabase, table: str, where_sql: str, params: list) -> object:
    return db._conn.execute(
        f"SELECT ingested_at FROM {table} WHERE {where_sql}", params
    ).fetchone()[0]


def test_merge_earnings_release_bumps_ingested_at_on_update(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        row = {
            "cik": 8818, "accession_number": "acc-1", "filing_date": "2026-04-28",
            "fiscal_year": 2026, "fiscal_quarter": 1, "period_end": "2026-03-31",
            "revenue_gaap": 2298.5, "net_income_gaap": 168100000.0,
            "eps_gaap_diluted": None, "has_non_gaap": False, "has_guidance": False,
            "parser_version": "2",
        }
        db.merge_earnings_releases([row], "run-1")
        first = _ingested_at(db, "sec_earnings_release", "cik = ? AND accession_number = ?", [8818, "acc-1"])

        time.sleep(0.01)
        row["revenue_gaap"] = 2298500000.0  # corrected value, same key
        db.merge_earnings_releases([row], "run-2")
        second = _ingested_at(db, "sec_earnings_release", "cik = ? AND accession_number = ?", [8818, "acc-1"])

        assert second > first
    finally:
        db.close()


def test_merge_executive_records_bumps_ingested_at_on_update(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        row = {
            "cik": 8818, "accession_number": "acc-1", "fiscal_year": 2026,
            "exec_name": "Jane Doe", "exec_role": "CEO", "parser_version": "1",
        }
        db.merge_executive_records([row], "run-1")
        first = _ingested_at(
            db, "sec_executive_record",
            "cik = ? AND accession_number = ? AND exec_name = ?", [8818, "acc-1", "Jane Doe"],
        )

        time.sleep(0.01)
        row["exec_role"] = "CFO"
        db.merge_executive_records([row], "run-2")
        second = _ingested_at(
            db, "sec_executive_record",
            "cik = ? AND accession_number = ? AND exec_name = ?", [8818, "acc-1", "Jane Doe"],
        )

        assert second > first
    finally:
        db.close()


def test_merge_employment_events_bumps_ingested_at_on_update(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        row = {
            "accession_number": "acc-1", "event_index": 1, "cik": 8818,
            "event_type": "appointment", "person_name": "Jane Doe",
            "effective_date": "2026-01-01", "parser_version": "1",
        }
        db.merge_employment_events([row], "run-1")
        first = _ingested_at(
            db, "sec_employment_event", "accession_number = ? AND event_index = ?", ["acc-1", 1],
        )

        time.sleep(0.01)
        row["person_name"] = "John Smith"
        db.merge_employment_events([row], "run-2")
        second = _ingested_at(
            db, "sec_employment_event", "accession_number = ? AND event_index = ?", ["acc-1", 1],
        )

        assert second > first
    finally:
        db.close()


def test_merge_thirteenf_holdings_bumps_ingested_at_on_update(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        row = {
            "cik": 8818, "accession_number": "acc-1", "holding_index": 1,
            "period_of_report": "2026-03-31", "shares_held": 100.0, "parser_version": "1",
        }
        db.merge_thirteenf_holdings([row], "run-1")
        first = _ingested_at(
            db, "sec_thirteenf_holding",
            "cik = ? AND accession_number = ? AND holding_index = ?", [8818, "acc-1", 1],
        )

        time.sleep(0.01)
        row["shares_held"] = 200.0
        db.merge_thirteenf_holdings([row], "run-2")
        second = _ingested_at(
            db, "sec_thirteenf_holding",
            "cik = ? AND accession_number = ? AND holding_index = ?", [8818, "acc-1", 1],
        )

        assert second > first
    finally:
        db.close()


def test_merge_thirteenf_filings_bumps_ingested_at_on_update(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        row = {
            "accession_number": "acc-1", "cik": 8818, "period_of_report": "2026-03-31",
            "filing_date": "2026-04-15", "form": "13F-HR", "parser_version": "1",
        }
        db.merge_thirteenf_filings([row], "run-1")
        first = _ingested_at(db, "sec_thirteenf_filing", "accession_number = ?", ["acc-1"])

        time.sleep(0.01)
        row["effective_status"] = "superseded"
        db.merge_thirteenf_filings([row], "run-2")
        second = _ingested_at(db, "sec_thirteenf_filing", "accession_number = ?", ["acc-1"])

        assert second > first
    finally:
        db.close()


def test_merge_guidance_facts_bumps_ingested_at_on_update(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        row = {
            "fact_key": 1, "cik": 8818, "accession_number": "acc-1", "metric": "revenue",
            "period_type": "quarterly", "fiscal_year": 2026, "fiscal_quarter": 1,
            "as_of": "2026-04-28", "source_system": "sec_8k", "value_mid": 100.0,
            "parser_version": "1",
        }
        db.merge_guidance_facts([row], "run-1")
        first = _ingested_at(
            db, "sec_guidance_fact",
            "cik = ? AND metric = ? AND fiscal_year = ? AND fiscal_quarter = ? AND as_of = ? "
            "AND accession_number = ? AND is_non_gaap = ? AND source_system = ?",
            [8818, "revenue", 2026, 1, "2026-04-28", "acc-1", False, "sec_8k"],
        )

        time.sleep(0.01)
        row["value_mid"] = 200.0
        db.merge_guidance_facts([row], "run-2")
        second = _ingested_at(
            db, "sec_guidance_fact",
            "cik = ? AND metric = ? AND fiscal_year = ? AND fiscal_quarter = ? AND as_of = ? "
            "AND accession_number = ? AND is_non_gaap = ? AND source_system = ?",
            [8818, "revenue", 2026, 1, "2026-04-28", "acc-1", False, "sec_8k"],
        )

        assert second > first
    finally:
        db.close()
