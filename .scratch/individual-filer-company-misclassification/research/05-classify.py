"""Classify the scan's per-filer summary (05-scan-bronze-entity-types.py output).

Reproduces ticket 05's table. The individual test is the same as
edgar_warehouse.loaders.bronze_submission_extractors.is_individual_filer.
Usage: python 05-classify.py summary.jsonl
"""
import collections, json, sys
from edgar_warehouse.loaders.bronze_submission_extractors import OWNERSHIP_FORMS

PERIODIC = {"10-K","10-Q","8-K","20-F","40-F","6-K","10-K/A","10-Q/A","8-K/A","20-F/A","40-F/A","6-K/A","10-KT","20FR12B","20FR12G","40FR12B"}
FPI = {"20-F","40-F","6-K","20-F/A","40-F/A","6-K/A","20FR12B","20FR12G","40FR12B","F-1","F-3","F-4","F-6"}

def cls(r):
    forms = set(r["forms"])
    if not forms: return "no recent filings"
    if forms & FPI: return "foreign issuer (20-F/40-F/6-K)"
    if forms & PERIODIC: return "domestic issuer (10-K/10-Q/8-K)"
    if any(f.startswith(("N-","485","NPORT","497","24F")) for f in forms): return "fund / investment filer"
    if forms & {"13F-HR","13F-HR/A","13F-NT"}: return "13F institutional manager"
    if forms & {"D","D/A"}: return "private offering issuer (Form D)"
    if forms <= OWNERSHIP_FORMS: return "ownership forms only"
    return "other entity forms"

rows = [json.loads(l) for l in open(sys.argv[1])]
other = [r for r in rows if r.get("entityType") == "other"]
print(collections.Counter(r.get("entityType") for r in rows))
for k, v in collections.Counter(cls(r) for r in other).most_common(): print(f"{v:7,}  {k}")
individual = [r for r in other if set(r["forms"]) and set(r["forms"]) <= OWNERSHIP_FORMS and not r.get("sic") and not r.get("tickers")]
print("individuals by is_individual_filer:", len(individual))
