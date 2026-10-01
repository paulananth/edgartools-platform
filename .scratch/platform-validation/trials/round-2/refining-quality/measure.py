"""Measure the draft business_postcode_present check on the pinned cm05-7000 capture.

Offline, read-only against the repo. Writes results to work2/measure.json.
"""
import hashlib, json, re, sys
from collections import Counter
from pathlib import Path

from edgar_warehouse.rules import files
from edgar_warehouse.loaders.bronze_submission_extractors import stage_company_loader, stage_address_loader
from edgar_warehouse.mdm.clean import company_source, adapters, quality
from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, mapped_values, normalize

W = Path("/Users/aneenaananth/.local/share/edgartools/clean-mdm/trials/refining-quality/work2")
DRAFT = W / "rules"
REPO = Path("/Users/aneenaananth/projects/edgartools-platform-worktrees/claude-skills-4/rules")
CAP = Path("/Users/aneenaananth/.local/share/edgartools/clean-mdm/captures/sec.submissions.company/cm05-7000")
SRC, CODE = "sec.submissions.company", "sec.submissions.company.v1"

# --- pin -------------------------------------------------------------------------
receipts_raw = (CAP / "receipts.jsonl").read_bytes()
batch_hash = hashlib.sha256(receipts_raw).hexdigest()
receipts = [json.loads(l) for l in receipts_raw.decode().splitlines() if l.strip()]
bad = []
for r in receipts:
    p = CAP / "bronze" / r["key"].removeprefix("warehouse/bronze/")
    b = p.read_bytes()
    if hashlib.sha256(b).hexdigest() != r["sha256"] or len(b) != r["bytes"]:
        bad.append(r["key"])
if bad:
    sys.exit(f"pin failed: {len(bad)} files differ, e.g. {bad[:3]}")

# --- tickers from the pinned catalog (the classification rule reads `tickers`) ---
cat = next(r for r in receipts if "company_tickers_exchange" in r["key"])
catalog = json.loads((CAP / "bronze" / cat["key"].removeprefix("warehouse/bronze/")).read_text())
ci, ti = catalog["fields"].index("cik"), catalog["fields"].index("ticker")
tickers: dict[int, list[str]] = {}
for row in catalog["data"]:
    if row[ci] is not None and row[ti]:
        tickers.setdefault(int(row[ci]), [])
        if row[ti] not in tickers[int(row[ci])]:
            tickers[int(row[ci])].append(row[ti])

# --- rows ------------------------------------------------------------------------
def build(r):
    path = CAP / "bronze" / r["key"].removeprefix("warehouse/bronze/")
    payload = json.loads(path.read_bytes())
    cik = int(re.search(r"cik=(\d+)", r["key"]).group(1))
    row = stage_company_loader(payload, cik, "dry-run", r["sha256"], "dry-run")[0]
    biz = [a for a in stage_address_loader(payload, cik, "dry-run", r["sha256"], "dry-run") if a["address_type"] == "business"]
    row["business_address"] = company_source.business_address(biz[0]) if biz else None
    row["forms"] = sorted({f for f in ((payload.get("filings") or {}).get("recent") or {}).get("form", []) if f})
    row["tickers"] = tickers.get(cik, [])
    return row, r, biz[0] if biz else None

subs = [r for r in receipts if "/submissions/" in r["key"]]
rows = [build(r) for r in subs]

draft = files.mdm_contract(SRC, CODE, root=DRAFT)
base = files.mdm_contract(SRC, CODE, root=REPO)
quality.check_quality(draft["quality"])
policy = files.policy(root=DRAFT)

def cls(biz_raw, row):
    a = row["business_address"]
    if a is None:
        return "no_business_address"
    return "US" if a.get("country") == "US" else ("foreign" if a.get("country") else "country_unknown")

def run(contract, label):
    allf = Counter(); allflag = []; allexc = Counter()
    assertions, deferred = [], []
    for row, r, biz_raw in rows:
        try:
            f, m, q = mapped_values(row, contract)
            for fl in (q or {}).get("flags", []):
                allf[fl] += 1
            if "business_postcode_present" in (q or {}).get("flags", []):
                allflag.append((row, biz_raw))
        except UnsupportedRecord as e:
            allexc[e.args[0]] += 1
        pub = {"artifact_sha256": r["sha256"], "member": r["key"], "publication_key": "dry-run", "revision": 0}
        try:
            assertions.append(normalize(row, source_code=CODE, contract=contract, publication=pub, policy=policy))
        except UnsupportedRecord as e:
            deferred.append({"reason": e.args[0], "cik": row["cik"]})
    return dict(all_flags=allf, all_exceptions=allexc, flagged=allflag, assertions=assertions, deferred=deferred)

