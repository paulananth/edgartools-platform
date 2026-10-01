"""Hand-built dry run of the SEC Company feed's data quality on one capture.

Run from the repo root:  uv run --no-sync python <this file> [--limit N]
Reads only local files. Writes results beside this script.
"""
from __future__ import annotations

import argparse, copy, hashlib, json, sys, time
from collections import Counter, defaultdict
from pathlib import Path

from edgar_warehouse.loaders.bronze_submission_extractors import stage_address_loader, stage_company_loader
from edgar_warehouse.mdm.clean import company_source as cs
from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, mapped_values, normalize
from edgar_warehouse.mdm.clean.quality import counts
from edgar_warehouse.rules import files

CAP = Path.home() / ".local/share/edgartools/clean-mdm/captures/sec.submissions.company/cm05-7000"
OUT = Path(__file__).resolve().parent


def load_receipts():
    rows = [json.loads(l) for l in (CAP / "receipts.jsonl").read_text().splitlines() if l.strip()]
    return rows


def tickers_from_catalog(path: Path) -> dict[int, list[str]]:
    body = json.loads(path.read_bytes())
    i_cik, i_t = body["fields"].index("cik"), body["fields"].index("ticker")
    out: dict[int, list[str]] = {}
    for row in body["data"]:
        if row[i_cik] is None or not row[i_t]:
            continue
        out.setdefault(int(row[i_cik]), []).append(row[i_t])
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def build_row(payload: dict, sha: str, tickers: dict) -> dict:
    cik = int(payload["cik"])
    row = stage_company_loader(payload, cik, "dry-run", sha, "dry-run")[0]
    row["last_sync_run_id"] = row.pop("sync_run_id")
    business = None
    for a in stage_address_loader(payload, cik, "dry-run", sha, "dry-run"):
        if a["address_type"] == "business":
            business = cs.business_address(a)
    forms = sorted({f for f in ((payload.get("filings") or {}).get("recent") or {}).get("form") or [] if f})
    return {**row, "business_address": business, "forms": forms,
            "tickers": tickers.get(cik, []), "name_census": None, "_origin": {}}


def run(contract, rows, policy):
    """Return (all-filer quality per cik, normalize assertions, deferred)."""
    per_cik, assertions, deferred = {}, [], []
    for sha, key, row in rows:
        f = copy.deepcopy(row)
        try:
            fields, matching, q = mapped_values(f, contract)
            per_cik[row["cik"]] = {"quality": q, "fields": fields, "matching": matching}
        except UnsupportedRecord as exc:
            per_cik[row["cik"]] = {"exception": exc.args[0]}
        try:
            a = normalize(copy.deepcopy(row), source_code=cs.SOURCE_CODE, contract=contract, policy=policy,
                          publication={"artifact_sha256": sha, "member": key,
                                       "publication_key": "dry-run", "revision": 0})
            assertions.append(a)
        except UnsupportedRecord as exc:
            deferred.append({"reason": exc.args[0], "cik": row["cik"]})
    return per_cik, assertions, deferred


