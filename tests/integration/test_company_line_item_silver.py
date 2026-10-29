"""Ticket 46: silver's `company_line_item`, built by one SQL query over the facts
in `company_fact` from line-items.yaml, one row per company, line item and fiscal
year. Every name and number here is invented."""

from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from sqlalchemy import text

from edgar_warehouse.financials import line_items
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.silver_writer.sink import PostgresSink
from edgar_warehouse.silver_writer.writer import land
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database

FOLDER = files.ROOT / "sources" / "sec.company-facts"
US, EU, MARCH = "0000000001", "0000000003", "0000000002"


def no_masters(source_code, kind, keys):
    return {}


def fact(company, concept, value, end, start=None, *, taxonomy="us-gaap", unit="USD", accession="0000000001-26-000001",
         filed="2026-02-01", form="10-K"):
    return {"company_key": company, "taxonomy": taxonomy, "concept": concept, "unit": unit,
            "currency": unit.split("/")[0] if unit[:3].isupper() and unit[:3] != "pur" else None,
            "period": f"{start}/{end}" if start else end, "period_start": start, "period_end": end,
            "value": str(value), "accession": accession, "filed": filed, "form": form,
            "fiscal_year_filed": None, "fiscal_period_filed": None, "frame": None}


def year_2025(company, concept, value, **kw):
    return fact(company, concept, value, "2025-12-31", "2025-01-01", **kw)


def balance_2025(company, concept, value, **kw):
    return fact(company, concept, value, "2025-12-31", **kw)


