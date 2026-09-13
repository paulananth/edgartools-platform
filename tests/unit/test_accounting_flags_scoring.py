"""score_accounting_flags: in-memory forensic scoring (silver-merge-engine-
migration Ticket 03).

Replaces backfill_accounting_flags, which read sec_financial_derived back out
of local DuckDB and ran a COALESCE UPDATE against sec_accounting_flag. These
tests pin the old read-back-and-UPDATE semantics onto the pure function:

- Ticket 42: only a FY row that matches a real flag row counts as an update.
- The cross-period chain advances past a FY row with no flag row.
- COALESCE: a None score never clobbers an earlier score for the accession.
- merge_financial_derived's old ON CONFLICT split: fiscal_year/form_type
  first-seen, metrics last-seen, per (accession_number, fiscal_period,
  period_end).
- silver-retirement-integrity Ticket 04: scored rows stay complete -- every
  non-score column survives, so the dbt collapse never sees a thin row.
"""

from __future__ import annotations

from edgar_warehouse.parsers.accounting_flags import score_accounting_flags

_A23 = "0000320193-23-000106"
_A24 = "0000320193-24-000123"
_A25 = "0000320193-25-000079"
_SCORE_COLUMNS = ("beneish_m_score", "altman_z_score", "piotroski_f_score")

_APPLE_2023 = {
    "revenue": 383285000000, "gross_profit": 169148000000, "net_income": 96995000000,
    "total_assets": 352583000000, "total_liabilities": 290437000000, "total_equity": 62146000000,
}
_APPLE_2024 = {
    "revenue": 391035000000, "gross_profit": 180683000000, "net_income": 93736000000,
    "total_assets": 364980000000, "total_liabilities": 308030000000, "total_equity": 56950000000,
}


def _derived(accession, fiscal_year, *, fiscal_period="FY", period_end=None, **metrics):
    row = {
        "cik": 320193,
        "accession_number": accession,
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "period_end": period_end or f"{fiscal_year}-09-30",
        "form_type": "10-K",
    }
    row.update(metrics)
    return row


def _flag(accession, fiscal_year):
    return {
        "cik": 320193,
        "accession_number": accession,
        "fiscal_year": fiscal_year,
        "period_end": f"{fiscal_year}-09-30",
        "form_type": "10-K",
        "auditor_name": "Ernst & Young LLP",
        "auditor_pcaob_id": "42",
        "auditor_location": "San Jose, CA",
        "icfr_attestation": True,
        "auditor_changed": None,
        "beneish_m_score": None,
        "altman_z_score": None,
        "piotroski_f_score": None,
        "parser_version": "1",
    }


def _scores(row):
    return {column: row[column] for column in _SCORE_COLUMNS}


def test_no_flag_rows_scores_nothing() -> None:
    """Ticket 42's live gap: derived FY rows exist but no flag base rows --
    the count must be 0, not a count of no-op attempts."""
    scored, updated = score_accounting_flags(
        [], [_derived(_A23, 2023, **_APPLE_2023), _derived(_A24, 2024, **_APPLE_2024)]
    )

    assert scored == []
    assert updated == 0


def test_counts_only_fy_rows_that_match_a_flag_row() -> None:
    scored, updated = score_accounting_flags(
        [_flag(_A24, 2024)],
        [_derived(_A23, 2023, **_APPLE_2023), _derived(_A24, 2024, **_APPLE_2024)],
    )

    assert updated == 1
    assert scored[0]["altman_z_score"] is not None
    assert scored[0]["piotroski_f_score"] is not None


def test_prior_year_without_a_flag_row_still_feeds_cross_period_scores() -> None:
    with_prior, _ = score_accounting_flags(
        [_flag(_A24, 2024)],
        [_derived(_A23, 2023, **_APPLE_2023), _derived(_A24, 2024, **_APPLE_2024)],
    )
    without_prior, _ = score_accounting_flags(
        [_flag(_A24, 2024)], [_derived(_A24, 2024, **_APPLE_2024)]
    )

    assert with_prior[0]["beneish_m_score"] is not None
    assert without_prior[0]["beneish_m_score"] is None


def test_scored_rows_keep_every_non_score_column_and_leave_input_untouched() -> None:
    flag = _flag(_A24, 2024)
    original = dict(flag)

    scored, _ = score_accounting_flags([flag], [_derived(_A24, 2024, **_APPLE_2024)])

    assert flag == original
    assert set(scored[0]) == set(original)
    for column, value in original.items():
        if column not in _SCORE_COLUMNS:
            assert scored[0][column] == value


def test_a_later_none_score_never_overwrites_an_earlier_score() -> None:
    """Two FY rows can share an accession with different period_end (the
    derived key includes both) -- the second one's None scores must leave
    the first one's scores in place, like the old COALESCE(?, score)."""
    prior = _derived(_A23, 2023, **_APPLE_2023)
    first = _derived(_A24, 2024, period_end="2024-09-28", **_APPLE_2024)
    second = _derived(_A24, 2024, period_end="2024-06-29", revenue=1.0)

    scored, updated = score_accounting_flags([_flag(_A24, 2024)], [prior, first, second])
    expected, _ = score_accounting_flags([_flag(_A24, 2024)], [prior, first])

    assert updated == 2
    assert _scores(scored[0]) == _scores(expected[0])
    assert all(score is not None for score in _scores(scored[0]).values())


def test_duplicate_derived_key_keeps_first_seen_fiscal_year_and_last_seen_metrics() -> None:
    early = _derived(_A24, 2024, period_end="2024-09-28", **_APPLE_2023)
    late = _derived(_A24, 2030, period_end="2024-09-28", **_APPLE_2024)
    later_year = _derived(_A25, 2025, **_APPLE_2023)

    scored, _ = score_accounting_flags(
        [_flag(_A24, 2024)], [early, late, later_year]
    )
    expected, _ = score_accounting_flags(
        [_flag(_A24, 2024)], [dict(late, fiscal_year=2024), later_year]
    )

    assert _scores(scored[0]) == _scores(expected[0])
    # Ordered as 2024 (first-seen), so it is scored before 2025 with no prior year.
    assert scored[0]["beneish_m_score"] is None


def test_rows_missing_a_not_null_column_are_skipped() -> None:
    """sec_financial_derived's NOT NULL columns meant the old DuckDB
    read-back never saw such a row."""
    scored, updated = score_accounting_flags(
        [_flag(_A24, 2024)],
        [dict(_derived(_A24, 2024, **_APPLE_2024), fiscal_year=None)],
    )

    assert updated == 0
    assert all(score is None for score in _scores(scored[0]).values())


def test_non_annual_rows_are_ignored() -> None:
    scored, updated = score_accounting_flags(
        [_flag(_A24, 2024)],
        [_derived(_A24, 2024, fiscal_period="Q3", **_APPLE_2024)],
    )

    assert updated == 0
    assert all(score is None for score in _scores(scored[0]).values())


def test_rows_are_scored_in_fiscal_year_order_regardless_of_input_order() -> None:
    flags = [_flag(_A23, 2023), _flag(_A24, 2024)]
    in_order = [_derived(_A23, 2023, **_APPLE_2023), _derived(_A24, 2024, **_APPLE_2024)]

    scored, _ = score_accounting_flags(flags, list(reversed(in_order)))
    expected, _ = score_accounting_flags(flags, in_order)

    assert scored == expected