def all_filer_counts(per_cik):
    t = Counter()
    for v in per_cik.values():
        if "exception" in v:
            if v["exception"].startswith("quality_"):
                t["exception:" + v["exception"].removeprefix("quality_")] += 1
            continue
        q = v["quality"] or {}
        for fx in q.get("fixes") or {}:
            t["fixed:" + fx] += 1
        for w in q.get("withheld") or []:
            t["withheld:" + w] += 1
        for fl in q.get("flags") or []:
            t["flagged:" + fl] += 1
    return dict(sorted(t.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    t0 = time.time()
    receipts = load_receipts()
    cat = [r for r in receipts if "/reference/" in r["key"]]
    docs = sorted((r for r in receipts if "/submissions/" in r["key"]), key=lambda r: r["key"])
    if args.limit:
        docs = docs[: args.limit]
    cat_path = CAP / cat[0]["key"].removeprefix("warehouse/")
    assert hashlib.sha256(cat_path.read_bytes()).hexdigest() == cat[0]["sha256"], "catalog sha256"
    tickers = tickers_from_catalog(cat_path)
    rows, raw, mismatched = [], {}, []
    for r in docs:
        p = CAP / r["key"].removeprefix("warehouse/")
        b = p.read_bytes()
        if hashlib.sha256(b).hexdigest() != r["sha256"]:
            mismatched.append(r["key"]); continue
        payload = json.loads(b)
        rows.append((r["sha256"], r["key"], build_row(payload, r["sha256"], tickers)))
        raw[int(payload["cik"])] = {
            "name": payload.get("name"), "soi": payload.get("stateOfIncorporation"),
            "soi_desc": payload.get("stateOfIncorporationDescription"),
            "biz_state": ((payload.get("addresses") or {}).get("business") or {}).get("stateOrCountry"),
            "mail_state": ((payload.get("addresses") or {}).get("mailing") or {}).get("stateOrCountry"),
            "entity_type": payload.get("entityType"), "sic": payload.get("sic"),
            "sic_desc": payload.get("sicDescription"),
            "biz_street": ((payload.get("addresses") or {}).get("business") or {}).get("street1"),
        }
    t_read = time.time() - t0
    manifest = "\n".join(f"{s} {k}" for s, k, _ in rows) + "\n"
    batch_hash = hashlib.sha256((cat[0]["sha256"] + "\n" + manifest).encode()).hexdigest()
    (OUT / "input-manifest.txt").write_text(f"{cat[0]['sha256']} {cat[0]['key']}\n" + manifest)

    policy = files.policy()
    contract = cs.CONTRACT
    base_cik, base_a, base_d = run(contract, rows, policy)
    no_dc = copy.deepcopy(contract)
    no_dc["quality"]["fixes"] = [f for f in no_dc["quality"]["fixes"] if f["id"] != "dc_state_is_empty"]
    nodc_cik, nodc_a, nodc_d = run(no_dc, rows, policy)

    # examples per fix/check (all filers)
    examples = defaultdict(list)
    for cik, v in base_cik.items():
        if "exception" in v:
            k = "exception:" + v["exception"].removeprefix("quality_")
            examples[k].append({"cik": cik, "name": raw[cik]["name"]}); continue
        q = v["quality"] or {}
        for fx, d in (q.get("fixes") or {}).items():
            after = v["fields"].get("state_of_incorporation") if "state" in d["path"] else v["matching"].get("address")
            examples["fixed:" + fx].append({"cik": cik, "name": raw[cik]["name"], "original": d["original"], "after": after})
        for w in q.get("withheld") or []:
            examples["withheld:" + w].append({"cik": cik, "name": raw[cik]["name"], "address": v["matching"].get("address")})
        for fl in q.get("flags") or []:
            examples["flagged:" + fl].append({"cik": cik, "name": raw[cik]["name"],
                                              "state_of_incorporation": v["fields"].get("state_of_incorporation")})

    # DC analysis
    dc = []
    for cik, r in raw.items():
        if (r["soi"] or "").strip().upper() == "DC":
            b, n = base_cik[cik], nodc_cik[cik]
            dc.append({"cik": cik, **r,
                       "with_fix_state": b.get("fields", {}).get("state_of_incorporation"),
                       "with_fix_quality": b.get("quality"),
                       "without_fix_state": n.get("fields", {}).get("state_of_incorporation"),
                       "without_fix_flags": (n.get("quality") or {}).get("flags")})
    dc_mdm = {a["record_key"] for a in base_a if a["provenance"].get("quality", {}).get("fixes", {}).get("dc_state_is_empty")}

    # record-by-record diff, MDM-bound assertions
    def key(a):
        return a["record_key"]
    bmap, nmap = {key(a): a for a in base_a}, {key(a): a for a in nodc_a}
    diff = []
    for k in sorted(set(bmap) | set(nmap)):
        b, n = bmap.get(k), nmap.get(k)
        bf, nf = (b or {}).get("fields"), (n or {}).get("fields")
        if bf != nf or (b or {}).get("provenance", {}).get("quality") != (n or {}).get("provenance", {}).get("quality"):
            diff.append({"record_key": k,
                         "with_fix": {"state_of_incorporation": (bf or {}).get("state_of_incorporation"),
                                      "quality": (b or {}).get("provenance", {}).get("quality", {}).get("fixes", {}).get("dc_state_is_empty")},
                         "without_fix": {"state_of_incorporation": (nf or {}).get("state_of_incorporation"),
                                         "flags": (n or {}).get("provenance", {}).get("quality", {}).get("flags")}})

    result = {
        "sample": {"documents": len(docs), "sha_verified": len(rows), "sha_mismatch": mismatched,
                   "batch_hash": batch_hash, "read_seconds": round(t_read, 1),
                   "total_seconds": round(time.time() - t0, 1)},
        "quality_version": contract["quality"]["version"],
        "all_filers_counts": all_filer_counts(base_cik),
        "mdm_bound": {"assertions": len(base_a), "deferred_by_reason": dict(Counter(d["reason"] for d in base_d)),
                      "counts": counts(base_a, base_d)},
        "without_dc_fix": {"all_filers_counts": all_filer_counts(nodc_cik),
                           "mdm_bound_counts": counts(nodc_a, nodc_d)},
        "examples": {k: v[:10] for k, v in sorted(examples.items())},
        "dc": {"raw_dc_filers": len(dc), "dc_fixed_in_mdm_bound": len(dc_mdm),
               "soi_desc": dict(Counter(d["soi_desc"] for d in dc)),
               "business_state": dict(Counter(d["biz_state"] for d in dc)),
               "with_fix_state": dict(Counter(str(d["with_fix_state"]) for d in dc)),
               "records": dc},
        "record_diff_mdm_bound_with_vs_without_dc_fix": diff,
    }
    name = f"dry-run-{len(docs)}.json"
    (OUT / name).write_text(json.dumps(result, indent=1, default=str, ensure_ascii=False))
    print(json.dumps({k: result[k] for k in ("sample", "all_filers_counts", "mdm_bound", "without_dc_fix")}, indent=1))
    print("dc:", json.dumps({k: v for k, v in result["dc"].items() if k != "records"}, indent=1))
    print("diff records:", len(diff))


if __name__ == "__main__":
    main()