FACTS = [
    # Revenue: the first concept present in the list, flagged when a later one is larger.
    year_2025(US, "RevenueFromContractWithCustomerExcludingAssessedTax", 500),
    year_2025(US, "SalesRevenueNet", 520),
    fact(US, "Revenues", 130, "2025-12-31", "2025-10-01"),  # a quarter is never the year's
    # Net income: the latest-filed copy wins.
    year_2025(US, "NetIncomeLoss", 10),
    year_2025(US, "NetIncomeLoss", 12, accession="0000000001-27-000001", filed="2027-02-01"),
    # Book value: computed, equity including NCI less NCI.
    balance_2025(US, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", 100),
    balance_2025(US, "MinorityInterest", 10),
    # Gross profit: revenue's value less the first cost concept present.
    year_2025(US, "CostOfGoodsAndServicesSold", 300),
    # Total debt: a required leg plus an optional one, its first present concept.
    balance_2025(US, "LongTermDebt", "50.5"),
    balance_2025(US, "CommercialPaper", 5),
    # Liabilities: the computed terms are in two units, so nothing.
    balance_2025(US, "LiabilitiesAndStockholdersEquity", 1000, unit="EUR", accession="0000000001-26-000009",
                 filed="2026-01-01"),
    # Cash: one copy filed in two units keeps the unit its filing uses most.
    balance_2025(US, "CashAndCashEquivalentsAtCarryingValue", 70),
    balance_2025(US, "CashAndCashEquivalentsAtCarryingValue", 65, unit="EUR"),
    # Shares outstanding: the cover-page concept, flagged.
    balance_2025(US, "EntityCommonStockSharesOutstanding", 7, taxonomy="dei", unit="shares"),
    # A year ending in March is the previous year's (Compustat FYEAR); the annual
    # report's own year wins over a later period seen only in another form.
    fact(MARCH, "Revenues", 40, "2025-03-31", "2024-04-01", accession="0000000002-25-000001", filed="2025-05-01"),
    fact(MARCH, "Assets", 90, "2025-03-31", accession="0000000002-25-000001", filed="2025-05-01"),
    fact(MARCH, "Revenues", 41, "2025-05-31", "2024-06-01", accession="0000000002-25-000002", filed="2025-07-01",
         form="8-K"),
    # An IFRS filer, with a stray us-gaap fact in the same filing.
    year_2025(EU, "Revenue", 200, taxonomy="ifrs-full", unit="EUR", accession="0000000003-26-000001"),
    year_2025(EU, "ProfitLoss", 20, taxonomy="ifrs-full", unit="EUR", accession="0000000003-26-000001"),
    year_2025(EU, "Revenues", 999, unit="EUR", accession="0000000003-26-000001"),
]


@pytest.fixture
def built(postgres):
    admin, _ = postgres
    with silver_database(admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        sink = PostgresSink(runtime)
        for name in ("silver-company-fact.yaml", "silver-company-line-item.yaml"):
            silver.register(owner, spec_file(FOLDER / name, None), runtime_role=RUNTIME)
        land(sink, "company_fact", copy.deepcopy(FACTS), no_masters)
        result = line_items.build(runtime, sink, no_masters)
        with runtime.connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(text("SELECT * FROM silver.company_line_item"))]
        yield result, {(r["company_key"], r["fiscal_year"], r["line_item"]): r for r in rows}


def test_one_row_per_company_line_item_and_fiscal_year(built):
    result, rows = built
    assert result["inserted"] == len(rows) == 3 * 23
    assert {(c, y) for c, y, _ in rows} == {(US, 2025), (MARCH, 2024), (EU, 2025)}
    dps = rows[(US, 2025, "dps")]
    assert (dps["value"], dps["null_reason"], dps["period_end"].isoformat()) == (None, "no concept filed", "2025-12-31")
    assert {r["rule_version"] for r in rows.values()} == {line_items.load().version}


def test_the_first_present_concept_s_latest_copy_wins(built):
    _, rows = built
    revenue, income = rows[(US, 2025, "revenue")], rows[(US, 2025, "net_income")]
    assert (revenue["value"], revenue["concept"], revenue["flags"]) == (
        Decimal(500), "RevenueFromContractWithCustomerExcludingAssessedTax", ["revenue quality check"])
    assert revenue["period_start"].isoformat() == "2025-01-01"
    assert (income["value"], income["accession"], income["filed"].isoformat()) == (
        Decimal(12), "0000000001-27-000001", "2027-02-01")
    cash, shares = rows[(US, 2025, "cash")], rows[(US, 2025, "shares_outstanding")]
    assert (cash["value"], cash["unit"], cash["currency"], cash["period_start"]) == (Decimal(70), "USD", "USD", None)
    assert (shares["value"], shares["concept"], shares["flags"]) == (
        Decimal(7), "EntityCommonStockSharesOutstanding", ["cover-page date"])


def test_computed_values_are_exact_and_name_their_inputs(built):
    _, rows = built
    book, gross, debt = (rows[(US, 2025, n)] for n in ("book_value", "gross_profit", "total_debt"))
    assert (book["value"], book["concept"], book["flags"]) == (Decimal(90), "computed", ["computed"])
    assert [i["concept"] for i in book["inputs"]] == [
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "MinorityInterest"]
    assert (gross["value"], gross["inputs"][0]) == (Decimal(200), {"line_item": "revenue", "value": "500.0000000000"})
    assert gross["accession"] == "0000000001-26-000001" and gross["period_start"].isoformat() == "2025-01-01"
    assert (debt["value"], [i["concept"] for i in debt["inputs"]]) == (Decimal("55.5"), ["LongTermDebt", "CommercialPaper"])
    liabilities = rows[(US, 2025, "liabilities")]
    assert (liabilities["value"], liabilities["null_reason"]) == (None, "no concept filed")  # two units


def test_the_fiscal_year_and_its_taxonomy(built):
    _, rows = built
    march = rows[(MARCH, 2024, "revenue")]
    assert (march["value"], march["period_end"].isoformat()) == (Decimal(40), "2025-03-31")
    assert rows[(MARCH, 2024, "assets")]["value"] == Decimal(90)
    eu, profit = rows[(EU, 2025, "revenue")], rows[(EU, 2025, "net_income")]
    assert (eu["taxonomy"], eu["concept"], eu["value"], eu["currency"]) == ("ifrs-full", "Revenue", Decimal(200), "EUR")
    assert (profit["concept"], profit["flags"]) == ("ProfitLoss", ["includes NCI"])
