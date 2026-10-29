"""Ticket 47: silver's `company_measure`, built by SQL over `company_line_item` from
measures.yaml, one row per company, measure, fiscal year and window. Every name
and number here is invented."""

from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from sqlalchemy import text

from edgar_warehouse.financials import line_items, measures
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import land
from tests.integration.test_company_line_item_silver import fact, no_masters
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database

FOLDER = files.ROOT / "sources" / "sec.company-facts"
(GROWING, LOSS, STATUTORY, NO_PLACE, NO_RATE, BANK, UNMASTERED, EUROS, MOVED, TWO_ENDS, GAP) = (
    f"{n:010d}" for n in range(1, 12))
# Each company's SIC and place of incorporation, as its Company master holds them; UNMASTERED has none.
COMPANIES = {GROWING: ("3571", "DE"), LOSS: ("3571", "DE"), STATUTORY: ("3571", "DE"), NO_PLACE: ("3571", None),
             NO_RATE: ("3571", "1F"), BANK: ("6022", "DE"), EUROS: ("3571", "DE"), MOVED: ("3571", "DE"),
             TWO_ENDS: ("3571", "DE"), GAP: ("3571", "DE")}


def line(company, year, item, value, currency="USD", end=None):
    return {"company_key": company, "line_item": item, "fiscal_year": year, "period_start": None,
            "period_end": end or f"{year}-12-31", "value": str(value), "unit": currency or "shares",
            "currency": currency, "taxonomy": "us-gaap", "concept": "Invented", "inputs": None,
            "accession": f"{company}-{year % 100:02d}-000001", "filed": f"{year + 1}-02-01", "flags": [],
            "null_reason": None, "rule_version": "invented"}


def year(company, fiscal_year, end=None, **items):
    return [line(company, fiscal_year, item, value, end=end) for item, value in items.items()]


LINES = [
    # Growth of 10% a year; returns on the average and the beginning balance; ROIC on its own tax rate.
    *year(GROWING, 2021, revenue=100, net_income=5, book_value=50),
    *year(GROWING, 2022, revenue=110),
    *year(GROWING, 2023, revenue=121),
    *year(GROWING, 2024, revenue="133.1", net_income=10, book_value=80, total_debt=40, cash=20, ocf=30, capex=10),
    *year(GROWING, 2025, revenue="146.41", gross_profit="58.564", net_income=12, book_value=120, current_assets=50,
          operating_income=100, pretax_income=80, income_tax=20, total_debt=60, cash=30, ocf=40, capex=15),
    line(GROWING, 2025, "shares_outstanding", 10, currency=None),
    # A negative denominator, and growth from a loss.
    *year(LOSS, 2024, net_income=-3),
    *year(LOSS, 2025, net_income=4, book_value=-10, total_debt=5),
    # A loss before tax: ROIC takes the country's statutory rate.
    *year(STATUTORY, 2024, total_debt=50, book_value=50, cash=0),
    *year(STATUTORY, 2025, operating_income=100, pretax_income=-20, income_tax=2, total_debt=50, book_value=50, cash=0),
    *year(NO_PLACE, 2025, operating_income=10, pretax_income=0, income_tax=0),
    *year(NO_RATE, 2025, operating_income=10, pretax_income=-1, income_tax=0),
    *year(BANK, 2025, revenue=100, gross_profit=40, net_income=10),
    *year(UNMASTERED, 2025, revenue=100, gross_profit=40, net_income=10),
    *year(EUROS, 2025, revenue=100),
    line(EUROS, 2025, "gross_profit", 40, currency="EUR"),
    # A year with no annual period: the year end moved from December to June, or a year held two annual
    # periods, or neither.
    *year(MOVED, 2021, revenue=100),
    *year(MOVED, 2023, end="2023-06-30", revenue=120),
    *year(TWO_ENDS, 2021, revenue=100),
    *year(TWO_ENDS, 2023, revenue=120),
    *year(GAP, 2021, revenue=100),
    *year(GAP, 2023, revenue=120),
]
FACTS = [fact(TWO_ENDS, "Revenues", 110, "2023-06-30", "2022-07-01"),
         fact(TWO_ENDS, "Revenues", 120, "2023-12-31", "2023-01-01")]


@pytest.fixture
def built(postgres):
    admin, _ = postgres
    with silver_database(admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        sink = PostgresSink(runtime)
        for name in ("silver-company-fact.yaml", "silver-company-line-item.yaml", "silver-company-measure.yaml"):
            silver.register(owner, spec_file(FOLDER / name, None), runtime_role=RUNTIME)
        land(sink, "company_fact", copy.deepcopy(FACTS), no_masters)
        land(sink, "company_line_item", copy.deepcopy(LINES), no_masters)
        asked = []
        result = measures.build(runtime, sink, no_masters,
                                lambda keys: asked.append(keys) or {k: COMPANIES[k] for k in keys if k in COMPANIES})
        with runtime.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(text("SELECT * FROM silver.company_measure"))]
        yield result, asked, {(r["company_key"], r["measure"], r["fiscal_year"], r["window_years"]): r for r in rows}


