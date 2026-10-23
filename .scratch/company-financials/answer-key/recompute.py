"""Ticket 44, by hand: one value per hard case recomputed from the raw company
facts (exact decimals) and compared with the answer key. Each input is re-read
from the raw file as the latest-filed copy of the key's concept and period; the
arithmetic is written out here, not taken from the oracle. Local only.

    python3 -I .scratch/company-financials/answer-key/recompute.py <proving/company-facts folder>
"""
import gzip
import json
import sys
from datetime import date
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 40
ROOT = Path(sys.argv[1])
key = json.loads((ROOT / "answer-key.json").read_text())
DOCS = {}
Q = Decimal("1e-12")
CASES = json.loads((ROOT / "answer-key-cases.json").read_text())["cases"]


def chosen(case):
    """The chosen company that covers a hard case (the cases file is local)."""
    return next(cik for cik, cases in CASES.items() if case in cases)


def doc(cik):
    if cik not in DOCS:
        with gzip.open(ROOT / "cohort" / f"{cik}.json.gz", "rt") as f:
            DOCS[cik] = json.loads(f.read(), parse_float=Decimal, parse_int=Decimal)
    return DOCS[cik]


def item(cik, year, name):
    return key["companies"][cik]["line_items"][str(year)][name]


def raw(cik, year, name):
    """The latest-filed raw copy of the key's chosen concept for that period."""
    it = item(cik, year, name)
    start = next((c.get("start") for t in it["tried"] for c in t["copies"] if c["accn"] == it["accn"]), None)
    facts = doc(cik)["facts"][it["taxonomy"]][it["concept"]]["units"][it["unit"]]
    filed = [f for f in facts if f["end"] == it["end"] and f.get("start") == start]
    latest = max(filed, key=lambda f: (f["filed"], f["accn"]))
    return Decimal(str(latest["val"])), it["unit"], it["taxonomy"], start, it["end"]


def measure(cik, name, year, window=None):
    return next(m for m in key["companies"][cik]["measures"]
                if m["measure"] == name and m["year"] == year and m["window"] == window)


def same(computed, m):
    return Decimal(m["value"]) == computed.quantize(Q)


def days(start, end):
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


rows = []
A, B, C = chosen("mixed_currencies"), chosen("stock_split"), chosen("financial_services")

# A changed its year end and its currency, B is a 52/53-week filer with a split, C a bank.

# 52/53-week year (B): a year of 371 days counting both ends, and its 1-year revenue CAGR.
years = sorted(int(y) for y in key["companies"][B]["line_items"])
long_year = next(y for y in years
                 if (y - 1) in years and item(B, y, "revenue").get("tried") and item(B, y - 1, "revenue").get("tried")
                 and days(raw(B, y, "revenue")[3], raw(B, y, "revenue")[4]) == 371)
now, prior = raw(B, long_year, "revenue")[0], raw(B, long_year - 1, "revenue")[0]
m = measure(B, "revenue_cagr", long_year, 1)
rows.append(("52/53-week year", f"revenue CAGR 1y, {long_year} (371 days)", same(now / prior - 1, m)))

# Stock split (B): diluted EPS CAGR over 1 year on the split-adjusted latest copies.
def split_visible(cik, year, name):
    """The year's filed copies differ by a whole-number ratio: a split restated them."""
    it = item(cik, year, name)
    vals = {Decimal(c["val"]) for t in it.get("tried", []) for c in t["copies"] if c["concept"] == it["concept"]}
    lo, hi = min(vals, default=0), max(vals, default=0)
    return lo > 0 and hi != lo and (hi / lo) == (hi / lo).to_integral_value()


split_year = next(x["year"] for x in key["companies"][B]["measures"]
                  if x["measure"] == "eps_diluted_cagr" and x["window"] == 1 and x["value"] is not None
                  and split_visible(B, x["year"], "diluted_shares"))
m = measure(B, "eps_diluted_cagr", split_year, 1)
rows.append(("stock split", f"diluted EPS CAGR 1y, {split_year}",
             same(raw(B, split_year, "eps_diluted")[0] / raw(B, split_year - 1, "eps_diluted")[0] - 1, m)))

