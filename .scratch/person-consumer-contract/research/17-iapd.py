"""Research 17: IAPD lookups to settle ADV homonym-candidate pairs (stratum H) that offline
evidence cannot settle. Fair-access rules from the brief: User-Agent from EDGAR_IDENTITY,
<= 1 request/s, stop on any 403/429, hard cap 300, every request logged to
research/17-iapd-requests.jsonl. Individual endpoint only (research 16 F2 shape). Ids already
probed by research 16 are reused from 16-results.jsonl, not re-requested.

Run: R17_ALLOW_NET=1 EDGAR_IDENTITY="..." uv run --no-project --with requests python 17-iapd.py
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import requests

os.environ.setdefault("R17_ALLOW_NET", "1")
spec = importlib.util.spec_from_file_location("c17", Path(__file__).with_name("17-common.py"))
c17 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c17)

UA = os.environ.get("EDGAR_IDENTITY") or "EdgarTools Platform research theananthfamily@gmail.com"
CAP = 300
LOG = c17.HERE / "17-iapd-requests.jsonl"
RES = c17.HERE / "17-iapd-results.jsonl"
RAW = c17.R17 / "iapd_raw"
RAW.mkdir(parents=True, exist_ok=True)
IND = "https://api.adviserinfo.sec.gov/search/individual/{id}"


def n_logged() -> int:
    return sum(1 for _ in open(LOG)) if LOG.exists() else 0


class Stop(Exception):
    pass


def get(url: str) -> requests.Response:
    n = n_logged()
    if n >= CAP:
        raise Stop(f"cap {CAP} reached")
    time.sleep(1.0)
    ts = dt.datetime.now(dt.timezone.utc)
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=30)
    with open(LOG, "a") as f:
        f.write(json.dumps({"n": n + 1, "ts_utc": ts.isoformat(), "url": url, "status": r.status_code,
                            "bytes": len(r.content)}) + "\n")
    if r.status_code in (403, 429):
        raise Stop(f"HTTP {r.status_code} on request {n + 1}")
    return r


def summarise(owner_id: str, r: requests.Response) -> dict:
    out = {"owner_id": owner_id, "http_status": r.status_code, "resolves": False}
    try:
        j = r.json()
    except Exception:
        out["error"] = "non-json"
        return out
    hits = j.get("hits", {}).get("hits", [])
    out["hits_total"] = j.get("hits", {}).get("total")
    recs = []
    for h in hits:
        src = h.get("_source", {}).get("iacontent")
        try:
            recs.append(json.loads(src) if isinstance(src, str) else src)
        except Exception:
            recs.append({"_raw": str(src)[:200]})
    with open(RAW / f"{owner_id}.json", "w") as f:
        json.dump(recs, f)
    for rec in recs:
        bi = rec.get("basicInformation", {}) or {}
        if str(bi.get("individualId")) != str(owner_id):
            continue
        out["resolves"] = True
        out["name"] = {k: bi.get(k) for k in ("firstName", "middleName", "lastName")}
        out["otherNames"] = bi.get("otherNames") or []
        out["bcScope"] = bi.get("bcScope")
        out["iaScope"] = bi.get("iaScope")
        out["daysInIndustry"] = bi.get("daysInIndustry")
        emp = []
        for k in ("currentEmployments", "currentIAEmployments", "previousEmployments", "previousIAEmployments"):
            for e in rec.get(k) or []:
                emp.append({"list": k, "firmId": e.get("firmId"), "firmName": e.get("firmName"),
                            "begin": e.get("registrationBeginDate"), "end": e.get("registrationEndDate"),
                            "city": (e.get("branchOfficeLocations") or [{}])[0].get("city") if e.get("branchOfficeLocations") else None})
        out["employments"] = emp
        out["firm_ids"] = sorted({str(e["firmId"]) for e in emp if e.get("firmId") is not None})
        out["n_registrations"] = len(rec.get("registeredStates") or []) if isinstance(rec.get("registeredStates"), list) else None
        out["disclosureFlag"] = rec.get("disclosureFlag")
        out["hasDisclosure"] = rec.get("hasDisclosure")
        out["examsPassed"] = [x.get("examCategory") for x in (rec.get("stateExamCategory") or []) + (rec.get("principalExamCategory") or []) + (rec.get("productExamCategory") or []) if isinstance(x, dict)]
    return out


def main(ids: list[str]) -> None:
    done = set()
    if RES.exists():
        for line in open(RES):
            done.add(json.loads(line)["owner_id"])
    # research 16 results are reused, never re-requested
    r16 = {}
    for line in open(c17.HERE / "16-results.jsonl"):
        d = json.loads(line)
        if d["endpoint"] == "individual":
            r16[d["owner_id"]] = d
    for oid in ids:
        if oid in done:
            continue
        if oid in r16:
            d = r16[oid]
            with open(RES, "a") as f:
                f.write(json.dumps({"owner_id": oid, "reused_from": "16-results.jsonl", "resolves": d["resolves"],
                                    "name": d.get("iapd_name"), "otherNames": (d.get("iapd_name") or {}).get("otherNames"),
                                    "bcScope": d.get("bcScope"), "iaScope": d.get("iaScope"),
                                    "firm_ids": d.get("history_firm_ids"), "employments": None}) + "\n")
            done.add(oid)
            continue
        try:
            r = get(IND.format(id=oid))
        except Stop as e:
            print("STOP:", e, file=sys.stderr)
            return
        s = summarise(oid, r)
        s["ts_et"] = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=-4))).isoformat(timespec="seconds")
        with open(RES, "a") as f:
            f.write(json.dumps(s) + "\n")
        done.add(oid)


if __name__ == "__main__":
    ids = [l.strip() for l in open(sys.argv[1]) if l.strip()]
    print("requested", len(ids), "already logged", n_logged())
    main(ids)
    print("done; logged", n_logged())
