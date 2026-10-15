"""Compare the filed CUSIP and ISIN pairs with OpenFIGI's composite FIGIs (ticket 79 part 1, ticket 80). Counts only."""
import hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_readings

RUN, CAPTURE = Path(sys.argv[1]), Path(sys.argv[2])
store = Artifacts()
def load(ref_path):
    ref = {"uri": ref_path.as_uri(), "sha256": hashlib.sha256(ref_path.read_bytes()).hexdigest()}
    return source_readings.load(ref, store, max_bytes=16 * 1024**3, max_rows=10**8, allow_lookup_receipts=True)[0]["artifacts"][0]["tables"]

empty = Counter()
def answers(kind):
    found, status = {}, Counter()
    for request in sorted((CAPTURE / kind).glob("*.request.json")):
        jobs = json.loads(request.read_text())
        reply = json.loads(request.with_name(request.name.replace(".request", "")).read_text())
        for job, answer in zip(jobs, reply):
            if "data" in answer:
                status["found"] += 1
                # Every FIGI a listing carries: a bond has no composite or share class, only its own FIGI.
                found[job["idValue"]] = {f for d in answer["data"] for f in (d.get("figi"), d.get("compositeFIGI"), d.get("shareClassFIGI")) if f}
                empty[kind] += not found[job["idValue"]]
            else:
                status[answer.get("warning") or answer.get("error")] += 1
    return found, status
cusip_figi, cusip_status = answers("id_cusip")
isin_figi, isin_status = answers("id_isin")
pairs = load(RUN / "pairs/output/combined.json")["pairs"]
combined = load(RUN / "combine/output/combined.json")
def verdict(c, i):
    a, b = cusip_figi.get(c), isin_figi.get(i)
    if a is None or b is None:
        return "not both found"
    return "same security" if a & b else "different securities"
one_to_one = Counter(verdict(p["cusip"], p["isin"]) for p in pairs if p["cusip_isins"] == 1 and p["isin_cusips"] == 1)
by_isin = defaultdict(list)
for p in pairs:
    if p["isin_cusips"] > 1:
        by_isin[p["isin"]].append(p["cusip"])
several = Counter()
for isin, cusips in by_isin.items():
    agree = sum(verdict(c, isin) == "same security" for c in cusips)
    several["exactly one CUSIP agrees" if agree == 1 else ("none agrees" if agree == 0 else "several agree")] += 1
cusip_by_figi = defaultdict(set)
for c, figis in cusip_figi.items():
    for f in figis:
        cusip_by_figi[f].add(c)
isin_only = Counter()
for row in combined["security_isin"]:
    figis = isin_figi.get(row["isin"])
    if figis is None:
        isin_only["ISIN not found"] += 1
    else:
        held = set().union(*(cusip_by_figi.get(f, set()) for f in figis)) if figis else set()
        isin_only["shares a FIGI with an N-PORT CUSIP" if held else "no N-PORT CUSIP shares its FIGI"] += 1
print(json.dumps({"found_with_no_figi": empty, "cusip_answers": cusip_status, "isin_answers": isin_status, "one_to_one_pairs": one_to_one,
                  "isins_with_several_cusips": several, "isin_only_securities": isin_only}, indent=1))
