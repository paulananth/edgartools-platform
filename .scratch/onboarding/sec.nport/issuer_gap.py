"""Ticket 22: where the CUSIPs with one issuer LEI but no ISSUED_BY link go (counts only).
Usage: issuer_gap.py ZIP NISSUER"""
import csv, io, json, re, sys, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from edgar_warehouse.rules import files
from edgar_warehouse.mdm.clean import adapters

ZIP, OUT = Path(sys.argv[1]), Path(sys.argv[2])
CODE = "sec.nport.security.v1"
contract = files.source("sec.nport.security")["mdm"][CODE]["contract"]
root = OUT / "mdm-security"
manifest = json.loads((root / "manifest.json").read_bytes())
seen, linked, aside = set(), set(), {}
for b in manifest["batches"]:
    for rec in map(json.loads, (root / b["input"]["path"]).read_bytes().splitlines()):
        seen.add(rec["cusip"])
        try:
            r = adapters.normalize(rec, source_code=CODE, contract=contract, publication={
                **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                "member": b["input"]["path"]})
            if any(l.get("type") == "ISSUED_BY" for l in r.get("relationships") or []):
                linked.add(rec["cusip"])
        except adapters.UnsupportedRecord as x:
            aside[rec["cusip"]] = x.reason
LEI = re.compile(r"[A-Z0-9]{18}[0-9]{2}")
by_cusip = defaultdict(set)
csv.field_size_limit(10**8)
with zipfile.ZipFile(ZIP) as z:
    for row in csv.DictReader(io.TextIOWrapper(z.open("FUND_REPORTED_HOLDING.tsv"), "utf-8"), delimiter="\t"):
        c = (row["ISSUER_CUSIP"] or "").strip().upper()
        l = (row["ISSUER_LEI"] or "").strip().upper()
        if c and c not in ("000000000", "999999999") and LEI.fullmatch(l) and set(l) != {"0"}:
            by_cusip[c].add(l)
gap = [c for c, ls in by_cusip.items() if len(ls) == 1 and c not in linked]
why = Counter("set aside: " + aside[c] if c in aside else ("no record" if c not in seen else "accepted, no link")
              for c in gap)
print(json.dumps({"gap": len(gap), "why": dict(why)}, indent=1))