# Negative base (B or A): a CAGR whose first or last raw value is at or below zero
# is null, "not meaningful" (ticket 39).
for cik in (B, A):
    nm = [x for x in key["companies"][cik]["measures"] if x["reason"] == "not meaningful" and x["measure"].endswith("_cagr")]
    if nm:
        x = nm[0]; base = x["measure"][:-5]; first = x["year"] - x["window"]
        v, w = raw(cik, first, base)[0], raw(cik, x["year"], base)[0]
        rows.append(("negative base", f"{x['measure']} {x['window']}y, {x['year']}: first or last value <= 0",
                     min(v, w) <= 0 and x["value"] is None and x["reason"] == "not meaningful"))
        break

# Changed year end (A): the year keeps the new year end's period (ticket 35), and a
# 1-year CAGR into it is computed on that period, recomputed from the raw copies.
yrs = key["companies"][A]["years"]
x = next(x for x in key["companies"][A]["measures"]
         if x["measure"].endswith("_cagr") and x["window"] == 1 and x["value"] is not None
         and "earlier_end" in yrs[str(x["year"])])
base = x["measure"][:-5]
now, _, _, start, end = raw(A, x["year"], base)
later = end == yrs[str(x["year"])]["end"] and end > yrs[str(x["year"])]["earlier_end"]
rows.append(("changed year end", f"{x['measure']} 1y, {x['year']}: on the period ending at the new year end",
             later and same(now / raw(A, x["year"] - 1, base)[0] - 1, x)))

# Restatement (C): net margin in the first year whose revenue has two distinct filed values.
def restated(cik, year, name):
    it = item(cik, year, name)
    return len({c["val"] for t in it.get("tried", []) for c in t["copies"] if c["concept"] == it["concept"]}) > 1


ry = next(x["year"] for x in key["companies"][C]["measures"]
          if x["measure"] == "net_margin" and x["value"] is not None and restated(C, x["year"], "revenue"))
m = measure(C, "net_margin", ry)
rows.append(("restatement", f"net margin {ry}, latest copies", same(raw(C, ry, "net_income")[0] / raw(C, ry, "revenue")[0], m)))

# Non-December year end (C): ROE on the beginning balance, the prior October's equity.
y = next(x["year"] for x in key["companies"][C]["measures"] if x["measure"] == "roe_beginning" and x["value"] is not None)
ni, _, _, _, end = raw(C, y, "net_income"); bv, _, _, _, bend = raw(C, y - 1, "book_value")
m = measure(C, "roe_beginning", y)
rows.append(("non-December year end", f"ROE beginning {y} (ends {end[5:]}, prior {bend[5:]})", same(ni / bv, m) and end[5:7] != "12"))

# Non-USD (C): the restated year's revenue in its reporting currency, never converted.
v, unit, tax, _, _ = raw(C, ry, "revenue")
rows.append(("non-USD filer", f"revenue {ry} kept in {unit}, not converted", unit != "USD" and Decimal(item(C, ry, "revenue")["value"]) == v))

# IFRS (A): net margin in a year A files under ifrs-full, from its ifrs-full concepts.
iy = next(x["year"] for x in key["companies"][A]["measures"] if x["measure"] == "net_margin" and x["value"] is not None
          and yrs[str(x["year"])]["taxonomy"] == "ifrs-full")
(ni, _, nt, _, _), (rv, _, rt, _, _) = raw(A, iy, "net_income"), raw(A, iy, "revenue")
rows.append(("IFRS filer", f"net margin {iy} from {nt} concepts", nt == rt == "ifrs-full" and same(ni / rv, measure(A, "net_margin", iy))))

# Financial services (C, a bank's SIC code): gross margin not meaningful.
x = next(x for x in key["companies"][C]["measures"] if x["measure"] == "gross_margin")
rows.append(("financial services", f"gross margin {x['year']}: {x['reason']}", key["companies"][C]["sic"].startswith("60") and x["reason"] == "not meaningful for financial services"))

# Mixed currencies (A): the inputs' units differ.
x = next(x for x in key["companies"][A]["measures"] if x["reason"] == "mixed currencies")
base = x["measure"][:-5]
units = {raw(A, yy, base)[1] for yy in (x["year"] - x["window"], x["year"])}
rows.append(("mixed currencies", f"{x['measure']} {x['year']}: input units {sorted(units)}", len(units) > 1 and x["value"] is None))
recomputed = {"52/53-week year", "stock split", "changed year end", "restatement", "non-December year end", "IFRS filer"}

for case, what, ok in rows:
    what = f"{what} [{'value recomputed' if case in recomputed else 'reason from raw inputs'}]"
    print(f"{'OK ' if ok else 'BAD'} {case}: {what}")
print(f"{sum(r[2] for r in rows)} of {len(rows)} agree")
