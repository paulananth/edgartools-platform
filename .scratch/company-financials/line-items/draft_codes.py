"""Ticket 46: draft, approve and publish RDM code set `financial-line-items`
version 1 from `rules/sources/sec.company-facts/line-items.yaml`, on a
disposable PostgreSQL 16 (the shared server is untouched).

Each line item is a code with its label, its definition and its period
(`duration` or `instant`, a property). Its crosswalk names every concept the
map tries as the line item itself, in `us-gaap`, `ifrs-full` or `dei`
(`to_version: outside`), each with its SKOS match type (`FLAG_MATCH` in the
test); a computed value's terms stay in the map only. The test
`tests/unit/test_financial_line_items.py` holds the map and this crosswalk
equal. Published to a scratch folder; its two files are copied into
`rules/reference/published/financial-line-items/1/`.

Run from the repo root: uv run --no-sync python .scratch/company-financials/line-items/draft_codes.py
"""
import shutil
import tempfile
from pathlib import Path

import yaml

from edgar_warehouse.rdm.database import migrate
from edgar_warehouse.rdm.store import RDM
from tests.integration.test_rdm_postgres import server
from tests.unit.test_financial_line_items import crosswalk_of

MAP = Path("rules/sources/sec.company-facts/line-items.yaml")
OUT = Path("rules/reference/published")
INSTANT = {"book_value", "assets", "shares_outstanding", "total_debt", "cash", "liabilities",
           "current_assets", "current_liabilities"}
# Each line item's label and plain-words definition (research 01 sections 4 and 6).
WORDS = {
    "revenue": ("Revenue", "Total revenue for the period; for a bank, insurer or utility its industry total."),
    "net_income": ("Net income attributable to parent", "Profit or loss for the period attributable to the parent's owners."),
    "eps_diluted": ("Diluted EPS", "Diluted earnings per share for the period, on the latest-filed (split-adjusted) series."),
    "ocf": ("Operating cash flow", "Net cash provided by or used in operating activities."),
    "capex": ("Capital expenditure", "Cash paid to acquire property, plant and equipment."),
    "book_value": ("Book value", "Equity attributable to the parent at the period's end, excluding noncontrolling interest."),
    "assets": ("Total assets", "Total assets at the period's end."),
    "diluted_shares": ("Diluted weighted-average shares", "Weighted-average number of diluted shares outstanding over the period."),
    "shares_outstanding": ("Shares outstanding", "Common shares outstanding at the period's end."),
    "gross_profit": ("Gross profit", "Revenue less cost of revenue for the period."),
    "operating_income": ("Operating income", "Operating income or loss as the filer presents it; empty where it presents none."),
    "total_debt": ("Total debt", "Borrowings at the period's end, long-term and short-term; never borrowing capacity, "
                                 "never IFRS lease liabilities."),
    "cash": ("Cash and equivalents", "Cash and cash equivalents at the period's end."),
    "liabilities": ("Total liabilities", "Total liabilities at the period's end."),
    "current_assets": ("Current assets", "Assets classified as current at the period's end; empty for a balance sheet "
                                         "presented by liquidity."),
    "current_liabilities": ("Current liabilities", "Liabilities classified as current at the period's end; empty for a "
                                                   "balance sheet presented by liquidity."),
    "pretax_income": ("Pretax income", "Income from continuing operations before income taxes."),
    "income_tax": ("Income tax", "Income tax expense or benefit for the period."),
    "interest_expense": ("Interest expense", "Interest expense for the period; never net interest."),
    "da": ("Depreciation and amortization", "Depreciation, depletion and amortization for the period."),
    "dividends_paid": ("Dividends paid", "Cash dividends paid to common shareholders in the period."),
    "buybacks": ("Share buybacks", "Cash paid to repurchase the filer's own common shares in the period."),
    "dps": ("Dividends per share", "Common dividends per share declared, else paid, for the period."),
}


def main() -> None:
    body = yaml.safe_load(MAP.read_text())
    items = body["line_items"]
    assert set(items) == set(WORDS) and len(items) == 23
    codes = [{"code": code, "label": WORDS[code][0], "definition": WORDS[code][1],
              "properties": {"period": "instant" if code in INSTANT else "duration"}} for code in items]
    crosswalk = [{"from_code": code, "to_set": to_set, "to_version": "outside", "to_code": concept, "match_type": match}
                 for (code, to_set, concept), match in sorted(crosswalk_of(body).items())]
    with server() as engine:
        migrate(engine("rdm"), runtime_role="rdm_runtime")
        rdm = RDM(engine("rdm", "rdm_runtime"))
        rdm.draft({"code_set": "financial-line-items", "name": "Financial line items",
                   "definition": "The standard line items silver keeps for each company and annual period, each "
                                 "chosen from the concepts a filer reports, in the order the line-item map gives.",
                   "authority": "internal", "steward": "operator"},
                  "1", codes, created_by="claude (ticket 46)",
                  evidence={"from": str(MAP), "version": body["version"], "line_items": len(codes),
                            "rulings": "tickets 38, 42; research 01 section 6, research 04"},
                  levels=[{"depth": 1, "name": "Line item"}], crosswalk=crosswalk,
                  usage=[{"store": "silver", "object": "company_line_item", "field": "line_item"}],
                  hints=[{"kind": "meaning", "text": "A code's property `period`: duration (a flow over the year) "
                                                     "or instant (a balance at its end)."},
                         {"kind": "use_when", "text": "Naming a standard financial figure of a company and year; "
                                                     "its crosswalk names the reported concepts it can come from."}])
        rdm.approve("financial-line-items", "1", by="operator, 2026-10-22 (ticket 46)",
                    words="Yes, code set + crosswalk (Recommended)")
        with tempfile.TemporaryDirectory() as scratch:
            published = rdm.publish("financial-line-items", "1", out=Path(scratch))
            target = OUT / "financial-line-items" / "1"
            target.mkdir(parents=True, exist_ok=True)
            for name in ("canonical.jsonl", "pin.json"):
                shutil.copyfile(Path(scratch) / "financial-line-items" / "1" / name, target / name)
    print(published)


if __name__ == "__main__":
    main()
