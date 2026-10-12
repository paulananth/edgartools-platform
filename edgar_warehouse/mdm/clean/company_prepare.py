"""Company preparation: the input manifest of the Company `mastering` target.

A bundle is up to 512 SEC main submissions documents from one receipt-bound
raw capture. This writer checks the caller's inputs (the documents are main
documents the capture's receipts name, in the population the Name Census
counted), binds the approved run IDs and the census digest into the
contracts, and freezes every unit's input. Bookkeeping runs the target's steps
(`rules run --source sec.submissions.company --target mastering`) and the
registered workers do the work:

- `main` and `keys`: each document read by `census-main.yaml` and
  `census-keys.yaml`, two a unit;
- `catalog`: the exchange ticker catalog read once (`catalog.yaml`);
- `census`: the Name Census read once, narrowed to the bundle's names and CIKs
  by lookup sets derived from the key readings (`census.yaml`);
- `combine`: each main unit with the census and the catalog
  (`combine-census-captured.yaml`);
- `records`: the bundle's combined rows as one publication (`mdm.prepare`);
- `merge`: that manifest through the Merge Stage (`mdm.merge`).

The census and combine inputs are composed: Bookkeeping fills them with the
verified readings they name. Python collects no domain evidence and edits no
rules settings; it only binds the caller's approved facts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files as rules_files
from .evidence import instant
from . import raw_capture
from .raw_capture import read_bounded
from .sec_company import CONTRACT, POLICY, SOURCE_CODE
from .store import Conflict, canonical, digest

ROOT = rules_files.ROOT / "sources/sec.submissions.company"
TARGET = "mastering"
DOCUMENTS_BYTES = 1024**2
CENSUS_BYTES = 256 * 1024**2
POPULATION_BYTES = 64 * 1024**2
KEY_READING_BYTES = 16 * 1024**2  # every census-keys reading of one bundle
# A census read derives its lookup sets from at most 256 key readings of 2 documents.
BUNDLE_DOCUMENTS = 512
# The contracts the target's readings and combination run.
RULES = ("census-main.yaml", "census-keys.yaml", "catalog.yaml", "census.yaml", "combine-census-captured.yaml")
# Where `census.yaml` and the combination take the census digest.
CENSUS_DIGEST = "0" * 64


def _bind(value, bindings):
    if isinstance(value, str):
        return bindings.get(value, value)
    if isinstance(value, list):
        return [_bind(item, bindings) for item in value]
    if isinstance(value, dict):
        return {key: _bind(item, bindings) for key, item in value.items()}
    return value


def _unit(output: str, keys: dict, source: dict) -> dict:
    return {"keys": {**keys, "destination": output}, "input": source, "output": output, "cursor": {}}


def _units(store, root: str, folder: Path, receipts: dict, keys: list[str], catalog: str, census: bytes,
           census_hash: str, pins: dict, publication: dict) -> dict:
    """Every step's units, inputs frozen: contracts bound, documents by receipt, inputs composed."""
    inputs = root + "/inputs"
    put = lambda value: store.put(inputs, value)  # noqa: E731
    main_rules = rules_files.load(ROOT / "census-main.yaml")
    main_contract = put(main_rules)
    keys_contract = put(rules_files.load(ROOT / "census-keys.yaml"))
    per_unit = main_rules["execution"]["max_artifacts"]
    main, readers = [], []
    for start in range(0, len(keys), per_unit):
        name = f"main-{start}"
        documents = [raw_capture.document(folder, receipts, key) for key in keys[start:start + per_unit]]
        for key in keys[start:start + per_unit]:
            raw_capture.document_bytes(folder, receipts, key)  # equal to its receipt before it is frozen
        contexts = [put({"version": 1, "input": ref, "values": {
            "cik": raw_capture.cik(key), "sync_run_id": pins["capture_run"], "raw_object_id": receipts[key],
            "load_mode": pins["load_mode"], "recent_limit": None, "last_synced_at": pins["observed_at"],
            "bronze_object": key}}) for key, ref in zip(keys[start:start + per_unit], documents)]
        main.append(_unit(f"{root}/main/{start}.reading.json", {"unit": name}, put({
            "version": 2, "contract": main_contract,
            "artifacts": [{"input": ref, "context": c} for ref, c in zip(documents, contexts)]})))
        readers.append(_unit(f"{root}/keys/{start}.reading.json", {"unit": f"keys-{start}"}, put({
            "version": 1, "contract": keys_contract, "artifacts": documents})))
    catalog_ref = raw_capture.document(folder, receipts, catalog)
    raw_capture.document_bytes(folder, receipts, catalog)
    catalog_unit = _unit(f"{root}/catalog.reading.json", {"unit": "catalog"}, put({
        "version": 2, "contract": put(rules_files.load(ROOT / "catalog.yaml")),
        "artifacts": [{"input": catalog_ref, "context": put({"version": 1, "input": catalog_ref, "values": {
            "sync_run_id": pins["catalog_run"], "last_synced_at": pins["observed_at"],
            "source_name": "catalog_exchange"}})}]}))
    # The census is read as its canonical bytes, whose sha256 is the digest bound into the contracts.
    census_ref = store.put_bytes(f"{inputs}/name-census.json", census)
    readings = [{"step": "keys", "key": unit["keys"]["unit"]} for unit in readers]
    sets = {name: {"readings": {"slot": "keys"}, "table": "keys", "column": column,
                   "max_input_bytes": KEY_READING_BYTES, "max_input_rows": len(keys)}
            for name, column in (("names", "_name_key"), ("ciks", "_cik_key"))}
    census_unit = _unit(f"{root}/census.reading.json", {"unit": "census"}, {"compose": {
        "document": {"version": 3, "contract": put(_bind(rules_files.load(ROOT / "census.yaml"),
                                                         {CENSUS_DIGEST: census_hash})),
                     "artifacts": [{"input": census_ref,
                                    "context": put({"version": 1, "input": census_ref, "values": {}}),
                                    "lookups": {"slot": "lookups"}}]},
        "slots": {"lookups": {"compose": {"document": {"version": 2, "input": census_ref, "sets": sets},
                                          "slots": {"keys": readings}}}}}})
    combine_contract = put(_bind(rules_files.load(ROOT / "combine-census-captured.yaml"), {
        "APPROVED_COMPANY_CAPTURE_RUN": pins["capture_run"], "APPROVED_CATALOG_CAPTURE_RUN": pins["catalog_run"],
        CENSUS_DIGEST: census_hash}))
    combine = [_unit(f"{root}/combine/{n}.reading.json", {"unit": f"combine-{n}"}, {"compose": {
        "document": {"version": 1, "contract": combine_contract,
                     "readings": {"main": {"slot": "main"}, "census": {"slot": "census"},
                                  "catalog_exchange": {"slot": "catalog"}}},
        "slots": {"main": {"step": "main", "key": unit["keys"]["unit"]},
                  "census": {"step": "census", "key": "census"}, "catalog": {"step": "catalog", "key": "catalog"}}}})
               for n, unit in enumerate(main)]
    records = _unit(f"{root}/records/manifest.json", {
        "unit": "records", "table": "company", "dataset": SOURCE_CODE, "policy": digest(POLICY),
        "consumer": publication["consumer"], "batch_id": publication["batch_id"], "as_of": publication["as_of"],
        "publication_key": publication["publication_key"], "revision": str(publication["revision"])}, {"compose": {
            "document": {"version": 1, "readings": {"slot": "combined"}},
            "slots": {"combined": [{"step": "combine", "key": unit["keys"]["unit"]} for unit in combine]}}})
    merge = {"keys": {"batch_id": publication["batch_id"], "consumer": publication["consumer"]},
             "input": {"from": {"step": "records", "key": "records"}}, "output": f"{root}/merge.json", "cursor": {}}
    return {"main": main, "keys": readers, "catalog": [catalog_unit], "census": [census_unit],
            "combine": combine, "records": [records], "merge": [merge]}


