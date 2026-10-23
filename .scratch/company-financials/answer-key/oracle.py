"""Ticket 44: the answer key for the line items and measures, computed from the
long-form facts by the operator's rulings (skills/company-financials/SKILL.md),
independently of the build. Every value carries every candidate fact tried and
why the chosen one won, so it can be checked by eye.

The key holds real figures and names, so it is written to a local file, never
to the repository (the repository is public); its sha256 is recorded on the
ticket instead.

    uv run --no-sync python .scratch/company-financials/answer-key/oracle.py \
        <company facts folder> <submissions bronze folder> <cases file> <key out file>

Inputs are the captured company facts (one JSON per company), read as exact
decimals, never floats; each input's sha256 is in the key.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from datetime import date
from decimal import Decimal, getcontext
from collections import Counter
from pathlib import Path

getcontext().prec = 40
PLACES = Decimal("1e-12")
FACTS, SUBMISSIONS, CASES, OUT = (Path(a).expanduser() for a in sys.argv[1:5])
# The pinned reference data this key reads (ticket 133): read by its pin, never a copy.
PUBLISHED = Path(__file__).resolve().parents[3] / "rules" / "reference" / "published"

# --- the rulings ------------------------------------------------------------------
ANNUAL = range(364, 372)  # ticket 35: 364-371 days, counting the first and last day
ANNUAL_REPORTS = {"10-K", "20-F", "40-F"}  # with their amendments (form "/A")
INSTANT = {"book_value", "assets", "shares_outstanding", "total_debt", "cash", "liabilities",
           "current_assets", "current_liabilities"}
# Ticket 38 (research 01 section 6, cost of revenue in the standard's order) and
# ticket 42 / research 04 (ifrs-full). Each entry: a concept, or ("computed", how).
LISTS = {
    "us-gaap": {
        "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                    ("computed", "goods_plus_services"), ("kind", "RevenuesNetOfInterestExpense", "bank"),
                    ("kind", "InterestAndDividendIncomeOperating", "bank"),
                    ("kind", "RegulatedAndUnregulatedOperatingRevenue", "utility"),
                    ("kind", "PremiumsEarnedNet", "insurer")],
        "net_income": ["NetIncomeLoss", ("computed", "profit_less_nci"), ("flag", "ProfitLoss", "includes NCI")],
        "eps_diluted": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted",
                        ("flag", "IncomeLossFromContinuingOperationsPerDilutedShare", "continuing operations")],
        "ocf": ["NetCashProvidedByUsedInOperatingActivities",
                ("flag", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "continuing operations")],
        "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
                  ("flag", "PaymentsToAcquireProductiveAssets", "includes software and intangibles"),
                  "PaymentsToAcquireOtherPropertyPlantAndEquipment", "PaymentsForCapitalImprovements"],
        "book_value": ["StockholdersEquity", ("computed", "equity_less_nci"), "PartnersCapital", "MembersEquity"],
        "assets": ["Assets"],
        "diluted_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding",
                           "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"],
        "shares_outstanding": ["CommonStockSharesOutstanding",
                               ("flag", "dei:EntityCommonStockSharesOutstanding", "cover-page date")],
        "gross_profit": ["GrossProfit", ("computed", "revenue_less_cost")],
        "operating_income": ["OperatingIncomeLoss"],
        "total_debt": [("computed", "us_debt")],
        "cash": ["CashAndCashEquivalentsAtCarryingValue",
                 ("flag", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "includes restricted cash"),
                 "Cash"],
        "liabilities": ["Liabilities", ("computed", "us_liabilities")],
        "current_assets": ["AssetsCurrent"],
        "current_liabilities": ["LiabilitiesCurrent"],
        "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
        "income_tax": ["IncomeTaxExpenseBenefit"],
        "interest_expense": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt",
                             "InterestAndDebtExpense", "InterestExpenseOperating"],
        "da": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
               "DepreciationAmortizationAndAccretionNet", ("flag", "Depreciation", "excludes amortization")],
        "dividends_paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
        "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
        "dps": ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"],
    },
    "ifrs-full": {
        "revenue": ["Revenue", "RevenueFromContractsWithCustomers", ("kind", "RevenueFromInterest", "bank"),
                    ("kind", "InterestRevenueCalculatedUsingEffectiveInterestMethod", "bank"),
                    ("kind", "InsuranceRevenue", "insurer")],
        "net_income": ["ProfitLossAttributableToOwnersOfParent", ("computed", "ifrs_profit_less_nci"),
                       ("flag", "ProfitLoss", "includes NCI")],
        "eps_diluted": ["DilutedEarningsLossPerShare", "BasicAndDilutedEarningsLossPerShare",
                        ("flag", "DilutedEarningsLossPerShareFromContinuingOperations", "continuing operations")],
        "ocf": ["CashFlowsFromUsedInOperatingActivities"],
        "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                  ("flag", "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
                   "includes intangibles and other assets")],
        "book_value": ["EquityAttributableToOwnersOfParent", ("computed", "ifrs_equity_less_nci")],
        "assets": ["Assets"],
        "diluted_shares": ["AdjustedWeightedAverageShares"],
        "shares_outstanding": ["NumberOfSharesOutstanding",
                               ("flag", "dei:EntityCommonStockSharesOutstanding", "cover-page date")],
        "gross_profit": ["GrossProfit", ("computed", "ifrs_revenue_less_cost")],
        "operating_income": ["ProfitLossFromOperatingActivities"],
        "total_debt": [("computed", "ifrs_debt")],
        "cash": ["CashAndCashEquivalents", ("flag", "Cash", "cash only")],
        "liabilities": ["Liabilities", ("computed", "ifrs_liabilities")],
        "current_assets": ["CurrentAssets"],
        "current_liabilities": ["CurrentLiabilities"],
        "pretax_income": ["ProfitLossBeforeTax"],
        "income_tax": ["IncomeTaxExpenseContinuingOperations"],
        "interest_expense": ["InterestExpense", "InterestExpenseOnBorrowings",
                             ("flag", "FinanceCosts", "includes other finance costs")],
        "da": ["DepreciationAndAmortisationExpense", "AdjustmentsForDepreciationAndAmortisationExpense",
               ("flag", "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
                "includes impairment"),
               ("flag", "DepreciationExpense", "excludes amortisation")],
        "dividends_paid": ["DividendsPaidClassifiedAsFinancingActivities",
                           "DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities", "DividendsPaid"],
        "buybacks": ["PaymentsToAcquireOrRedeemEntitysShares"],
        "dps": ["DividendsRecognisedAsDistributionsToOwnersPerShare"],
    },
}
# Ticket 42: SIC 6000-6199 and 6300-6411 are financial services; these measures are
# not meaningful for it (with the current ratio, operator 2026-10-22).
NOT_FS = {"gross_margin", "roic_average", "roic_beginning", "debt_to_assets", "debt_to_equity", "current_ratio"}
GROWTH = ("revenue", "net_income", "eps_diluted", "ocf", "fcf", "book_value")


def fiscal_year(end: str) -> int:
    """Compustat's FYEAR (operator, 2026-10-22: "Compustat FYEAR (Recommended)"): a
    fiscal year ending January to May belongs to the previous calendar year."""
    d = date.fromisoformat(end)
    return d.year if d.month >= 6 else d.year - 1


def end_month(end: str) -> int:
    """The month a year ends in, a 52/53-week drift into early January read as December."""
    return date.fromordinal(date.fromisoformat(end).toordinal() - 7).month


def days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def currency(unit: str) -> str | None:
    head = unit.split("/")[0]
    return head if len(head) == 3 and head.isupper() else None


def pinned(code_set: str, version: str = "1") -> dict[str, dict]:
    """A published code set's codes, refused unless they are its pinned bytes."""
    folder = PUBLISHED / code_set / version
    data = (folder / "canonical.jsonl").read_bytes()
    if hashlib.sha256(data).hexdigest() != json.loads((folder / "pin.json").read_text())["sha256"]:
        raise SystemExit(f"{code_set} {version} differs from its pin")
    return {row["code"]: row for row in map(json.loads, data.decode().splitlines())}


