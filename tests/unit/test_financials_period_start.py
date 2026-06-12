"""Tests for period_start capture and QTD-preference (Stage 2 of the
period_end PK fix, TODOS.md "sec_financial_fact PK omits period_end").

Stage 1 added period_end to sec_financial_fact's PK. Stage 2 adds
period_start, which disambiguates duration-concept facts that share the same
(accn, concept, fiscal_period, segment, period_end) but cover different
windows (QTD "3 months ended" vs. YTD "6 months ended", both ending on the
same date). These tests cover:

1. ``_extract_financial_fact_row`` (parsers/financials.py) captures the raw
   "start" for duration facts and a sentinel for instant facts.
2. ``compute_derived_for_accession`` (parsers/financials_derived.py) prefers
   the QTD (latest period_start / shortest duration) value when a concept has
   both a QTD and YTD row in the same group.
"""

from __future__ import annotations

from edgar_warehouse.parsers.financials import (
    _INSTANT_FACT_PERIOD_START_SENTINEL,
    _extract_financial_fact_row,
)
from edgar_warehouse.parsers.financials_derived import compute_derived_for_accession


def test_extract_financial_fact_row_captures_period_start_for_duration_fact():
    fact = {
        "accn": "0000320193-25-000050",
        "fy": 2024,
        "fp": "Q2",
        "start": "2024-01-01",
        "end": "2024-06-30",
        "form": "10-Q",
        "val": 2000,
    }
    row = _extract_financial_fact_row(320193, "us-gaap/Revenues", "USD", fact)
    assert row is not None
    assert row["period_start"] == "2024-01-01"
    assert row["period_end"] == "2024-06-30"


def test_extract_financial_fact_row_uses_sentinel_for_instant_fact():
    fact = {
        "accn": "0000320193-24-000123",
        "fy": 2024,
        "fp": "Q4",
        "end": "2024-09-28",
        "form": "10-K",
        "val": 391035000000,
    }
    row = _extract_financial_fact_row(320193, "us-gaap/AccountsPayableCurrent", "USD", fact)
    assert row is not None
    assert "start" not in fact
    assert row["period_start"] == _INSTANT_FACT_PERIOD_START_SENTINEL
    assert row["period_end"] == "2024-09-28"


def test_compute_derived_prefers_qtd_revenue_over_ytd():
    """Same (accn, fiscal_period, period_end) group with both a YTD (6mo)
    and QTD (3mo) Revenues fact -- the derived row should carry the QTD
    (incremental) value, not the YTD cumulative value.
    """
    fact_rows = [
        {
            "concept": "Revenues",
            "value": 200_000_000,  # YTD (6 months)
            "period_start": "2024-01-01",
            "period_end": "2024-06-30",
        },
        {
            "concept": "Revenues",
            "value": 110_000_000,  # QTD (3 months) -- the correct per-period value
            "period_start": "2024-04-01",
            "period_end": "2024-06-30",
        },
    ]

    derived = compute_derived_for_accession(
        cik=320193,
        accession_number="0000320193-25-000050",
        fiscal_year=2024,
        fiscal_period="Q2",
        period_end="2024-06-30",
        form_type="10-Q",
        fact_rows=fact_rows,
    )

    rows = derived["sec_financial_derived"]
    assert len(rows) == 1
    assert rows[0]["revenue"] == 110_000_000


def test_compute_derived_unaffected_when_only_one_duration_present():
    """Q1/instant facts have a single period_start across the group --
    behavior is unchanged from before Stage 2."""
    fact_rows = [
        {
            "concept": "Revenues",
            "value": 90_000_000,
            "period_start": "2024-01-01",
            "period_end": "2024-03-31",
        },
        {
            "concept": "us-gaap/AssetsCurrent",
            "value": 50_000_000,
            "period_start": _INSTANT_FACT_PERIOD_START_SENTINEL,
            "period_end": "2024-03-31",
        },
    ]

    derived = compute_derived_for_accession(
        cik=320193,
        accession_number="0000320193-25-000010",
        fiscal_year=2024,
        fiscal_period="Q1",
        period_end="2024-03-31",
        form_type="10-Q",
        fact_rows=fact_rows,
    )

    rows = derived["sec_financial_derived"]
    assert len(rows) == 1
    assert rows[0]["revenue"] == 90_000_000
