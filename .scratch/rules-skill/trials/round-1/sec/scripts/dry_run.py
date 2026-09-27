"""Step 7 dry run: put sample records through adapters.normalize.

Records are built by the repo's own code, not by hand:
  submissions JSON -> bronze_submission_extractors loaders (individuals
  skipped by is_individual_filer, as silver_landing_store does) -> a scratch
  silver landing (parquet + manifest, the shape `write_run` in the tests uses)
  -> company tickers via _parse_company_ticker_rows, stamped as
  replace_company_tickers does -> a Name Census counted against an EMPTY
  GLEIF golden copy (no GLEIF file is captured here) -> prepare_company_bundle
  (what `edgar-warehouse mdm prepare-clean-company` runs) -> normalize.

Stand-ins, stated so nobody mistakes them: last_synced_at is a fixed dry-run
time, not the real capture time; the run ids are invented; the Name Census
has no GLEIF side. No network. Run from repo/ with PYTHONDONTWRITEBYTECODE=1.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from edgar_warehouse.loaders.bronze_submission_extractors import (
    is_individual_filer,
    stage_address_loader,
    stage_company_loader,
    stage_former_name_loader,
    stage_recent_filing_loader,
)
from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.company_source import (
    prepare_company_bundle,
    write_name_census,
)
from edgar_warehouse.rules import files
from edgar_warehouse.silver_landing_store import _parse_company_ticker_rows

SB = Path(sys.argv[1])
INPUTS = SB / "inputs"
WORK = SB / "scratch" / "dry-run"
SOURCE, CODE = "sec.submissions.company", "sec.submissions.company.v1"
CAPTURE, CATALOG = "dry-run-capture", "dry-run-catalog"
SYNCED = datetime(2026, 9, 26, tzinfo=UTC)
SAMPLE = [  # CIK -> why it is in the sample
    ("0000320193", "Apple: operating, listed (step 8)"),
    ("0001306965", "Shell: 'other', foreign, EDGAR country X0 (step 10)"),
    ("0000937966", "ASML: 'other', foreign, EDGAR code P7 in stateOrCountry"),
    ("0001806201", "Open Lending: operating, LPRO in submissions but not in the catalog"),
    ("0002032331", "Arrowpoint (Singapore) 13F adviser: states an LEI"),
    ("0002015731", "Lord Abbett ... Trust: fund-like name, Form D"),
    ("0002134860", "SCA Murrells Inlet, LLC: Form D only"),
    ("0001109147", "Axiom Investors LLC: 13F filer"),
    ("0001825921", "ICONIQ ... GP, Ltd.: files Forms 3/4 as an entity"),
    ("0000938419", "KLEMP WALTER V: individual control"),
]


def stamp(rows, run_id):
    return [{**r, "last_sync_run_id": run_id, "last_synced_at": SYNCED} for r in rows]


def write_run(root: Path, run_id: str, tables: dict) -> Path:
    for name, rows in tables.items():
        pq.write_table(pa.Table.from_pylist(rows), root / f"{name}.parquet")
    manifest = root / f"{run_id}.json"
    manifest.write_text(json.dumps({
        "schema_version": 1, "target": "silver_landing", "run_id": run_id,
        "tables": [
            {"table_name": n, "relative_path": f"{n}.parquet", "file_count": 1,
             "row_count": len(r)}
            for n, r in tables.items()
        ],
    }))
    return manifest


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    landing = WORK / "landing"
    landing.mkdir(parents=True)
    company, address, former, filing, skipped = [], [], [], [], []
    wanted = {c for c, _ in SAMPLE}
    for path in sorted((INPUTS / "submissions").glob("CIK*.json")):
        cik_text = path.stem.removeprefix("CIK")
        if cik_text not in wanted:
            continue
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        payload = json.loads(raw)
        cik = int(payload["cik"])
        filing += stage_recent_filing_loader(payload, cik, CAPTURE, sha, "dry-run")
        if is_individual_filer(payload):
            skipped.append(cik_text)  # production writes no Company row for it
            continue
        company += stage_company_loader(payload, cik, CAPTURE, sha, "dry-run")
        address += stage_address_loader(payload, cik, CAPTURE, sha, "dry-run")
        former += stage_former_name_loader(payload, cik, CAPTURE, sha, "dry-run")
    manifest = write_run(landing, CAPTURE, {
        "sec_company": stamp(company, CAPTURE),
        "sec_company_filing": stamp(filing, CAPTURE),
        "sec_company_address": stamp(address, CAPTURE),
        "sec_company_former_name": stamp(former, CAPTURE),
    })
    # One catalog only: replace_company_tickers' default source_name.
    doc = json.loads((INPUTS / "tickers" / "company_tickers_exchange.json").read_text())
    tickers = [
        {**r, "source_name": "company_tickers_exchange", "source_rank": i}
        for i, r in enumerate(_parse_company_ticker_rows(doc), 1)
        if r.get("cik") is not None and r.get("ticker")
    ]
    ticker_manifest = write_run(landing, CATALOG, {"sec_company_ticker": stamp(tickers, CATALOG)})

    # An empty GLEIF golden copy: the census counts SEC names only.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("golden.json", json.dumps({"records": []}))
    archive = WORK / "gleif-empty.json.zip"
    archive.write_bytes(buf.getvalue())
    meta = WORK / "gleif-empty.metadata.json"
    meta.write_text(json.dumps({
        "format": "json.zip", "cdf_version": "LEI_3.1",
        "content_date": "2026-09-11T16:00:00+00:00",
        "file_content": "GLEIF_FULL_PUBLISHED", "delta_start": None, "record_count": 0,
    }))
    census = WORK / "name-census.json"
    write_name_census(
        landing_root=str(landing), landing_manifest=str(manifest),
        gleif_archive=str(archive), gleif_metadata=str(meta),
        gleif_sha256=hashlib.sha256(buf.getvalue()).hexdigest(), output=str(census),
    )
    bundle = WORK / "bundle"
    report = prepare_company_bundle(
        landing_root=str(landing), landing_manifest=str(manifest),
        ticker_manifest=str(ticker_manifest), name_census=str(census),
        output=str(bundle), limit=len(company), as_of="2026-09-26T00:00:00+00:00",
        revision=0,
    )
    records = [json.loads(line) for line in (bundle / "records.jsonl").read_text().splitlines()]
    contract = files.mdm_contract(SOURCE, CODE)
    policy = files.policy()

    # The publication exactly as the skill's step 7 writes it.
    skill_publication = {"member": "sample", "publication_key": "dry-run", "revision": 0}
    try:
        normalize(records[0], source_code=CODE, contract=contract,
                  publication=skill_publication, policy=policy)
        print("skill's publication dict: accepted")
    except Exception as error:  # noqa: BLE001 - reporting what happens
        print(f"skill's publication dict: {type(error).__name__}: {error}")
    publication = {**skill_publication, "artifact_sha256": report["files"]["records.jsonl"]["sha256"],
                   "effective_at": None}

    print(f"\nindividuals skipped before a Company row exists (is_individual_filer): {skipped}")
    print(f"bundle: {report['scope']}\n")
    why = dict(SAMPLE)
    results = []
    for row in records:
        cik = f"{int(row['cik']):010d}"
        try:
            body = normalize(row, source_code=CODE, contract=contract,
                             publication=publication, policy=policy)
            out = {
                "cik": cik, "why": why[cik], "outcome": "assertion",
                "kind": body["kind"],
                "classification": body["provenance"].get("classification"),
                "record_key": body["record_key"], "identifiers": body["identifiers"],
                "fields": {k: v.get("value", "<unknown>") for k, v in body["fields"].items()},
                "matching": {k: v for k, v in body["provenance"].get("matching", {}).items()
                             if k != "name_census"},
                "name_census": {k: body["provenance"]["matching"]["name_census"].get(k)
                                for k in ("key", "ciks", "leis")},
                "observed_at": body["provenance"]["source"]["observed_at"],
                "adapter_version": body["provenance"]["adapter_version"],
                "assertion_id": body["assertion_id"][:16] + "...",
                "rule_inputs": {"entity_type": row["entity_type"], "sic": row["sic"],
                                "category": row["category"], "tickers": row["tickers"],
                                "forms": len(row["forms"])},
            }
        except UnsupportedRecord as held:
            out = {
                "cik": cik, "why": why[cik], "outcome": "deferred",
                "reason": held.reason, "detail": held.detail,
                "probable_kind": held.probable_kind,
                "rule_inputs": {"entity_type": row["entity_type"], "sic": row["sic"],
                                "category": row["category"], "tickers": row["tickers"],
                                "forms": sorted(row["forms"])[:8]},
            }
        results.append(out)
        print(json.dumps(out, indent=1, default=str))
    (WORK / "dry-run.json").write_text(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
