"""Ticket 22: what the SEC and GLEIF quality rules do on the ticket 08 inputs.

The proof the operator reads before approving a quality version (Q6): exact
counts per fix and check, and up to 10 examples of each. It also measures the
over-shared address threshold (Q8): how many entities 10, 25 and 100 entities
per address would withhold, per source and across both.

SEC: each filer of the bronze scan becomes the landing row the SEC reader
writes (`company_source`: the business address, its country read from
`stateOrCountry`, else `countryCode`, through `edgar_jurisdiction`), then the
production `adapters.normalize` runs on it with the repo's SEC contract and
merge rules. So the counts are what a run reports. Records `normalize` sets
aside for reasons other than quality are counted as `deferred:<reason>`.

GLEIF: the extract holds each record's parsed values, not the XML the native
reader reads, so its fields are rebuilt as the GLEIF contract maps them (the
legal name, the legal address) and `quality.apply` runs on them. Only
GENERAL entities, as the Company rules take.

Over-shared addresses count only addresses the quality rule left fit to
match on: a registered agent's or a placeholder street is already withheld.

    python .scratch/company-mastering/research/22-quality-proving-run.py \\
        <cm08-sec-scan.jsonl> <cm08-gleif-all.jsonl> <out.json>
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.company_source import CONTRACT, SOURCE_CODE
from edgar_warehouse.mdm.clean.names import edgar_jurisdiction
from edgar_warehouse.mdm.clean.quality import apply, withheld
from edgar_warehouse.rules import files

EXAMPLES = 10


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sec_row(f: dict) -> dict:
    """The SEC reader's landing row for one filer (`company_source`)."""
    b = (f.get("addresses") or {}).get("business") or {}
    place = edgar_jurisdiction(b.get("stateOrCountry") or b.get("countryCode"))
    return {
        "cik": int(f["cik"]),
        "entity_name": f.get("name") or None,
        "entity_type": f.get("entityType") or None,
        "sic": f.get("sic") or None,
        "state_of_incorporation": f.get("stateOfIncorporation") or None,
        "business_address": {
            "street": b.get("street1") or None,
            "street2": b.get("street2") or None,
            "city": b.get("city") or None,
            "region": b.get("stateOrCountry") or None,
            "postal_code": b.get("zipCode") or None,
            "country": place.split("-")[0] if place else None,
        },
        "last_sync_run_id": "proving-run",
        "last_synced_at": "2026-09-28T00:00:00+00:00",
        "raw_object_id": f.get("key"),
    }


def gleif_fields(e: dict) -> dict:
    a = e.get("legal") or {}
    lines = a.get("lines") or []
    address = {k: v for k, v in {
        "street": lines[0] if lines else None, "street2": "\n".join(lines[1:]) or None,
        "city": a.get("city"), "region": a.get("region"), "postcode": a.get("postal"), "country": a.get("country"),
    }.items() if v}
    return {"name": e.get("legal_name") or None, "address": address or None}


class Tally:
    def __init__(self):
        self.counts, self.examples = Counter(), defaultdict(list)
        self.shared = defaultdict(set)

    def example(self, key, item):
        if len(self.examples[key]) < EXAMPLES:
            self.examples[key].append(item)

    def record(self, key, name, address, q, matching, fields):
        self.counts["records"] += 1
        for fix, change in (q.get("fixes") or {}).items():
            self.counts[f"fixed:{fix}"] += 1
            path = change["path"]
            now = (matching if path.startswith("matching.") else fields).get(path.split(".", 1)[1])
            self.example(f"fixed:{fix}", {"key": key, "name": name, "original": change["original"], "now": now})
        for path in q.get("withheld") or []:
            self.counts[f"withheld:{path}"] += 1
            self.example(f"withheld:{path}", {"key": key, "name": name, "address": address})
        for flag in q.get("flags") or []:
            self.counts[f"flagged:{flag}"] += 1
            self.example(f"flagged:{flag}", {"key": key, "name": name,
                                             "state_of_incorporation": fields.get("state_of_incorporation")})
        std = matching.get("address") or {}
        if std.get("street") and not withheld({"provenance": {"quality": q}}, "matching.address"):
            where = (std["street"].split("\n")[0], (std.get("postcode") or "")[:5], std.get("country") or "")
            self.shared[where].add(key)