new = run(draft, "draft")
old = run(base, "repo")

# records MDM receives, flagged by the new check
def flagged_ids(assertions):
    return [a for a in assertions if "business_postcode_present" in (((a.get("provenance") or {}).get("quality") or {}).get("flags") or [])]

mdm_flagged = flagged_ids(new["assertions"])
mdm_ciks = set()
for a in mdm_flagged:
    mdm_ciks.add(json.dumps(a.get("record_key") or a.get("subject") or "", sort_keys=True))

def breakdown(pairs):
    c = Counter()
    for row, biz_raw in pairs:
        c[cls(biz_raw, row)] += 1
    return dict(c)

def example(row, biz_raw):
    return {"cik": f"{row['cik']:010d}", "name": row["entity_name"], "entity_type": row["entity_type"],
            "business_address_mapped": row["business_address"],
            "raw_zip": None if biz_raw is None else biz_raw["zip_code"],
            "raw_state_or_country": None if biz_raw is None else biz_raw["state_or_country"]}

# MDM-side breakdown: map assertion back to row by cik
by_cik = {f"{row['cik']:010d}": (row, b) for row, r, b in rows}
def a_cik(a):
    s = json.dumps(a)
    m = re.search(r'"(\d{10})"', s)
    return m.group(1) if m else None
mdm_pairs = [by_cik[a_cik(a)] for a in mdm_flagged if a_cik(a) in by_cik]

# before/after, record by record, on what MDM receives
def body_wo_quality(a):
    a = json.loads(json.dumps(a, default=str))
    q = (a.get("provenance") or {}).get("quality")
    if q:
        q.pop("version", None); q.pop("flags", None)
    for k in list(a):
        if k in ("assertion_id", "fingerprint", "record_fingerprint", "id"):
            a.pop(k)
    return a
pairs_same_len = len(new["assertions"]) == len(old["assertions"])
other_diffs = 0
if pairs_same_len:
    for x, y in zip(new["assertions"], old["assertions"]):
        qx = ((x.get("provenance") or {}).get("quality") or {})
        qy = ((y.get("provenance") or {}).get("quality") or {})
        fx = [f for f in qx.get("flags", []) if f != "business_postcode_present"]
        if fx != qy.get("flags", []) or qx.get("withheld") != qy.get("withheld") or qx.get("fixes") != qy.get("fixes") or x.get("fields") != y.get("fields"):
            other_diffs += 1

# controls (made-up TEST INPUTS)
def control(addr):
    row = {"cik": 9999999999, "entity_name": "TEST INPUT CONTROL CORP", "business_address": addr}
    return mapped_values(row, draft)[2].get("flags", [])
controls = {
    "TEST INPUT: address without postcode": control({"street": "1 MAIN ST", "city": "SPRINGFIELD", "region": "US-IL", "postal_code": None, "country": "US"}),
    "TEST INPUT: address with postcode": control({"street": "1 MAIN ST", "city": "SPRINGFIELD", "region": "US-IL", "postal_code": "62701", "country": "US"}),
    "TEST INPUT: no business address": control(None),
}

out = {
    "batch_hash": batch_hash,
    "files_pinned": len(receipts), "submissions_documents": len(subs), "pin_mismatches": 0,
    "all_filers": {"n": len(rows), "flags": dict(new["all_flags"]), "exceptions": dict(new["all_exceptions"]),
                   "postcode_flagged": len(new["flagged"]), "postcode_breakdown": breakdown(new["flagged"])},
    "mdm_receives": {"assertions": len(new["assertions"]), "deferred": len(new["deferred"]),
                     "deferred_reasons": dict(Counter(d["reason"] for d in new["deferred"])),
                     "quality_counts": quality.counts(new["assertions"], new["deferred"]),
                     "postcode_flagged": len(mdm_flagged), "postcode_breakdown": breakdown(mdm_pairs)},
    "repo_v1_quality_counts": quality.counts(old["assertions"], old["deferred"]),
    "before_after": {"same_assertion_count": pairs_same_len, "records_differing_other_than_new_flag": other_diffs,
                     "records_gaining_flag": len(mdm_flagged)},
    "controls": controls,
    "examples_all_filers": [example(*p) for p in new["flagged"][:10]],
    "examples_mdm_receives": [example(*p) for p in mdm_pairs[:10]],
    "examples_mdm_address_without_postcode": [example(*p) for p in mdm_pairs if p[0]["business_address"] is not None][:10],
}
(W / "measure.json").write_text(json.dumps(out, indent=2, default=str))
print(json.dumps({k: v for k, v in out.items() if not k.startswith("examples")}, indent=2, default=str))
