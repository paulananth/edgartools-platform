"""Company preparation boundary; transformations execute authenticated Rules workers.

A bundle is a bounded set of SEC main submissions documents from one
receipt-bound raw capture. Each document is read by `census-main.yaml`, two a
unit; the Name Census (which must have counted this capture's population) is
read once, narrowed to the bundle's name keys; the exchange ticker catalog is
read once; and each unit is combined by `combine-census.yaml`. Every worker
runs with its verifier and is retained in the bundle, with the documents it
read, so the bundle verifies on its own. This creator binds the approved run
IDs and inputs; it collects no domain evidence in Python.
"""

from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files as rules_files
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers import source_read, source_combine, source_parquet
from edgar_warehouse.workers.source_staging import StagedArtifacts
from .evidence import instant
from .name_frequency import BRONZE, _read_bounded
from .store import Conflict, canonical, digest

SOURCE_CODE = "sec.submissions.company.v1"
CONTRACT = rules_files.mdm_contract("sec.submissions.company", SOURCE_CODE)
POLICY = rules_files.policy()
_json_value = source_parquet.json_scalar
ROOT = rules_files.ROOT / "sources/sec.submissions.company"
RECEIPTS_BYTES = 64 * 1024**2
DOCUMENTS_BYTES = 1024**2
CENSUS_BYTES = 256 * 1024**2
CATALOG_BYTES = 64 * 1024**2
ZERO = "0" * 64


def _bind(value, bindings):
    if isinstance(value, str):
        return bindings.get(value, value)
    if isinstance(value, list):
        return [_bind(item, bindings) for item in value]
    if isinstance(value, dict):
        return {key: _bind(item, bindings) for key, item in value.items()}
    return value


def _receipts(capture: Path) -> tuple[bytes, dict[str, str]]:
    raw = _read_bounded(capture / "receipts.jsonl", RECEIPTS_BYTES)
    return raw, {r["key"]: r["sha256"] for r in map(json.loads, raw.decode("utf-8").splitlines())}


def _document(capture: Path, receipts: dict, key: str) -> bytes:
    """A captured document's bytes, equal to its receipt."""
    if key not in receipts or not key.startswith(BRONZE):
        raise Conflict(f"The capture's receipts do not name {key}")
    data = (capture / "bronze" / key[len(BRONZE):]).read_bytes()
    if hashlib.sha256(data).hexdigest() != receipts[key]:
        raise Conflict(f"Captured document differs from its receipt: {key}")
    return data


