"""L7: ADV records mapped by the contract's reading equal the old mapping, record for record.

Ran 2026-10-13 06:33 ET on this branch before the old mapping was deleted
(1.5 min; result: l7-adv-equivalence.json). It needs a checkout that still has
the old mapping, so it cannot run after L7:
    uv run python l7_adv_equivalence.py <local iapd_adv_bulk folder>
"""
import calendar, collections, copy, hashlib, json, sys
from pathlib import Path
from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine

ROOT = Path(sys.argv[1])
READS = {"iapd.adv.filings.v1": ("adviser-filings-csv.yaml", "filings"),
         "iapd.adv.custodians.v1": ("custody-csv.yaml", "custody")}
summary = {}
for code, (name, table) in READS.items():
    configured = files.mdm_contract("iapd.adv", code)
    retained = copy.deepcopy(configured); retained["adapter"].pop("reading")
    engine = SourceEngine(files.load(files.ROOT / "sources/iapd.adv" / name))
    counts, differ = collections.Counter(), []
    for zipped in sorted(ROOT.glob("*/*.zip")):
        y, m = map(int, zipped.parent.name.split("-"))
        published = f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
        data = zipped.read_bytes()
        rows = engine.read(data, context={"published": published}).tables[table]
        pub = {"artifact_sha256": hashlib.sha256(data).hexdigest(), "member": table,
               "publication_key": hashlib.sha256(data).hexdigest(), "revision": 0, "effective_at": published + "T23:59:59+00:00"}
        for row in rows:
            def run(body):
                try:
                    return ("assertion", digest(adapters.normalize(row, source_code=code, contract=body, publication=pub)))
                except adapters.UnsupportedRecord as e:
                    return ("deferred", e.reason)
            a, b = run(configured), run(retained)
            counts[a[0] if a[0] == "assertion" else a[1]] += 1
            counts["equal" if a == b else "differ"] += 1
            if a != b and len(differ) < 5:
                differ.append({"month": zipped.parent.name, "reading": a, "old": b})
    summary[code] = {"counts": dict(counts), "first_differences": differ}
print(json.dumps(summary, indent=1, sort_keys=True))
