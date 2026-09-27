"""Build records in the reader's shape from the captured files, then profile them.

The reader is `company_source.prepare_company_bundle`. It cannot be imported
while `rules/sources/sec.submissions.company/source.yaml` is missing, and it
reads landing Parquet plus a Name Census (needs a full GLEIF Golden Copy),
so the record is built by hand here from its code:
- silver rows: the repo's own extractors (`bronze_submission_extractors`) and
  `_parse_company_ticker_rows`, plus the stamps `_record_landing_passthrough`
  adds (`first_sync_run_id`, `last_sync_run_id`, `last_synced_at`);
- `forms`, `business_address`, `tickers`: company_source's collectors
  (`_filed_forms`, `_business_addresses`, `_catalog_tickers`), copied below;
- `name_census`: None (no census; the classification rule does not read it);
- `_origin`: the reader's keys, with scratch values.
Then runs the Company classification rule on each record.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from edgar_warehouse.loaders.bronze_submission_extractors import (
    is_individual_filer,
    stage_address_loader,
    stage_company_loader,
    stage_recent_filing_loader,
)
from edgar_warehouse.mdm.clean.classification import fired
from edgar_warehouse.mdm.clean.names import edgar_jurisdiction
from edgar_warehouse.rules import files
from edgar_warehouse.silver_landing_store import _parse_company_ticker_rows

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
RUN = "scratch-capture-run"
TICKER_RUN = "scratch-ticker-run"
STAMP = "2026-09-27T00:00:00+00:00"

catalog_path = ROOT / "tickers" / "company_tickers_exchange.json"
catalog_bytes = catalog_path.read_bytes()
ticker_rows = [
    {**r, "source_name": "company_tickers_exchange", "source_rank": i}
    for i, r in enumerate(_parse_company_ticker_rows(json.loads(catalog_bytes)), 1)
]
# company_source._catalog_tickers
listed: dict[int, list[tuple]] = {}
for row in ticker_rows:
    if row["cik"] is None or not row["ticker"]:
        continue
    listed.setdefault(int(row["cik"]), []).append((row["source_rank"], row["ticker"]))
catalog = {cik: [t for _, t in sorted(pairs)] for cik, pairs in listed.items()}

policy = files.policy()
rule = next(r for r in policy["kinds"]["company"]["rules"] if r["rule_id"] == "sec-company-candidate")

records, individuals = [], []
for f in sorted((ROOT / "submissions").glob("*.json")):
    raw = f.read_bytes()
    doc = json.loads(raw)
    cik = int(doc["cik"])
    sha = hashlib.sha256(raw).hexdigest()  # raw_object_id is the document's sha256
    if is_individual_filer(doc):
        individuals.append((doc["cik"], doc["name"]))
        continue
    (company,) = stage_company_loader(doc, cik, RUN, sha, "bootstrap_full")
    company = {"first_sync_run_id": RUN, **company, "last_sync_run_id": RUN, "last_synced_at": STAMP}
    forms = sorted({r["form"] for r in stage_recent_filing_loader(doc, cik, RUN, sha, "bootstrap_full") if r["form"]})
    business = None
    for row in stage_address_loader(doc, cik, RUN, sha, "bootstrap_full"):
        if row["address_type"] != "business":
            continue
        place = edgar_jurisdiction(row["state_or_country"] or row.get("country_code"))
        business = {
            "street": row["street1"] or None,
            "street2": row["street2"] or None,
            "city": row["city"] or None,
            "region": row["state_or_country"] or None,
            "postal_code": row["zip_code"] or None,
            "country": place.split("-")[0] if place else None,
        }
    record = {
        **company,
        "forms": forms,
        "business_address": business,
        "tickers": catalog.get(cik, []),
        "name_census": None,
        "_origin": {
            "member": "sec_company/.../sec_company.parquet",
            "sha256": "<sha256 of the sec_company parquet>",
            "row_ordinal": len(records) + 1,
            "manifest_sha256": "<sha256 of the landing manifest>",
            "name_census_sha256": "<not built>",
            "bronze": {"object": f"submissions/{f.name}", "sha256": sha, "locator": "$"},
        },
    }
    records.append(record)

OUT.write_text("\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n")
print(f"individuals dropped by is_individual_filer: {len(individuals)}")
for c, n in individuals:
    print(f"  {c} {n}")
print(f"records in the reader's shape: {len(records)}  (written to {OUT})")
print("keys:", sorted(records[0]))
steps = Counter()
for r in records:
    verdict, step = fired(rule, r, policy["kinds"]["company"])
    steps[(step, verdict)] += 1
    print(
        f"  {r['cik']:>8} {r['entity_type']:9} sic={r['sic']!r:7} soi={r['state_of_incorporation']!r:5} "
        f"ein={r['ein']!r:12} tickers={r['tickers']} forms={r['forms'][:5]}{'...' if len(r['forms']) > 5 else ''} "
        f"biz={(r['business_address'] or {}).get('postal_code')!r}/{(r['business_address'] or {}).get('country')!r} "
        f"-> step {step}: {verdict}  | {r['entity_name']}"
    )
print("by step:", dict(steps))