def _configured_records(capture, receipts, keys, catalog_key, census, census_hash, pins, output):
    # The workers' inputs are private copies of bytes already checked against
    # their receipts; every contract, input and output is retained in the bundle.
    with tempfile.TemporaryDirectory(prefix=".company-workers-") as folder:
        root = Path(output).resolve() / "workers"
        staging = Path(folder)
        store = StagedArtifacts(root, staging)
        tasks = []

        def read(name, contract, inputs):
            """One `source.read` unit over (bytes, context values) inputs, executed then verified."""
            artifacts = []
            for index, (data, values) in enumerate(inputs):
                source = store.put_bytes((root / f"{name}-{index}.input").as_uri(), data)
                entry = {"input": source}
                if values is not None:
                    entry["context"] = store.put(root.as_uri(), {"version": 1, "input": source, "values": values})
                artifacts.append(entry)
            contract["execution"]["input_sha256s"] = [a["input"]["sha256"] for a in artifacts]
            version = 2 if all("context" in a for a in artifacts) else 1
            request = store.put(root.as_uri(), {"version": version, "contract": store.put(root.as_uri(), contract),
                                                "artifacts": artifacts if version == 2 else [a["input"] for a in artifacts]})
            task = {"input": request, "output": (root / f"{name}.reading.json").as_uri(), "checks": ["source.output"]}
            candidate = source_read.execute(task, store)
            if source_read.verify({**task, "candidate": candidate}, store) != ({"source.output": True}, []):
                raise ValueError("Configured reading verification failed")
            tasks.append({"profile": "source.read", "task": {**task, "candidate": candidate}})
            return candidate

        main_contract = rules_files.load(ROOT / "census-main.yaml")
        units = []
        for start in range(0, len(keys), main_contract["execution"]["max_artifacts"]):
            unit = keys[start:start + main_contract["execution"]["max_artifacts"]]
            inputs = [(_document(capture, receipts, key), {
                "cik": int(key.split("/cik=", 1)[1].split("/", 1)[0]), "sync_run_id": pins["capture_run"],
                "raw_object_id": receipts[key], "load_mode": pins["load_mode"], "recent_limit": None,
                "last_synced_at": pins["observed_at"]}) for key in unit]
            units.append((unit, read(f"main-{start}", deepcopy(main_contract), inputs)))
        rows = [row for _, ref in units for artifact in store.json(ref)["artifacts"]
                for row in artifact["tables"]["company"]]
        census_contract = _bind(rules_files.load(ROOT / "census.yaml"), {ZERO: census_hash})
        census_contract["execution"]["max_input_bytes"] = CENSUS_BYTES
        census_contract["read"]["limits"]["max_bytes"] = CENSUS_BYTES
        census_contract["read"]["tables"]["names"]["each"]["entries"]["keys"] = sorted({r["_name_key"] for r in rows})
        census_contract["read"]["tables"]["cascade"]["each"]["entries"]["keys"] = sorted(
            {f"{int(r['cik']):010d}" for r in rows})
        # The census is read as its canonical bytes, whose sha256 is the digest bound above.
        census_ref = read("census", census_contract, [(canonical(census).encode(), None)])
        catalog = read("catalog_exchange", rules_files.load(ROOT / "catalog.yaml"), [(
            _document(capture, receipts, catalog_key),
            {"sync_run_id": pins["catalog_run"], "last_synced_at": pins["observed_at"], "source_name": "catalog_exchange"})])
        combine = _bind(rules_files.load(ROOT / "combine-census.yaml"), {
            "APPROVED_COMPANY_CAPTURE_RUN": pins["capture_run"], "APPROVED_CATALOG_CAPTURE_RUN": pins["catalog_run"],
            ZERO: census_hash})
        # This capture holds main documents and one ticker catalog only (L4 finding:
        # continuation pages and the second catalog are not captured).
        combine["combine"]["groups"]["forms"]["source"] = ["main"]
        combine["combine"]["groups"]["tickers"]["source"] = ["catalog_exchange"]
        rule = store.put(root.as_uri(), combine)
        records = []
        for n, (unit, main) in enumerate(units):
            request = store.put(root.as_uri(), {"version": 1, "contract": rule, "readings": {
                "main": main, "catalog_exchange": catalog, "census": census_ref}})
            task = {"input": request, "output": (root / f"combined-{n}.reading.json").as_uri(),
                    "checks": ["source.combined"]}
            try:
                result = source_combine.execute(task, store)
            except ValueError as exc:
                if "row check failed: last_sync_run_id" in str(exc):
                    raise Conflict("Evidence row belongs to a different capture run or different catalog run") from exc
                raise
            if source_combine.verify({**task, "candidate": result}, store) != ({"source.combined": True}, []):
                raise ValueError("Configured combination verification failed")
            tasks.append({"profile": "source.combine", "task": {**task, "candidate": result}})
            combined = store.json(result)["artifacts"][0]["tables"]["company"]
            by_cik = {int(row["cik"]): row for row in combined}
            for key in unit:
                row = by_cik[int(key.split("/cik=", 1)[1].split("/", 1)[0])]
                # Where the record was delivered, beside what it says (ticket 10).
                records.append({**row, "_origin": {"bronze": {"object": key, "sha256": receipts[key], "locator": "$"}}})
        proof = {"version": 1, "workers": tasks, "frozen_census_digest": census_hash}
        store.put_bytes((root / "proof.json").as_uri(), (canonical(proof) + "\n").encode())
        retained = {"workers/" + str(path.relative_to(staging)): path.read_bytes()
                    for path in staging.rglob("*") if path.is_file()}
        return records, retained


def verify_company_bundle(output, *, expected):
    """Re-read published inputs and reproduce every configured worker output."""
    target = Path(output).resolve()
    if (target / "inventory.json").read_bytes() != (
        canonical(expected) + "\n"
    ).encode():
        raise Conflict("Prepared inventory differs from approved report")
    for name, pin in expected["files"].items():
        path = (target / name).resolve()
        if not path.is_relative_to(target):
            raise ValueError("Prepared member escapes the bundle")
        data = _read_bounded(path, pin["bytes"])
        if (
            len(data) != pin["bytes"]
            or hashlib.sha256(data).hexdigest() != pin["sha256"]
        ):
            raise Conflict("Prepared member differs from approved report: " + name)
    store = Artifacts()
    proof = json.loads((target / "workers/proof.json").read_bytes())
    if (
        set(proof) != {"version", "workers", "frozen_census_digest"}
        or proof["version"] != 1
    ):
        raise ValueError("Unsupported Company worker proof")
    profiles = {"source.read": source_read, "source.combine": source_combine}
    for entry in proof["workers"]:
        if set(entry) != {"profile", "task"} or entry["profile"] not in profiles:
            raise ValueError("Unsupported Company worker profile")
        profiles[entry["profile"]].verify(entry["task"], store)
    combined = store.json(proof["workers"][-1]["task"]["candidate"])
    records = combined["artifacts"][0]["tables"]["company"]
    expected = "".join(
        json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
        for row in records
    ).encode()
    if (target / "records.jsonl").read_bytes() != expected:
        raise Conflict("Prepared records differ from the verified workers")
    return {"source.output": True, "source.combined": True, "records": len(records)}




