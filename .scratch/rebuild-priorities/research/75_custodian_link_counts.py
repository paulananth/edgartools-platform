"""Ticket 75: the CUSTODIAN links the 13 local Form ADV months state, counts only.

Each monthly file through the real chain (both source extracts with the
file's month end as `published`, combine.yaml, mdm.prepare, the two Dataset
Contracts), no MDM. Counts the links the filings state, how many name a
custodian identified by BD number or LEI (they can resolve) or by name only
(they wait), and the adviser-custodian pairs over the 13 months, with how
many were named in more than one month. Usage: 75_custodian_link_counts.py OUT"""
import calendar, json, sys, time
from collections import Counter
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read

ZIPS = sorted(Path.home().glob(
    ".local/share/edgartools/clean-mdm/proving/p07/inputs/warehouse/bronze/reference/iapd_adv_bulk/*/*.zip"))
NAME, FILINGS, CUSTODIANS = "iapd.adv", "iapd.adv.filings.v1", "iapd.adv.custodians.v1"
FOLDER = files.ROOT / "sources" / NAME
OUT = Path(sys.argv[1])
store = Artifacts()


def read(root, contract_file, raw, published):
    root.mkdir(parents=True, exist_ok=True)
    body = {"source": NAME, "execution": {"profile": "source.read", "workers": 1, "max_artifacts": 1},
            **files.load(FOLDER / contract_file)}
    context = store.put(root.as_uri(), {"version": 1, "input": raw, "values": {"published": published}})
    manifest = store.put(root.as_uri(), {"version": 2, "contract": store.put(root.as_uri(), body),
                                         "artifacts": [{"input": raw, "context": context}]})
    return source_read.execute({"input": manifest, "output": (root / "reading.json").as_uri(),
                                "checks": ["source.output"]}, store)


def records(root, reading, table, code, **keys):
    task = {"input": reading, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
            "keys": {"table": table, "dataset": code, "policy": "0" * 64, "consumer": "count",
                     "batch_id": f"count-{code}", "as_of": "2026-10-16T00:00:00+00:00",
                     "effective_column": "published", **keys}}
    prepared = mdm_prepare.execute(task, store)
    contract = files.source(NAME)["mdm"][code]["contract"]
    outcome, out = Counter(), []
    for b in store.json(prepared)["batches"]:
        for line in (root / b["input"]["path"]).read_bytes().splitlines():
            try:
                out.append(adapters.normalize(json.loads(line), source_code=code, contract=contract, publication={
                    **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                    "member": b["input"]["path"]}))
                outcome["accepted"] += 1
            except adapters.UnsupportedRecord as x:
                outcome[x.reason] += 1
    return out, outcome


def source_readings_rows(combined):
    """The combined filings rows (each with its `custodians`)."""
    from edgar_warehouse.workers import source_readings
    loaded = source_readings.load(combined, store, max_bytes=4 * 1024**3, max_rows=10**7)[0]
    return [row for a in loaded["artifacts"] for row in a["tables"]["filings"]]


start = time.monotonic()
totals, kinds, months_per_pair, per_filing = Counter(), Counter(), Counter(), Counter()
for z in ZIPS:
    y, m = map(int, z.parent.name.split("-"))
    published = f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}T00:00:00+00:00"
    root = OUT / z.parent.name
    raw = store.put_bytes((root / "capture.zip").as_uri(), z.read_bytes())
    filings = read(root / "filings", "adviser-filings-csv.yaml", raw, published)
    custody = read(root / "custody", "custody-csv.yaml", raw, published)
    m_ = store.put(root.as_uri(), {"version": 1, "contract": store.put(root.as_uri(), files.load(FOLDER / "combine.yaml")),
                                   "readings": {"filings": filings, "custody": custody}})
    combined = source_combine.execute({"input": m_, "output": (root / "combine/out.json").as_uri(),
                                       "checks": [source_combine.CHECK], "keys": {}}, store)
    custodians, c_out = records(root / "mdm-custodians", custody, "custody", CUSTODIANS, distinct_on=["custodian_id"])
    advisers, f_out = records(root / "mdm-filings", combined, "filings", FILINGS)
    totals.update({f"custodians_{k}": v for k, v in c_out.items()})
    totals.update({f"filings_{k}": v for k, v in f_out.items()})
    accepted = {adapters.subject_key(CUSTODIANS, r["provenance"]["record_key"]) for r in custodians}
    for f in advisers:
        links = [l for l in f.get("relationships") or [] if l["type"] == "CUSTODIAN"]
        per_filing[len(links)] += 1
        totals["links"] += len(links)
        totals["links_to_a_custodian_record_set_aside"] += sum(l["target_subject"] not in accepted for l in links)
    for row in source_readings_rows(combined):
        for custodian_id in row["custodians"]:
            kinds[custodian_id.split(":", 1)[0]] += 1
            months_per_pair[(row["crd"], custodian_id)] += 1
    print(z.parent.name, dict(totals), round(time.monotonic() - start), "s", flush=True)

pairs = Counter(k[1].split(":", 1)[0] for k in months_per_pair)
report = {"months": len(ZIPS), "records": {k: v for k, v in totals.items() if k != "links"},
          "links_stated": totals["links"], "links_by_custodian_id_kind": dict(kinds),
          "links_per_filing": dict(sorted(per_filing.items())),
          "adviser_custodian_pairs": len(months_per_pair), "pairs_by_custodian_id_kind": dict(pairs),
          "pairs_named_in_more_than_one_month": sum(1 for v in months_per_pair.values() if v > 1),
          "seconds": round(time.monotonic() - start)}
print(json.dumps(report, indent=1))
(OUT / "report.json").write_text(json.dumps(report, indent=1))
