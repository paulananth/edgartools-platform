"""Which ISIN each N-PORT CUSIP Security would carry under the operator's choice ("Use FIGI to add pairs
too"), under two meanings of "FIGI agrees". Counts only; no requests."""
import hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_readings

RUN, CAPTURE = Path(sys.argv[1]), Path(sys.argv[2])
store = Artifacts()
def load(path):
    ref = {"uri": path.as_uri(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return source_readings.load(ref, store, max_bytes=16 * 1024**3, max_rows=10**8, allow_lookup_receipts=True)[0]["artifacts"][0]["tables"]
def answers(kind, fields):
    found = {}
    for request in sorted((CAPTURE / kind).glob("*.request.json")):
        for job, answer in zip(json.loads(request.read_text()), json.loads(request.with_name(request.name.replace(".request", "")).read_text())):
            if "data" in answer:
                found[job["idValue"]] = {d[f] for d in answer["data"] for f in fields if d.get(f)}
    return found
pairs = load(RUN / "pairs/output/combined.json")["pairs"]
isin_only = [r["isin"] for r in load(RUN / "combine/output/combined.json")["security_isin"]]
report = {}
for name, fields in (("listing or composite", ("figi", "compositeFIGI")), ("with share class", ("figi", "compositeFIGI", "shareClassFIGI"))):
    cf, isf = answers("id_cusip", fields), answers("id_isin", fields)
    same = lambda c, i: c in cf and i in isf and bool(cf[c] & isf[i])
    offers = defaultdict(set)   # cusip -> ISINs some case would attach
    cases = Counter()
    for p in pairs:
        if p["cusip_isins"] == 1 and p["isin_cusips"] == 1:
            if same(p["cusip"], p["isin"]):
                offers[p["cusip"]].add(p["isin"]); cases["1 filed one to one, FIGI agrees"] += 1
            else:
                cases["1 dropped: FIGI disagrees or cannot judge"] += 1
    several = defaultdict(list)
    for p in pairs:
        if p["isin_cusips"] > 1:
            several[p["isin"]].append(p["cusip"])
    for isin, cusips in several.items():
        agree = [c for c in cusips if same(c, isin)]
        if len(agree) == 1:
            offers[agree[0]].add(isin); cases["2 several CUSIPs, FIGI names one"] += 1
        else:
            cases["2 dropped: FIGI names none or several"] += 1
    by_figi = defaultdict(set)
    for c, figis in cf.items():
        for f in figis:
            by_figi[f].add(c)
    for isin in isin_only:
        held = set().union(*(by_figi.get(f, set()) for f in isf.get(isin, ())))
        if len(held) == 1:
            offers[next(iter(held))].add(isin); cases["3 ISIN-only, FIGI ties one CUSIP"] += 1
        elif held:
            cases["3 refused: FIGI ties several CUSIPs"] += 1
    holders = Counter(i for isins in offers.values() for i in isins)
    attached = {c: next(iter(i)) for c, i in offers.items() if len(i) == 1 and holders[next(iter(i))] == 1}
    cases["refused: a CUSIP offered two ISINs"] = sum(len(i) > 1 for i in offers.values())
    cases["refused: an ISIN offered to two CUSIPs"] = sum(n > 1 for n in holders.values())
    cases["CUSIP Securities carrying an ISIN"] = len(attached)
    report[name] = cases
print(json.dumps(report, indent=1))