def write_company_manifest(
    *,
    capture: str,
    documents: str,
    population: str,
    catalog: str,
    capture_run: str,
    catalog_run: str,
    observed_at: str,
    name_census: str,
    output: str,
    as_of: str,
    revision: int,
    load_mode: str = "default",
) -> dict:
    """The `mastering` target's input manifest for a bounded Company sample from a raw capture.

    `documents` lists this bundle's main submissions documents by receipt key
    (at most 512); `population` is the population the Name Census counted,
    which must hold them. The Company rule reads the forms a filer files (its
    main document's recent filings) and its tickers (SEC's exchange catalog,
    `catalog` by receipt key); the SEC-to-GLEIF matching rules read the
    business address and the Name Census. The approved capture and catalog run
    IDs and the observation time are the caller's facts, bound into every row.
    Returns the report: the manifest's reference and the publication's scope.
    """
    if type(revision) is not int or revision < 0:
        raise ValueError("Require a nonnegative explicit publication revision")
    instant(as_of)
    instant(observed_at)
    folder = Path(capture).resolve()
    receipts_raw, receipts = raw_capture.receipts(folder)
    documents_raw = read_bounded(Path(documents).resolve(), DOCUMENTS_BYTES)
    keys = json.loads(documents_raw)
    if (not isinstance(keys, list) or not 1 <= len(keys) <= BUNDLE_DOCUMENTS
            or len(set(keys)) != len(keys)):
        raise ValueError(f"A bundle names 1..{BUNDLE_DOCUMENTS} distinct main documents")
    if any("/main/" not in key for key in keys):
        raise ValueError("A bundle names main submissions documents only")
    census_raw = read_bounded(Path(name_census).resolve(), CENSUS_BYTES)
    census = json.loads(census_raw)
    population_raw = read_bounded(Path(population).resolve(), POPULATION_BYTES)
    sec = census.get("sec") or {}
    if (sec.get("receipts_sha256") != hashlib.sha256(receipts_raw).hexdigest()
            or sec.get("population_sha256") != hashlib.sha256(population_raw).hexdigest()
            or not set(keys) <= set(json.loads(population_raw))):
        raise Conflict("The Name Census did not count this capture's documents")
    canonical_census = canonical(census).encode()
    census_hash = hashlib.sha256(canonical_census).hexdigest()  # the census's digest
    documents_hash = hashlib.sha256(documents_raw).hexdigest()
    publication_key = (f"{capture_run}:sec_submissions:{documents_hash}:{catalog_run}:{receipts[catalog]}"
                       f":name_census:{census_hash}")
    # The consumer and batch ids name everything that shapes the rows: a rerun with another
    # observation time, load mode or rules version is a new consumer, not a reused batch key.
    rules = [rules_files.load(ROOT / name) for name in RULES]
    bundle = digest([publication_key, revision, as_of, observed_at, load_mode, rules])
    publication = {"publication_key": publication_key, "revision": revision, "as_of": as_of,
                   "consumer": f"{SOURCE_CODE}/{bundle}", "batch_id": f"company:{bundle}"}
    pins = {"capture_run": capture_run, "catalog_run": catalog_run, "observed_at": observed_at,
            "load_mode": load_mode}
    store = Artifacts()
    root = Path(output).resolve().as_uri()
    steps = _units(store, root, folder, receipts, keys, catalog, canonical_census, census_hash, pins, publication)
    manifest = store.put(root, {"version": 2, "steps": steps})
    scope = {
        "mode": "bounded_sample",
        "selected_records": len(keys),
        "whole_source_complete": False,
        "capture_run_id": capture_run,
        "ticker_run_id": catalog_run,
        "receipts_sha256": hashlib.sha256(receipts_raw).hexdigest(),
        "ciks": [raw_capture.cik(key) for key in keys],
        "bronze_named": len(keys),
    }
    return {
        "contract_version": 3,
        "source_code": SOURCE_CODE,
        "target": TARGET,
        "manifest": manifest,
        "publication": publication,
        "dataset_digest": digest(CONTRACT),
        "policy_digest": digest(POLICY),
        "scope": scope,
        "governance": "Dataset coverage and policy registration required; no identity bindings included",
    }