def prepare_company_bundle(
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
    """Pin a bounded Company sample from a raw capture, with the evidence its rules read.

    `documents` lists this bundle's main submissions documents by receipt key
    (at most 1,000); `population` is the population the Name Census counted,
    which must hold them. The Company rule reads the forms a filer files (its
    main document's recent filings) and its tickers (SEC's exchange catalog,
    `catalog` by receipt key); the SEC-to-GLEIF matching rules read the
    business address and the Name Census. The approved capture and catalog run
    IDs and the observation time are the caller's facts, bound into every row.
    """
    if type(revision) is not int or revision < 0:
        raise ValueError("Require a nonnegative explicit publication revision")
    instant(as_of)
    instant(observed_at)
    folder = Path(capture).resolve()
    receipts_raw, receipts = _receipts(folder)
    documents_raw = _read_bounded(Path(documents).resolve(), DOCUMENTS_BYTES)
    keys = json.loads(documents_raw)
    if not isinstance(keys, list) or not 1 <= len(keys) <= 1000 or len(set(keys)) != len(keys):
        raise ValueError("A bundle names 1..1000 distinct main documents")
    if any("/main/" not in key for key in keys):
        raise ValueError("A bundle names main submissions documents only")
    census_raw = _read_bounded(Path(name_census).resolve(), CENSUS_BYTES)
    census = json.loads(census_raw)
    population_raw = _read_bounded(Path(population).resolve(), 64 * 1024**2)
    sec = census.get("sec") or {}
    if (sec.get("receipts_sha256") != hashlib.sha256(receipts_raw).hexdigest()
            or sec.get("population_sha256") != hashlib.sha256(population_raw).hexdigest()
            or not set(keys) <= set(json.loads(population_raw))):
        raise Conflict("The Name Census did not count this capture's documents")
    census_hash = digest(census)
    pins = {"capture_run": capture_run, "catalog_run": catalog_run, "observed_at": observed_at,
            "load_mode": load_mode}
    records, worker_files = _configured_records(folder, receipts, keys, catalog, census, census_hash, pins, output)
    payload = ("\n".join(json.dumps(row, default=_json_value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False) for row in records) + "\n").encode()
    payload_hash = hashlib.sha256(payload).hexdigest()
    documents_hash = hashlib.sha256(documents_raw).hexdigest()
    publication_key = (f"{capture_run}:sec_submissions:{documents_hash}:{catalog_run}:{receipts[catalog]}"
                       f":name_census:{census_hash}")
    scope = {
        "mode": "bounded_sample",
        "selected_records": len(records),
        "whole_source_complete": False,
        "capture_run_id": capture_run,
        "ticker_run_id": catalog_run,
        "receipts_sha256": hashlib.sha256(receipts_raw).hexdigest(),
        "ciks": [r["cik"] for r in records],
        "bronze_named": len(records),
    }
    batch = digest([publication_key, revision, payload_hash, as_of])
    manifest = {
        "contract_version": 2,
        "as_of": as_of,
        "policy_digest": digest(POLICY),
        "scope": scope,
        "batches": [{
            "batch_id": "company:" + batch,
            "stage": "mastering",
            "consumer": f"{SOURCE_CODE}/{batch}",
            "expected_checkpoint": 0,
            "checkpoint": 1,
            "input": {"path": "records.jsonl", "sha256": payload_hash, "record_count": len(records),
                      "source_code": SOURCE_CODE,
                      "publication": {"publication_key": publication_key, "revision": revision, "effective_at": None}},
        }],
    }
    files = {
        "records.jsonl": payload,
        **worker_files,
        "documents.json": documents_raw,
        "population.json": population_raw,
        "name-census.json": census_raw,
        "dataset.json": (canonical(CONTRACT) + "\n").encode(),
        "policy.json": (canonical(POLICY) + "\n").encode(),
        "manifest.json": (canonical(manifest) + "\n").encode(),
    }
    inventory = {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)} for name, data in files.items()}
    report = {
        "contract_version": 2,
        "source_code": SOURCE_CODE,
        "scope": scope,
        "files": inventory,
        "governance": "Dataset coverage and policy registration required; no identity bindings included",
    }
    files["inventory.json"] = (canonical(report) + "\n").encode()
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not target.is_dir() or any(
            not (target / name).is_file() or (target / name).read_bytes() != data
            for name, data in files.items()
        ):
            raise Conflict("Existing pinned bundle has different content")
        return report
    stage = Path(tempfile.mkdtemp(prefix=".company-bundle-", dir=target.parent))
    try:
        for name, data in files.items():
            (stage / name).parent.mkdir(parents=True, exist_ok=True)
            with (stage / name).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        # A complete directory is exposed at once; an existing bundle is never overwritten.
        os.rename(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return report