PLACE_CODES, RATES = pinned("sec-place-codes"), pinned("corporate-tax-rates")


def country(place: str | None) -> str | None:
    """The ISO country a filed place code names: its exact ISO 3166 crosswalk, a
    subdivision (US-PA, CA-ON) read as its country."""
    for to_set, _, code, match in (PLACE_CODES.get(place or "") or {}).get("crosswalk", []):
        if to_set == "iso-3166" and match == "exact":
            return code.split("-")[0]
    return None


def statutory_rate(alpha2: str | None, end: str) -> Decimal | None:
    """The country's statutory rate in force on the fiscal year's end, as a fraction
    (operator, 2026-10-22: "Statutory rate (new source)"; RDM corporate-tax-rates)."""
    row = RATES.get(f"{alpha2}:{end[:4]}") if alpha2 else None
    if row is None or not (row["valid_from"] <= end <= row["valid_to"]):
        return None
    return Decimal(row["value"]) / 100


class Company:
    def __init__(self, cik: str, body: dict, sic: str | None, place: str | None = None):
        self.cik, self.sic = cik, sic
        self.country = country(place)
        self.fs = bool(sic and sic.isdigit() and (6000 <= int(sic) <= 6199 or 6300 <= int(sic) <= 6411))
        self.facts = body.get("facts") or {}
        self.years = self._years()

    def copies(self, taxonomy: str, concept: str):
        if concept.startswith("dei:"):
            taxonomy, concept = "dei", concept[4:]
        for unit, rows in ((self.facts.get(taxonomy) or {}).get(concept) or {}).get("units", {}).items():
            for f in rows:
                yield unit, f

    def _years(self) -> dict[int, dict]:
        """Each fiscal year: its annual period's end, keyed by Compustat's FYEAR. When
        two annual periods fall in one fiscal year, the year is the one an annual
        report covers as its own fiscal year; a 12-month period seen only as a
        comparative is kept as filed but is not a year (operator, 2026-10-22: "The
        reported year (Recommended)"). A report's own period is the annual period
        it files the most facts for. Both or neither reported: the later (ticket 35)."""
        ends: set[str] = set()
        per_report: dict[str, Counter] = {}
        for taxonomy in ("us-gaap", "ifrs-full"):
            for concept, spec in (self.facts.get(taxonomy) or {}).items():
                for unit, rows in (spec.get("units") or {}).items():
                    for f in rows:
                        if f.get("start") and days(f["start"], f["end"]) in ANNUAL:
                            ends.add(f["end"])
                            if (f.get("form") or "").split("/")[0] in ANNUAL_REPORTS:
                                per_report.setdefault(f["accn"], Counter())[f["end"]] += 1
        reported = {counts.most_common(1)[0][0] for counts in per_report.values()}
        years: dict[int, dict] = {}
        for end in sorted(ends):
            year = fiscal_year(end)
            held = years.get(year, {}).get("end")
            if held is None:
                years[year] = {"end": end}
            elif (held in reported) and (end not in reported):
                years[year]["comparative_end"] = end
            else:
                years[year] = {"end": end, ("comparative_end" if held not in reported and end in reported else "earlier_end"): held}
        for year, entry in years.items():
            entry["taxonomy"] = self._taxonomy(entry["end"])
        return years

    def _taxonomy(self, end: str) -> str:
        """The taxonomy a year is filed in (ticket 42): in the latest filing holding an
        annual fact ending that day, the taxonomy most of its facts use. A filer
        under one taxonomy can file a stray fact under the other."""
        by_filing: dict[tuple, Counter] = {}
        for taxonomy in ("us-gaap", "ifrs-full"):
            for spec in (self.facts.get(taxonomy) or {}).values():
                for rows in (spec.get("units") or {}).values():
                    for f in rows:
                        if f["end"] == end and f.get("start") and days(f["start"], end) in ANNUAL:
                            by_filing.setdefault((f["filed"], f["accn"]), Counter())[taxonomy] += 1
        if not by_filing:
            return "us-gaap"
        return by_filing[max(by_filing)].most_common(1)[0][0]

    def found(self, taxonomy: str, concept: str, end: str, instant: bool) -> list[dict]:
        """Every filed copy of a concept for the year ending `end`, latest filed first."""
        out = []
        for unit, f in self.copies(taxonomy, concept):
            if f["end"] != end:
                continue
            if instant != (not f.get("start")):
                continue
            if not instant and days(f["start"], end) not in ANNUAL:
                continue
            out.append({"concept": concept, "unit": unit, "val": str(f["val"]), "filed": f["filed"],
                        "accn": f["accn"], "form": f.get("form"), "start": f.get("start")})
        return sorted(out, key=lambda c: (c["filed"], c["accn"]), reverse=True)