def got(rows, company, measure, fiscal_year, window=1):
    row = rows[(company, measure, fiscal_year, window)]
    return row["value"], row["null_reason"]


def test_one_row_per_company_measure_fiscal_year_and_window(built):
    result, asked, rows = built
    definitions = measures.load()
    per_year = len(definitions.ratios) + 2 * len(definitions.returns) + len(definitions.series) * len(definitions.windows)
    years = {(r["company_key"], r["fiscal_year"]) for r in LINES}
    assert result["inserted"] == len(rows) == per_year * len(years)
    assert asked == [{k for k, _ in years}]
    assert {r["definition_version"] for r in rows.values()} == {definitions.version}


def test_a_ratio_and_its_reasons(built):
    _, _, rows = built
    assert got(rows, GROWING, "gross_margin", 2025) == (Decimal("0.4"), None)
    assert got(rows, GROWING, "current_ratio", 2025) == (None, "no concept filed")
    assert got(rows, EUROS, "gross_margin", 2025) == (None, "mixed currencies")
    assert got(rows, LOSS, "debt_to_equity", 2025) == (None, "denominator zero or negative")
    per_share = rows[(GROWING, "book_value_per_share", 2025, 1)]
    assert (per_share["value"], per_share["currency"]) == (Decimal(12), "USD")
    assert rows[(GROWING, "gross_margin", 2025, 1)]["currency"] is None
    margin = rows[(GROWING, "gross_margin", 2025, 1)]["inputs"]
    assert margin["revenue"] == {"fiscal_year": 2025, "value": "146.4100000000", "concept": "Invented",
                                 "accession": f"{GROWING}-25-000001"}


def test_the_statement_format_decides_what_is_meaningful(built):
    _, _, rows = built
    assert got(rows, BANK, "gross_margin", 2025) == (None, "not meaningful for financial services")
    assert got(rows, BANK, "roic_average", 2025) == (None, "not meaningful for financial services")
    assert got(rows, BANK, "net_margin", 2025) == (Decimal("0.1"), None)
    assert got(rows, UNMASTERED, "gross_margin", 2025) == (None, "statement format unknown")
    assert got(rows, UNMASTERED, "net_margin", 2025) == (Decimal("0.1"), None)


def test_returns_on_the_average_and_the_beginning_balance(built):
    _, _, rows = built
    assert got(rows, GROWING, "roe_average", 2025) == (Decimal("0.12"), None)
    assert got(rows, GROWING, "roe_beginning", 2025) == (Decimal("0.15"), None)
    assert got(rows, GROWING, "roe_average", 2021) == (None, "missing year")
    assert got(rows, GROWING, "roa_average", 2025) == (None, "no concept filed")


def test_roic_after_tax_on_its_own_rate_or_the_statutory_rate(built):
    _, _, rows = built
    # 100 x (1 - 20/80) over debt + equity - cash: 150 at the year's end, 100 at its beginning.
    assert got(rows, GROWING, "roic_average", 2025) == (Decimal("0.6"), None)
    assert got(rows, GROWING, "roic_beginning", 2025) == (Decimal("0.75"), None)
    assert rows[(GROWING, "roic_beginning", 2025, 1)]["inputs"]["return"]["rate_source"] == "filed"
    rate = next(Decimal(r["value"]) for r in line_items.published("corporate-tax-rates", "1")
                if r["code"] == "US:2025") / 100
    assert got(rows, STATUTORY, "roic_beginning", 2025) == (round(1 - rate, 10), None)
    assert rows[(STATUTORY, "roic_beginning", 2025, 1)]["inputs"]["return"]["rate_source"] == "statutory: US"
    assert got(rows, NO_PLACE, "roic_average", 2025) == (None, "no country of incorporation")
    assert got(rows, NO_RATE, "roic_average", 2025) == (None, "no statutory rate for the country and year")


def test_growth_over_exactly_n_years(built):
    _, _, rows = built
    assert got(rows, GROWING, "revenue_cagr", 2025, 1) == (Decimal("0.1"), None)
    assert got(rows, GROWING, "revenue_cagr", 2025, 3) == (Decimal("0.1"), None)
    assert got(rows, GROWING, "net_income_cagr", 2025, 1) == (Decimal("0.2"), None)
    assert got(rows, GROWING, "fcf_cagr", 2025, 1) == (Decimal("0.25"), None)  # (40 - 15) / (30 - 10)
    assert got(rows, GROWING, "revenue_cagr", 2025, 10) == (None, "missing year")
    assert got(rows, GROWING, "book_value_cagr", 2023, 1) == (None, "no concept filed")
    assert got(rows, LOSS, "net_income_cagr", 2025, 1) == (None, "not meaningful")


def test_a_gap_where_the_year_end_moved_is_a_changed_fiscal_year(built):
    _, _, rows = built
    assert got(rows, MOVED, "revenue_cagr", 2023, 1) == (None, "fiscal year changed")
    assert got(rows, TWO_ENDS, "revenue_cagr", 2023, 1) == (None, "fiscal year changed")
    assert got(rows, GAP, "revenue_cagr", 2023, 1) == (None, "missing year")
    assert got(rows, GAP, "revenue_cagr", 2023, 3) == (None, "missing year")