def sec(path: str) -> Tally:
    policy, tally = files.policy(), Tally()
    publication = {"publication_key": "proving-run", "revision": 0, "artifact_sha256": "0" * 64, "member": path}
    for n, line in enumerate(open(path)):
        if n % 20000 == 0:
            print(f"sec {n}", file=sys.stderr, flush=True)
        row = sec_row(json.loads(line))
        try:
            found = normalize(row, source_code=SOURCE_CODE, contract=CONTRACT, publication=publication, policy=policy)
        except UnsupportedRecord as exc:
            key = (f"exception:{exc.reason.removeprefix('quality_')}" if exc.reason.startswith("quality_")
                   else f"deferred:{exc.reason}")
            tally.counts[key] += 1
            tally.example(key, {"key": row["cik"], "name": row["entity_name"]})
            continue
        prov = found["provenance"]
        fields = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in found["fields"].items()}
        tally.record(row["cik"], row["entity_name"], row["business_address"], prov.get("quality") or {},
                     prov.get("matching") or {}, fields)
    return tally


def gleif(path: str, block: dict) -> Tally:
    tally = Tally()
    for n, line in enumerate(open(path)):
        if n % 500000 == 0:
            print(f"gleif {n}", file=sys.stderr, flush=True)
        e = json.loads(line)
        if e.get("category") != "GENERAL":
            continue
        fields, matching = gleif_fields(e), {}
        address = fields.get("address")
        try:
            q = apply(block, fields, matching)
        except UnsupportedRecord as exc:
            key = f"exception:{exc.reason.removeprefix('quality_')}"
            tally.counts[key] += 1
            tally.example(key, {"key": e["lei"], "name": e.get("legal_name")})
            continue
        tally.record(e["lei"], e.get("legal_name"), address, q, matching, fields)
    return tally


def thresholds(shared: dict) -> dict:
    out = {}
    for limit in (10, 25, 100):
        over = sorted(((len(v), k) for k, v in shared.items() if len(v) > limit), reverse=True)
        out[f"more than {limit}"] = {
            "addresses": len(over), "entities withheld": sum(n for n, _ in over),
            "largest": [[n, " / ".join(filter(None, k))] for n, k in over[:10]],
        }
    return out


def main(scan_path, gleif_path, out_path):
    gleif_block = files.source("gleif")["mdm"]["gleif.level1.v1"]["contract"]["quality"]
    s = sec(scan_path)
    g = gleif(gleif_path, gleif_block)
    both = defaultdict(set)
    for tally, tag in ((s, "sec"), (g, "gleif")):
        for where, keys in tally.shared.items():
            both[where] |= {f"{tag}:{k}" for k in keys}
    out = {
        "inputs": {"sec_scan": {"path": scan_path, "sha256": sha256(scan_path)},
                   "gleif": {"path": gleif_path, "sha256": sha256(gleif_path)}},
        "sec": {"version": CONTRACT["quality"]["version"], "counts": dict(sorted(s.counts.items())),
                "examples": s.examples, "over_shared": thresholds(s.shared)},
        "gleif": {"version": gleif_block["version"], "counts": dict(sorted(g.counts.items())),
                  "examples": g.examples, "over_shared": thresholds(g.shared)},
        "over_shared_across_both": thresholds(both),
    }
    with open(out_path, "w") as w:
        json.dump(out, w, indent=1, sort_keys=True, default=str)
    summary = {k: {"counts": out[k]["counts"]} for k in ("sec", "gleif")}
    for k in ("sec", "gleif"):
        summary[k]["over_shared"] = {t: x["entities withheld"] for t, x in out[k]["over_shared"].items()}
    summary["both"] = {t: x["entities withheld"] for t, x in out["over_shared_across_both"].items()}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