def value(copy: dict) -> Decimal:
    return Decimal(copy["val"])


def item(company: Company, year: int, name: str) -> dict:
    entry = company.years[year]
    taxonomy, end = entry["taxonomy"], entry["end"]
    instant = name in INSTANT
    tried = []

    def first(concept, flag=None, kind=None):
        copies = company.found(taxonomy, concept, end, instant)
        tried.append({"concept": concept, "copies": copies})
        if not copies:
            return None
        chosen = copies[0]
        return {"value": chosen["val"], "unit": chosen["unit"], "concept": concept, "accn": chosen["accn"],
                "filed": chosen["filed"], "flags": [f for f in (flag, kind and f"kind: {kind}") if f]}

    def get(concept):
        copies = company.found(taxonomy, concept, end, instant)
        tried.append({"concept": concept, "copies": copies, "part_of_computed": True})
        return copies[0] if copies else None

    def computed(how):
        parts = {
            "goods_plus_services": ("plus", ["SalesRevenueGoodsNet", "SalesRevenueServicesNet"]),
            "profit_less_nci": ("minus", ["ProfitLoss", "NetIncomeLossAttributableToNoncontrollingInterest"]),
            "ifrs_profit_less_nci": ("minus", ["ProfitLoss", "ProfitLossAttributableToNoncontrollingInterests"]),
            "equity_less_nci": ("minus", ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                                          "MinorityInterest"]),
            "ifrs_equity_less_nci": ("minus", ["Equity", "NoncontrollingInterests"]),
            "ifrs_liabilities": ("minus", ["EquityAndLiabilities", "Equity"]),
        }
        if how in parts:
            op, names = parts[how]
            got = [get(n) for n in names]
            if any(g is None for g in got) or len({g["unit"] for g in got}) > 1:
                return None
            total = value(got[0]) + value(got[1]) if op == "plus" else value(got[0]) - value(got[1])
            return {"value": str(total), "unit": got[0]["unit"], "concept": f"computed: {how}",
                    "accn": got[0]["accn"], "filed": got[0]["filed"], "flags": ["computed"]}
        if how in ("revenue_less_cost", "ifrs_revenue_less_cost"):
            rev = item(company, year, "revenue")
            cost_names = (["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfServices", "CostOfGoodsSold"]
                          if taxonomy == "us-gaap" else ["CostOfSales"])
            cost = next((c for c in (get(n) for n in cost_names) if c), None)
            if rev.get("value") is None or cost is None or rev["unit"] != cost["unit"]:
                return None
            return {"value": str(Decimal(rev["value"]) - value(cost)), "unit": cost["unit"],
                    "concept": f"computed: revenue - {cost['concept']}", "accn": cost["accn"],
                    "filed": cost["filed"], "flags": ["computed"]}
        if how == "us_liabilities":
            total, eq = get("LiabilitiesAndStockholdersEquity"), get(
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
            temp = get("TemporaryEquityCarryingAmountAttributableToParent")
            if total is None or eq is None:
                return None
            v = value(total) - value(eq) - (value(temp) if temp else 0)
            return {"value": str(v), "unit": total["unit"], "concept": "computed: us_liabilities",
                    "accn": total["accn"], "filed": total["filed"], "flags": ["computed"]}
        if how in ("us_debt", "ifrs_debt"):
            options = ([[["LongTermDebt"], ["ShortTermBorrowings", "CommercialPaper", "NotesPayableCurrent"]],
                        [["LongTermDebtNoncurrent"], ["LongTermDebtCurrent", "DebtCurrent"]],
                        [["LongTermDebtAndCapitalLeaseObligations"], ["LongTermDebtAndCapitalLeaseObligationsCurrent"]]]
                       if how == "us_debt" else
                       [[["Borrowings"]], [["LongtermBorrowings"], ["ShorttermBorrowings"]],
                        [["LongtermBorrowings"], ["CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"]]])
            for number, legs in enumerate(options):
                got = [next((c for c in (get(n) for n in leg) if c), None) for leg in legs]
                if got[0] is None:
                    continue
                legs_found = [g for g in got if g]
                if len({g["unit"] for g in legs_found}) > 1:
                    continue
                flags = ["computed"] + (["includes leases"] if how == "us_debt" and number == 2 else [])
                return {"value": str(sum(value(g) for g in legs_found)), "unit": legs_found[0]["unit"],
                        "concept": "computed: " + " + ".join(g["concept"] for g in legs_found),
                        "accn": legs_found[0]["accn"], "filed": legs_found[0]["filed"], "flags": flags}
            return None
        raise ValueError(how)

    for entry_spec in LISTS[taxonomy][name]:
        if isinstance(entry_spec, str):
            got = first(entry_spec)
        elif entry_spec[0] == "computed":
            got = computed(entry_spec[1])
        elif entry_spec[0] == "flag":
            got = first(entry_spec[1], flag=entry_spec[2])
        else:
            got = first(entry_spec[1], kind=entry_spec[2])
        if got:
            return {**got, "taxonomy": taxonomy, "end": end, "tried": tried}
    return {"value": None, "reason": "no concept filed", "taxonomy": taxonomy, "end": end, "tried": tried}


def measures(company: Company, items: dict[int, dict]) -> list[dict]:
    out = []

    def number(year, name):
        got = (items.get(year) or {}).get(name) or {}
        return (Decimal(got["value"]), currency(got["unit"])) if got.get("value") is not None else (None, None)

    def missing(prior):
        """Why the earlier year a measure needs has no figure. A year that has an
        annual period but not this figure is "missing year" (operator, 2026-10-22:
        'Null, "missing year"'; CAGR's missing endpoint). A year with no annual
        period is "fiscal year changed" when the year end moved around the gap,
        else "missing year" (ticket 35). Callers ask only once the later figure is
        known, so the gap is `prior`."""
        if prior in company.years:
            return "missing year"
        absent = prior
        before = [y for y in company.years if y < absent]
        after = [y for y in company.years if y > absent]
        if not before or not after:
            return "missing year"
        lo, hi = max(before), min(after)
        moved = end_month(company.years[lo]["end"]) != end_month(company.years[hi]["end"])
        moved |= any({"earlier_end", "comparative_end"} & set(company.years[y]) for y in company.years if lo <= y <= hi)
        return "fiscal year changed" if moved else "missing year"

    def add(name, year, window, val=None, reason=None, inputs=None):
        if val is not None:
            val = str(Decimal(val).quantize(PLACES))
        out.append({"measure": name, "year": year, "window": window, "value": val, "reason": reason, "inputs": inputs or {}})

    def ratio(name, year, top, bottom, inputs):
        if company.fs and name in NOT_FS:
            return add(name, year, None, reason="not meaningful for financial services")
        (a, ca), (b, cb) = top, bottom
        if a is None or b is None:
            return add(name, year, None, reason="no concept filed", inputs=inputs)
        if ca and cb and ca != cb:
            return add(name, year, None, reason="mixed currencies", inputs=inputs)
        if b <= 0:
            return add(name, year, None, reason="denominator zero or less", inputs=inputs)
        return add(name, year, None, val=a / b, inputs=inputs)

    for year in sorted(items):
        get = lambda n, y=year: number(y, n)
        ocf, capex = get("ocf"), get("capex")
        fcf = (ocf[0] - capex[0], ocf[1]) if ocf[0] is not None and capex[0] is not None and ocf[1] == capex[1] else (None, None)
        items[year]["fcf"] = ({"value": str(fcf[0]), "unit": items[year]["ocf"]["unit"], "concept": "computed: ocf - capex",
                               "flags": ["computed", "non-GAAP"]} if fcf[0] is not None else {"value": None, "reason": "no concept filed"})
        rev = get("revenue")
        ratio("gross_margin", year, get("gross_profit"), rev, {"gross_profit": year, "revenue": year})
        ratio("operating_margin", year, get("operating_income"), rev, {"operating_income": year, "revenue": year})
        ratio("net_margin", year, get("net_income"), rev, {"net_income": year, "revenue": year})
        ratio("fcf_margin", year, fcf, rev, {"fcf": year, "revenue": year})
        ratio("debt_to_assets", year, get("total_debt"), get("assets"), {})
        ratio("debt_to_equity", year, get("total_debt"), get("book_value"), {})
        ratio("liabilities_to_assets", year, get("liabilities"), get("assets"), {})
        ratio("current_ratio", year, get("current_assets"), get("current_liabilities"), {})
        ratio("book_value_per_share", year, get("book_value"), get("shares_outstanding"), {})
        ratio("fcf_per_share", year, fcf, get("diluted_shares"), {})
        # Returns, on the average and on the beginning balance (ticket 39).
        ni, oi, pre, tax = get("net_income"), get("operating_income"), get("pretax_income"), get("income_tax")
        prior = year - 1
        for base, top_name in (("roe", "book_value"), ("roa", "assets"), ("roic", None)):
            for form in ("average", "beginning"):
                name = f"{base}_{form}"
                if company.fs and name in NOT_FS:
                    add(name, year, None, reason="not meaningful for financial services")
                    continue
                if base == "roic":
                    if oi[0] is None:
                        add(name, year, None, reason="no concept filed")
                        continue
                    if pre[0] is None or tax[0] is None:
                        add(name, year, None, reason="no concept filed")
                        continue
                    rate = tax[0] / pre[0] if pre[0] > 0 else None
                    if rate is None or not (0 <= rate <= 1):
                        if company.country is None:
                            add(name, year, None, reason="no country of incorporation")
                            continue
                        rate = statutory_rate(company.country, company.years[year]["end"])
                        if rate is None:
                            add(name, year, None, reason="no statutory rate for the country and year")
                            continue
                    top = (oi[0] * (1 - rate), oi[1])

                    def capital(y):
                        d, e, c = number(y, "total_debt"), number(y, "book_value"), number(y, "cash")
                        if None in (d[0], e[0], c[0]) or len({d[1], e[1], c[1]}) > 1:
                            return (None, None)
                        return (d[0] + e[0] - c[0], e[1])
                    now, then = capital(year), capital(prior)
                else:
                    top = ni
                    now, then = number(year, top_name), number(prior, top_name)
                if top[0] is None or now[0] is None:
                    add(name, year, None, reason="no concept filed")
                    continue
                if prior not in items or then[0] is None:
                    add(name, year, None, reason=missing(prior))
                    continue
                currencies = {c for c in (top[1], now[1], then[1]) if c}
                if len(currencies) > 1:
                    add(name, year, None, reason="mixed currencies")
                    continue
                bottom = (now[0] + then[0]) / 2 if form == "average" else then[0]
                if bottom <= 0:
                    add(name, year, None, reason="denominator zero or less")
                    continue
                add(name, year, None, val=top[0] / bottom, inputs={"top": str(top[0]), "bottom": str(bottom)})
        # Growth over exactly 1, 3, 5 and 10 years (ticket 39).
        for name in GROWTH:
            for n in (1, 3, 5, 10):
                start, end_value = number(year - n, name) if name != "fcf" else (
                    (Decimal(items[year - n]["fcf"]["value"]), currency(items[year - n]["fcf"]["unit"]))
                    if (year - n) in items and items[year - n].get("fcf", {}).get("value") is not None else (None, None)), (
                    get(name) if name != "fcf" else fcf)
                label = f"{name}_cagr"
                if end_value[0] is None:
                    add(label, year, n, reason="no concept filed")
                elif start[0] is None:
                    add(label, year, n, reason=missing(year - n))
                elif start[1] and end_value[1] and start[1] != end_value[1]:
                    add(label, year, n, reason="mixed currencies")
                elif start[0] <= 0 or end_value[0] <= 0:
                    add(label, year, n, reason="not meaningful")
                else:
                    add(label, year, n, val=((end_value[0] / start[0]).ln() / n).exp() - 1,
                        inputs={"start": str(start[0]), "end": str(end_value[0])})
    return out


def filers() -> dict[str, tuple[str | None, str | None]]:
    """Each filer's SIC code and filed place of incorporation."""
    found = {}
    for path in SUBMISSIONS.rglob("CIK*.json"):
        try:
            body = json.loads(path.read_bytes())
        except ValueError:
            continue
        if body.get("cik") is not None:
            found[str(body["cik"]).zfill(10)] = (str(body["sic"]) if body.get("sic") else None,
                                                 body.get("stateOfIncorporation") or None)
    return found


def main() -> None:
    chosen = json.loads(CASES.read_text())
    filed = filers()
    key = {"rulings": "skills/company-financials/SKILL.md (tickets 35, 38, 39, 42, 44)", "companies": {}}
    for cik in chosen["chosen"]:
        path = FACTS / f"{cik}.json.gz"
        raw = path.read_bytes()
        body = json.loads(gzip.decompress(raw), parse_float=Decimal)
        sic, place = filed.get(cik, (None, None))
        company = Company(cik, body, sic, place)
        items = {y: {name: item(company, y, name) for name in LISTS["us-gaap"]} for y in sorted(company.years)}
        key["companies"][cik] = {
            "input_sha256": hashlib.sha256(raw).hexdigest(), "cases": chosen["cases"][cik],
            "format": "financial services" if company.fs else "industrial", "sic": sic, "country": company.country,
            "years": {y: {"end": company.years[y]["end"], "taxonomy": company.years[y]["taxonomy"],
                          **{k: company.years[y][k] for k in ("earlier_end", "comparative_end") if k in company.years[y]}}
                      for y in company.years},
            "line_items": items, "measures": measures(company, items)}
    text = json.dumps(key, indent=1, sort_keys=True, default=str)
    OUT.write_text(text)
    reasons, filled = {}, 0
    for c in key["companies"].values():
        for m in c["measures"]:
            if m["value"] is not None:
                filled += 1
            else:
                reasons[m["reason"]] = reasons.get(m["reason"], 0) + 1
    print(json.dumps({"key_sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "companies": len(key["companies"]),
                      "years": {k: len(v["years"]) for k, v in key["companies"].items()},
                      "measures_with_value": filled, "null_reasons": reasons}, indent=1))


if __name__ == "__main__":
    main()
