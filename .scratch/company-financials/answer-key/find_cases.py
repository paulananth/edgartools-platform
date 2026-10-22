"""Ticket 44: which cohort companies show each hard case (counts only in the repo).

Reads the captured company facts (one JSON per company, values as exact
decimals) and the captured submissions documents for the SIC code. Prints, per
hard case, how many companies show it, and a smallest set covering every case;
the CIKs it chooses go to a local file, never into the repository.

    uv run --no-sync python .scratch/company-financials/answer-key/find_cases.py \
        <company facts folder> <submissions bronze folder> <local out file>
"""
import gzip, json, re, sys
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

FACTS, SUBMISSIONS, OUT = (Path(a).expanduser() for a in sys.argv[1:4])
ANNUAL = range(364, 372)  # ticket 35: an annual period is 364-371 days
NOT_MONEY = {"shares", "pure", "USD/shares", "Year", "Years"}
CASES = ["weeks_52_53", "non_december", "changed_year_end", "restatement", "stock_split", "negative_base",
         "non_usd", "ifrs", "financial_services", "mixed_currencies"]


def days(f):
    """A period's length counting its first and last day: a 52-week year is 364."""
    return (date.fromisoformat(f["end"]) - date.fromisoformat(f["start"])).days + 1


def year_end_month(end: str) -> int:
    d = date.fromisoformat(end)
    return 12 if (d.month == 1 and d.day <= 7) else (d.month if d.day >= 24 else (d.month - 1 or 12))


def sic_codes() -> dict[str, str]:
    found = {}
    for path in SUBMISSIONS.rglob("CIK*.json"):
        if "-submissions-" in path.name:
            continue
        try:
            body = json.loads(path.read_bytes())
        except ValueError:
            continue
        if body.get("cik") is not None and body.get("sic"):
            found[str(body["cik"]).zfill(10)] = str(body["sic"])
    return found


def cases(body: dict, sic: str | None) -> set[str]:
    out = set()
    facts = body.get("facts") or {}
    if facts.get("ifrs-full"):
        out.add("ifrs")
    if sic and sic.isdigit() and (6000 <= int(sic) <= 6199 or 6300 <= int(sic) <= 6411):
        out.add("financial_services")
    lengths, months, currencies = set(), Counter(), set()
    by_period = defaultdict(set)
    for taxonomy in ("us-gaap", "ifrs-full"):
        for concept, spec in (facts.get(taxonomy) or {}).items():
            for unit, rows in (spec.get("units") or {}).items():
                for f in rows:
                    if not f.get("start") or days(f) not in ANNUAL or not str(f.get("form", "")).startswith(("10-K", "20-F", "40-F")):
                        continue
                    if unit not in NOT_MONEY and re.fullmatch(r"[A-Z]{3}", unit):
                        currencies.add(unit)
                    if concept in ("NetIncomeLoss", "ProfitLoss", "Revenues", "Revenue",
                                   "RevenueFromContractWithCustomerExcludingAssessedTax", "EarningsPerShareDiluted"):
                        by_period[(concept, unit, f["start"], f["end"])].add((Decimal(str(f["val"])), f["filed"], f["accn"]))
                    if concept in ("NetIncomeLoss", "ProfitLoss"):
                        lengths.add(days(f))
                        months[(f["end"][:4], year_end_month(f["end"]))] += 1
    if {364, 371} <= lengths:
        out.add("weeks_52_53")
    month_set = {m for (_, m) in months}
    if month_set and Counter(m for (_, m) in months).most_common(1)[0][0] != 12:
        out.add("non_december")
    if len(month_set) > 1:
        out.add("changed_year_end")
    if currencies - {"USD"}:
        out.add("non_usd")
    if len(currencies) > 1:
        out.add("mixed_currencies")
    for (concept, unit, start, end), copies in by_period.items():
        values = {v for v, _, _ in copies}
        if len(values) < 2:
            continue
        if concept == "EarningsPerShareDiluted":
            low, high = sorted(abs(v) for v in values)[0], sorted(abs(v) for v in values)[-1]
            if low and (high / low) >= Decimal("1.9") and abs(high / low - (high / low).to_integral()) < Decimal("0.05"):
                out.add("stock_split")
        elif concept in ("NetIncomeLoss", "ProfitLoss"):
            out.add("restatement")
    incomes = [v for (c, u, s, e), copies in by_period.items() if c in ("NetIncomeLoss", "ProfitLoss") for v, _, _ in copies]
    if any(v <= 0 for v in incomes) and any(v > 0 for v in incomes):
        out.add("negative_base")
    return out


sics = sic_codes()
shown, count = {}, Counter()
for path in sorted(FACTS.glob("*.json.gz")):
    body = json.loads(gzip.decompress(path.read_bytes()), parse_float=Decimal)
    cik = path.name.split(".")[0]
    shown[cik] = cases(body, sics.get(cik))
    count.update(shown[cik])
# The fewest companies covering every case shown at all (greedy set cover).
left, chosen = {c for c in CASES if count[c]}, []
while left:
    cik = max(sorted(shown), key=lambda k: (len(shown[k] & left), len(shown[k])))
    chosen.append(cik)
    left -= shown[cik]
OUT.write_text(json.dumps({"chosen": chosen, "cases": {k: sorted(shown[k]) for k in chosen}}, indent=1))
print(json.dumps({"companies": len(shown), "with_sic": sum(1 for k in shown if k in sics),
                  "companies_per_case": {c: count[c] for c in CASES},
                  "chosen": len(chosen), "cases_per_chosen": [len(shown[k]) for k in chosen],
                  "uncovered": [c for c in CASES if not count[c]]}, indent=1))
