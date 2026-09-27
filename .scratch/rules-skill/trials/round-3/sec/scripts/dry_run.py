"""Step 7 dry run: the real reader on a 10-filer sample, then the mapping.

Stands in for `edgar-warehouse rules check` (not built). No database, no network.
1. Capture: the repo's own writer (`SilverLandingStore.stage_submission`) on 10
   captured submissions files, flushed by `write_landing_export` to local Parquet
   plus a landing manifest. Pagination files are not captured (not in inputs/).
2. Ticker run: `replace_company_tickers` on the captured company_tickers_exchange.json.
3. TEST Name Census: SEC side counted by the reader's own `census_filers` over this
   sample capture; NO GLEIF side (a full Golden Copy is not in inputs/), so every
   entry has zero LEIs. Labelled test-only.
4. TEST bronze receipts: `bronze_receipts` over the 10 files, with sandbox paths.
5. The reader: `edgar-warehouse mdm prepare-clean-company` via `cli.main`.
6. The mapping: the loop of `clean.cli.batch_input` without its database read
   (the contract comes from the rules file instead of `current_reading`).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.mdm.clean import store as clean_store
from edgar_warehouse.mdm.clean.activation import check_policy
from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.company_source import SOURCE_CODE, bronze_receipts, census_filers
from edgar_warehouse.mdm.clean.evidence import deferred_record, validate_assertion
from edgar_warehouse.mdm.clean.merge import check_company_sources
from edgar_warehouse.mdm.clean.name_census import VERSION as CENSUS_VERSION, sec_keys
from edgar_warehouse.mdm.clean.store import canonical
from edgar_warehouse.rules import files
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.serving.silver_landing_writer import write_landing_export
from edgar_warehouse.silver_landing_store import SilverLandingStore, _parse_company_ticker_rows

INPUTS = Path(sys.argv[1])
WORK = Path(sys.argv[2])
SAMPLE = ["0000320193", "0000937966", "0001306965", "0001806201", "0002032331",
          "0002153788", "0001818752", "0001964532", "0001781934", "0001825921"]
RUN = "dryrun-capture-20260927"
TICKER_RUN = "dryrun-tickers-20260927"
NOW = datetime(2026, 9, 27, tzinfo=UTC)

if WORK.exists():
    shutil.rmtree(WORK)
root = WORK / "landing"
root.mkdir(parents=True)
location = StorageLocation(str(root))


def flush(buffer, run_id, command):
    write_landing_export(buffer, location, run_id=run_id, business_date="2026-09-27",
                         command_name=command, environment_name="dryrun", now=NOW)
    for path in root.rglob("*.json"):
        body = json.loads(path.read_text())
        if body.get("run_id") == run_id and body.get("target") == "silver_landing":
            return path
    raise SystemExit(f"no manifest for {run_id}")


# 1. capture
capture = LandingExportBuffer()
silver = SilverLandingStore(landing_export=capture)
receipts_in = []
for cik in SAMPLE:
    file = INPUTS / "submissions" / f"CIK{cik}.json"
    raw = file.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    silver.stage_submission(cik=int(cik), main_payload=json.loads(raw), pagination_payloads=[],
                            sync_run_id=RUN, raw_object_id=sha, load_mode="bootstrap_full")
    receipts_in.append({"path": f"inputs/submissions/{file.name}", "sha256": sha})
company_manifest = flush(capture, RUN, "bootstrap-full")
print("capture tables:", {k: len(v) for k, v in capture.tables().items()})

# 2. ticker run
tickers = LandingExportBuffer()
catalog = json.loads((INPUTS / "tickers" / "company_tickers_exchange.json").read_bytes())
SilverLandingStore(landing_export=tickers).replace_company_tickers(
    _parse_company_ticker_rows(catalog), TICKER_RUN, source_name="company_tickers_exchange")
ticker_manifest = flush(tickers, TICKER_RUN, "drive-reference-catalog-discovery")

# 3. TEST census (SEC side only)
filers, population = census_filers(landing_root=str(root), landing_manifest=str(company_manifest))
held = sec_keys(filers)
census = {
    "version": CENSUS_VERSION,
    "normalizers": {"sec": "normalize_text@sec-legal-form-kept-v1", "gleif": "normalize_text@legal-form-kept-v1"},
    "sec": population,
    "gleif": {"archive_sha256": "TEST-NO-GLEIF", "content_date": None, "file_content": "TEST-NO-GLEIF", "record_count": 0},
    "entries": {k: {"ciks": sorted(v)[:5], "cik_count": len(v), "leis": [], "lei_count": 0,
                    "other_name_holders": 0} for k, v in sorted(held.items())},
}
census_path = WORK / "test-name-census.json"
census_path.write_text(canonical(census) + "\n")

# 4. TEST receipts
receipts_path = WORK / "test-bronze-receipts.json"
receipts_path.write_text(canonical(bronze_receipts(RUN, receipts_in)) + "\n")

# 5. the reader, through its command
from edgar_warehouse.cli import main  # noqa: E402

bundle = WORK / "bundle"
code = main(["mdm", "prepare-clean-company", "--landing-root", str(root),
             "--landing-manifest", str(company_manifest), "--ticker-manifest", str(ticker_manifest),
             "--name-census", str(census_path), "--output", str(bundle),
             "--as-of", "2026-09-27T00:00:00Z", "--revision", "0", "--limit", "10",
             "--bronze-receipts", str(receipts_path)])
print("prepare-clean-company exit:", code)

# 6. the mapping, as batch_input runs it
manifest = json.loads((bundle / "manifest.json").read_text())
contract = files.mdm_contract("sec.submissions.company", SOURCE_CODE)
assert json.loads((bundle / "dataset.json").read_text()) == contract, "bundle pinned another contract"
policy = files.policy()
check_policy(policy)
(batch,) = manifest["batches"]
spec = batch["input"]
raw = (bundle / spec["path"]).read_bytes()
assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
assertions, deferred, occurrences = [], [], []
for ordinal, line in enumerate(raw.splitlines(), 1):
    row = json.loads(line)
    publication = {**spec["publication"], "artifact_sha256": spec["sha256"], "member": spec["path"],
                   "record_locator": f"{spec['sha256']}:line:{ordinal}"}
    try:
        a = normalize(row, source_code=SOURCE_CODE, contract=contract, publication=publication,
                      mapping_version=1, policy=policy)
        validate_assertion(a)
        assertions.append(a)
        bronze = (row.get("_origin") or {}).get("bronze")
        if bronze:
            occurrences.append({"assertion_id": a["assertion_id"], **bronze})
    except UnsupportedRecord as exc:
        deferred.append(deferred_record(
            source_code=SOURCE_CODE, publication_key=publication["publication_key"],
            record_locator=publication["record_locator"], schema_version=contract["schema_version"],
            reason=exc.reason, raw_record=row, probable_kind=exc.probable_kind,
            provenance={"artifact_sha256": spec["sha256"], "member": spec["path"],
                        "adapter_version": contract["adapter"]["version"], **exc.detail}))
assert len(assertions) + len(deferred) == spec["record_count"]
check_company_sources(policy, assertions)
blocking = [d for d in deferred if d["reason"] not in contract.get("nonblocking_deferred_reasons", [])]


# The static checks register_dataset runs before it reads the registry.
class _Stop(Exception):
    pass


class _StubConnection:
    def execute(self, *a, **k):
        raise _Stop


try:
    clean_store.register_dataset(_StubConnection(), SOURCE_CODE, "00000000-0000-0000-0000-000000000000", contract)
except _Stop:
    print("register_dataset static checks: pass (stopped at the registry read)")

out = {
    "records": spec["record_count"],
    "publication_key": spec["publication"]["publication_key"],
    "assertions": [{k: a[k] for k in ("record_key", "kind", "fields", "identifiers", "provenance")}
                   for a in assertions],
    "deferred": [{"cik": d["raw_record"]["cik"], "name": d["raw_record"]["entity_name"], "reason": d["reason"],
                  "probable_kind": d.get("probable_kind"), "classification": d["provenance"].get("classification")}
                 for d in deferred],
    "blocking_deferred": len(blocking),
    "occurrences": occurrences,
}
(WORK / "dry-run-output.json").write_text(json.dumps(out, indent=1, sort_keys=True))
print(json.dumps(out, indent=1, sort_keys=True))
