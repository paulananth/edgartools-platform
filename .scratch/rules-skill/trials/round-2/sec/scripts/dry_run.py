"""Step 7 dry run of sec.submissions.company.v1 (no databases, local files only).

1. Land the captured files with the repo's own writers into a local landing
   root: SilverLandingStore.stage_submission per submissions file (one capture
   run), replace_company_tickers for both catalogs (one ticker run), flushed by
   write_landing_export. No pagination pages are captured, so none are passed.
2. Name Census: BUILT BY HAND. `mdm name-census` needs a full GLEIF Golden
   Copy, which the trial does not have. The SEC side is counted with the real
   code (census_filers + sec_keys); the GLEIF side is empty.
3. Run the reader, prepare_company_bundle, on the landing (limit 1000).
   No bronze receipts: that command needs the bookkeeping database.
4. Put every bundled record through adapters.normalize with this contract,
   files.policy() and the skill's dry-run publication.
"""
import hashlib, json, sys
from datetime import UTC, datetime
from pathlib import Path

from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.serving.silver_landing_writer import write_landing_export
from edgar_warehouse.silver_landing_store import SilverLandingStore, _parse_company_ticker_rows
from edgar_warehouse.rules import files
from edgar_warehouse.mdm.clean import company_source
from edgar_warehouse.mdm.clean.activation import check_policy
from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.name_census import VERSION, SEC_NORMALIZER, GLEIF_NORMALIZER, sec_legal_form_key
from tests.support.retired_name_census import sec_keys
from edgar_warehouse.mdm.clean.store import canonical, digest

IN, OUT = Path(sys.argv[1]), Path(sys.argv[2])
ROOT = OUT / "landing"
DATE, NOW = "2026-09-26", datetime(2026, 9, 26, tzinfo=UTC)
CAPTURE, TICKERS = "dryrun-capture-0001", "dryrun-tickers-0001"
SOURCE = "sec.submissions.company.v1"


def flush(buffer, run_id, command):
    counts = write_landing_export(buffer, StorageLocation(str(ROOT)), run_id=run_id, business_date=DATE,
                                  command_name=command, environment_name="trial", now=NOW)
    rel = default_path_resolver().snowflake_export_run_manifest_path(
        workflow_name=f"silver_landing_{command}".replace("-", "_"), business_date=DATE, run_id=run_id)
    return counts, str(ROOT / rel)


# 1. landing
cap = LandingExportBuffer()
store = SilverLandingStore(landing_export=cap)
staged = {}
for f in sorted((IN / "submissions").glob("*.json")):
    raw = f.read_bytes()
    payload = json.loads(raw)
    r = store.stage_submission(cik=int(payload["cik"]), main_payload=payload, pagination_payloads=[],
                               sync_run_id=CAPTURE, raw_object_id=hashlib.sha256(raw).hexdigest(),
                               load_mode="dry_run")
    staged[payload["cik"]] = r["company_rows_written"]
cap_counts, cap_manifest = flush(cap, CAPTURE, "rules-dry-run-capture")
tick = LandingExportBuffer()
tstore = SilverLandingStore(landing_export=tick)
for name in ("company_tickers", "company_tickers_exchange"):
    doc = json.loads((IN / "tickers" / f"{name}.json").read_bytes())
    tstore.replace_company_tickers(_parse_company_ticker_rows(doc), TICKERS, source_name=name)
tick_counts, tick_manifest = flush(tick, TICKERS, "rules-dry-run-tickers")
print("capture landing:", cap_counts)
print("ticker landing:", tick_counts)
print("filers NOT landed as sec_company (is_individual_filer):",
      sorted(c for c, n in staged.items() if not n))

# 2. hand-built Name Census (SEC side real, GLEIF side empty)
filers, population = company_source.census_filers(landing_root=str(ROOT), landing_manifest=cap_manifest)
by_key = sec_keys(filers)
wanted = {sec_legal_form_key(n) for _, n, _ in filers} - {""}
census = {
    "version": VERSION,
    "normalizers": {"sec": SEC_NORMALIZER, "gleif": GLEIF_NORMALIZER},
    "sec": population,
    "gleif": {"archive_sha256": None, "content_date": None,
              "file_content": "NONE (trial: no GLEIF Golden Copy)", "record_count": 0},
    "entries": {k: {"ciks": sorted(by_key[k])[:5], "cik_count": len(by_key[k]), "leis": [],
                    "lei_count": 0, "other_name_holders": 0} for k in sorted(wanted)},
}
census_path = OUT / "name-census.json"
census_path.write_text(canonical(census) + "\n")

# 3. the reader
bundle = OUT / "bundle"
report = company_source.prepare_company_bundle(
    landing_root=str(ROOT), landing_manifest=cap_manifest, ticker_manifest=tick_manifest,
    name_census=str(census_path), output=str(bundle), limit=1000, as_of="2026-09-26T00:00:00Z", revision=0)
print("reader scope:", json.dumps(report["scope"], sort_keys=True))
contract = files.mdm_contract("sec.submissions.company", SOURCE)
print("bundle dataset.json == rules file contract:",
      json.loads((bundle / "dataset.json").read_text()) == contract)

# 4. normalize
policy = files.policy()
check_policy(policy)
raw = (bundle / "records.jsonl").read_bytes()
publication = {"artifact_sha256": hashlib.sha256(raw).hexdigest(), "member": "records.jsonl",
               "publication_key": "dry-run", "revision": 0}
assertions, deferred = [], []
for ordinal, line in enumerate(raw.splitlines(), 1):
    row = json.loads(line)
    try:
        assertions.append(normalize(row, source_code=SOURCE, contract=contract,
                                    publication=publication, policy=policy))
    except UnsupportedRecord as exc:
        deferred.append({"line": ordinal, "cik": row.get("cik"), "name": row.get("entity_name"),
                         "reason": exc.reason, "probable_kind": exc.probable_kind, **exc.detail})
(OUT / "assertions.json").write_text(json.dumps(assertions, indent=1, sort_keys=True))
(OUT / "deferred.json").write_text(json.dumps(deferred, indent=1, sort_keys=True))

print(f"\nrecords {len(raw.splitlines())}: assertions {len(assertions)}, set aside {len(deferred)}")
for a in assertions:
    f = {k: (v.get("value") if v["op"] == "value" else None) for k, v in a["fields"].items()}
    print(f"\nCOMPANY {a['record_key']} kind={a['kind']} ids={a['identifiers']} "
          f"step={a['provenance']['classification']['step']} schema={a['schema_version']}")
    for k, v in f.items():
        print(f"    {k:24s} {v}")
    print(f"    matching: postal={a['provenance']['matching']['business_postal_code']} "
          f"country={a['provenance']['matching']['business_country']} "
          f"census={ {k: a['provenance']['matching']['name_census'][k] for k in ('key','cik_count','lei_count')} if a['provenance']['matching']['name_census'] else None}")
print("\nSET ASIDE (each opens a blocking review: no non-blocking reasons):")
for d in deferred:
    c = d.get("classification", {})
    print(f"  {d['cik']:>8} {d['reason']:32s} step={c.get('step')} probable={d['probable_kind']} | {d['name']}")
