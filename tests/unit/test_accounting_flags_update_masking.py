"""Ticket 42: backfill_accounting_flags's success counter previously counted
any UPDATE call that didn't raise, even when it matched zero rows (DuckDB's
UPDATE against no matching rows doesn't raise). Real prod evidence: 129
"updates" reported for Apple, 0 actual sec_accounting_flag rows written --
because the upstream base-row-creation step (a separate, structural gap in
parse_entity_facts, out of scope here) never ran. Regression-tests the fix:
update_accounting_flag_scores now reports whether a row actually matched,
and backfill_accounting_flags only counts real matches.
"""

from __future__ import annotations

from edgar_warehouse.parsers.accounting_flags import backfill_accounting_flags
from edgar_warehouse.silver_store import SilverDatabase


def test_update_accounting_flag_scores_reports_no_match_when_row_missing(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    matched = db.update_accounting_flag_scores(
        cik=320193,
        accession_number="0000320193-24-000001",
        beneish_m_score=-2.5,
        altman_z_score=6.0,
        piotroski_f_score=7,
    )
    assert matched is False


def test_update_accounting_flag_scores_reports_match_when_row_exists(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    db.merge_accounting_flags(
        [
            {
                "cik": 320193,
                "accession_number": "0000320193-24-000001",
                "fiscal_year": 2024,
            }
        ],
        sync_run_id="test-run",
    )
    matched = db.update_accounting_flag_scores(
        cik=320193,
        accession_number="0000320193-24-000001",
        beneish_m_score=-2.5,
        altman_z_score=6.0,
        piotroski_f_score=7,
    )
    assert matched is True
    row = db.fetch(
        "SELECT beneish_m_score, altman_z_score, piotroski_f_score "
        "FROM sec_accounting_flag WHERE cik = ? AND accession_number = ?",
        [320193, "0000320193-24-000001"],
    )[0]
    assert row["beneish_m_score"] == -2.5
    assert row["altman_z_score"] == 6.0
    assert row["piotroski_f_score"] == 7


def test_backfill_accounting_flags_does_not_count_missing_base_rows(tmp_path) -> None:
    """The exact live scenario: sec_financial_derived has FY rows (so the
    cross-period loop runs), but no sec_accounting_flag base rows exist yet
    (the structural companyfacts DEI gap) -- updated must be 0, not a
    silently-inflated count of no-op attempts."""
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    db._conn.execute(
        """
        INSERT INTO sec_financial_derived
            (cik, accession_number, fiscal_year, fiscal_period, period_end, form_type,
             revenue, gross_profit, net_income, total_assets, total_liabilities,
             total_equity, parser_version)
        VALUES
            (320193, '0000320193-23-000001', 2023, 'FY', '2023-09-30', '10-K',
             383285000000, 169148000000, 96995000000, 352583000000, 290437000000,
             62146000000, 'test'),
            (320193, '0000320193-24-000001', 2024, 'FY', '2024-09-28', '10-K',
             391035000000, 180683000000, 93736000000, 364980000000, 308030000000,
             56950000000, 'test')
        """
    )
    # Deliberately no sec_accounting_flag rows -- reproduces the live gap.

    updated = backfill_accounting_flags(320193, db)

    assert updated == 0
    total_flag_rows = db.fetch("SELECT COUNT(*) AS n FROM sec_accounting_flag")[0]["n"]
    assert total_flag_rows == 0


def test_backfill_accounting_flags_counts_only_real_matches(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    db._conn.execute(
        """
        INSERT INTO sec_financial_derived
            (cik, accession_number, fiscal_year, fiscal_period, period_end, form_type,
             revenue, gross_profit, net_income, total_assets, total_liabilities,
             total_equity, parser_version)
        VALUES
            (320193, '0000320193-23-000001', 2023, 'FY', '2023-09-30', '10-K',
             383285000000, 169148000000, 96995000000, 352583000000, 290437000000,
             62146000000, 'test'),
            (320193, '0000320193-24-000001', 2024, 'FY', '2024-09-28', '10-K',
             391035000000, 180683000000, 93736000000, 364980000000, 308030000000,
             56950000000, 'test')
        """
    )
    # Only one of the two accessions has a base sec_accounting_flag row.
    db.merge_accounting_flags(
        [{"cik": 320193, "accession_number": "0000320193-24-000001", "fiscal_year": 2024}],
        sync_run_id="test-run",
    )

    updated = backfill_accounting_flags(320193, db)

    assert updated == 1
