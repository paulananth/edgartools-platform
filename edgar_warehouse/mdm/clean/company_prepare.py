"""Company preparation boundary; transformations execute authenticated Rules workers.

The existing authenticated census is frozen input. This creator binds physical
members and approved run IDs; it does not collect domain evidence in Python.
"""

from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
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
from .company_source import (
    SOURCE_CODE,
    CONTRACT,
    POLICY,
    _read_bounded,
    _read_manifest,
    _read_member,
    _read_receipts,
)
from .evidence import instant
from .store import Conflict, canonical, digest

_json_value = source_parquet.json_scalar
ROOT = rules_files.ROOT / "sources/sec.submissions.company"


@dataclass(frozen=True)
class _Member:
    field: str
    table: str
    file: str
    raw: bytes
    origin: dict
    columns: tuple[str, ...]


def _pin_member(root, landing, manifest_bytes, *, table, required, field, file):
    member, raw, parquet = _read_member(root, landing, table, required)
    return _Member(
        field,
        table,
        file,
        raw,
        {
            "member": member["relative_path"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "run_id": landing["run_id"],
        },
        tuple(parquet.schema_arrow.names),
    )


def _bind(value, bindings):
    if isinstance(value, str):
        return bindings.get(value, value)
    if isinstance(value, list):
        return [_bind(item, bindings) for item in value]
    if isinstance(value, dict):
        return {key: _bind(item, bindings) for key, item in value.items()}
    return value


def _configured_records(
    raw,
    parquet,
    pinned,
    census,
    census_hash,
    limit,
    landing,
    member,
    manifest_bytes,
    bronze,
    output,
):
    # Worker's physical inputs are private snapshots of bytes already validated
    # against manifests. All contracts/inputs/outputs are retained in the bundle.
    with tempfile.TemporaryDirectory(prefix=".company-workers-") as folder:
        root = Path(output).resolve() / "workers"
        staging = Path(folder)
        store = StagedArtifacts(root, staging)
        refs, tasks = {}, []

        def read(name, data, contract):
            source = store.put_bytes((root / (name + ".input")).as_uri(), data)
            contract["execution"]["input_sha256s"] = [source["sha256"]]
            rule = store.put(root.as_uri(), contract)
            request = store.put(
                root.as_uri(), {"version": 1, "contract": rule, "artifacts": [source]}
            )
            task = {
                "input": request,
                "output": (root / (name + ".reading.json")).as_uri(),
                "checks": ["source.output"],
            }
            try:
                candidate = source_read.execute(task, store)
                if source_read.verify({**task, "candidate": candidate}, store) != (
                    {"source.output": True},
                    [],
                ):
                    raise ValueError("Configured reading verification failed")
            except SourceRejected as exc:
                if exc.code == "assertion_failed" and "different" in str(exc):
                    raise Conflict(str(exc)) from exc
                raise
            refs[name] = candidate
            tasks.append(
                {"profile": "source.read", "task": {**task, "candidate": candidate}}
            )

        base = rules_files.load(ROOT / "landed-preparation.yaml")
        bindings = {
            "APPROVED_COMPANY_CAPTURE_RUN": landing["run_id"],
            "APPROVED_CATALOG_CAPTURE_RUN": pinned[-1].origin["run_id"],
        }
        main = _bind(deepcopy(base["company"]), bindings)
        table = main["read"]["tables"]["company"]
        reserved = {"_origin", "_name_key", "_join_cik"}
        if reserved.intersection(parquet.schema_arrow.names):
            raise ValueError("Company source contains reserved preparation columns")
        table["columns"].update(
            {name: {"value": {"path": name}} for name in parquet.schema_arrow.names}
        )
        table["take"] = {"const": {"value": limit}}
        main["read"]["parquet"] = {"take": limit}
        origin = {
            "member": member["relative_path"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            **{e.field: e.origin for e in pinned},
            "name_census_sha256": census_hash,
        }
        table["columns"]["_origin"]["object"]["fields"].update(
            {key: _literal(value) for key, value in origin.items()}
        )
        main["read"]["references"]["bronze"] = {
            sha: {"object": uri} for sha, uri in bronze.items()
        }
        read("main", raw, main)
        for e in pinned:
            contract = _bind(deepcopy(base[e.field]), bindings)
            if e.field == "business_address" and "country_code" in e.columns:
                contract["read"]["parquet"]["columns"].append("country_code")
            read(e.field, e.raw, contract)
        main_rows = store.json(refs["main"])["artifacts"][0]["tables"]["company"]
        census_contract = _bind(
            rules_files.load(ROOT / "census.yaml"), {"0" * 64: census_hash}
        )
        census_contract["execution"]["max_input_bytes"] = 256 * 1024**2
        census_contract["read"]["limits"]["max_bytes"] = 256 * 1024**2
        census_contract["read"]["tables"]["names"]["each"]["entries"]["keys"] = sorted(
            {row["_name_key"] for row in main_rows}
        )
        census_contract["read"]["tables"]["cascade"]["each"]["entries"]["keys"] = (
            sorted({f"{row['_join_cik']:010d}" for row in main_rows})
        )
        read("census", canonical(census).encode(), census_contract)
        combine = _bind(
            rules_files.load(ROOT / "combine-landed.yaml"),
            {**bindings, "0" * 64: census_hash},
        )
        rule = store.put(root.as_uri(), combine)
        request = store.put(
            root.as_uri(), {"version": 1, "contract": rule, "readings": refs}
        )
        task = {
            "input": request,
            "output": (root / "combined.reading.json").as_uri(),
            "checks": ["source.combined"],
        }
        try:
            result = source_combine.execute(task, store)
        except ValueError as exc:
            if "row check failed: last_sync_run_id" in str(exc):
                raise Conflict(
                    "Evidence row belongs to a different capture run or different catalog run"
                ) from exc
            raise
        if source_combine.verify({**task, "candidate": result}, store) != (
            {"source.combined": True},
            [],
        ):
            raise ValueError("Configured combination verification failed")
        records = store.json(result)["artifacts"][0]["tables"]["company"]
        tasks.append(
            {"profile": "source.combine", "task": {**task, "candidate": result}}
        )
        proof = {"version": 1, "workers": tasks, "frozen_census_digest": census_hash}
        store.put_bytes(
            (root / "proof.json").as_uri(), (canonical(proof) + "\n").encode()
        )
        retained = {
            "workers/" + str(path.relative_to(staging)): path.read_bytes()
            for path in staging.rglob("*")
            if path.is_file()
        }
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


def _literal(value):
    # Native const is scalar. Objects must declare their fields explicitly.
    if isinstance(value, dict):
        return {
            "object": {"fields": {key: _literal(item) for key, item in value.items()}}
        }
    return {"const": {"value": value}}


def prepare_company_bundle(
    *,
    landing_root: str,
    landing_manifest: str,
    ticker_manifest: str,
    name_census: str,
    output: str,
    limit: int,
    as_of: str,
    revision: int,
    bronze_receipts_path: str | None = None,
) -> dict:
    """Pin a bounded Company sample with the evidence its rules read.

    The Company rule reads two things the Company row does not carry
    (ticket 12): the forms a filer files, landed by the same capture
    (`sec_company_filing`), and its tickers, which SEC publishes in a catalog
    of its own landed by a separate run (`sec_company_ticker`). The
    SEC-to-GLEIF matching rules (ticket 08) read the business address
    (`sec_company_address`) and the Name Census, which must have counted this
    same capture. Each is pinned beside the Company member, and its digest is
    part of the key.
    """
    if not 1 <= limit <= 1000 or type(revision) is not int or revision < 0:
        raise ValueError(
            "Require --limit 1..1000 and a nonnegative explicit publication revision"
        )
    instant(as_of)
    root = Path(landing_root).resolve()
    landing, manifest_bytes = _read_manifest(root, landing_manifest)
    member, raw, parquet = _read_member(
        root,
        landing,
        "sec_company",
        {
            "cik",
            "entity_name",
            "entity_type",
            "raw_object_id",
            "last_sync_run_id",
            "last_synced_at",
        },
    )
    raw_hash = hashlib.sha256(raw).hexdigest()
    census_raw = _read_bounded(Path(name_census).resolve(), 256 * 1024 * 1024)
    census = json.loads(census_raw)
    sec = census.get("sec") or {}
    if not any(
        capture.get("capture_run_id") == landing["run_id"]
        and capture.get("company_member_sha256") == raw_hash
        for capture in sec.get("captures", [sec])
    ):
        raise Conflict("The Name Census did not count this Company capture")
    census_hash = digest(census)
    catalog, catalog_manifest_bytes = _read_manifest(root, ticker_manifest)
    receipts_raw, bronze = (
        _read_receipts(bronze_receipts_path, landing["run_id"])
        if bronze_receipts_path is not None
        else (None, {})
    )
    pinned = (
        _pin_member(
            root,
            landing,
            manifest_bytes,
            table="sec_company_filing",
            required={"cik", "form", "last_sync_run_id"},
            field="forms",
            file="filings.parquet",
        ),
        _pin_member(
            root,
            landing,
            manifest_bytes,
            table="sec_company_address",
            required={
                "cik",
                "address_type",
                "street1",
                "street2",
                "city",
                "zip_code",
                "state_or_country",
                "last_sync_run_id",
            },
            field="business_address",
            file="addresses.parquet",
        ),
        _pin_member(
            root,
            catalog,
            catalog_manifest_bytes,
            table="sec_company_ticker",
            required={"cik", "ticker", "source_rank", "last_sync_run_id"},
            field="tickers",
            file="tickers.parquet",
        ),
    )
    records, worker_files = _configured_records(
        raw,
        parquet,
        pinned,
        census,
        census_hash,
        limit,
        landing,
        member,
        manifest_bytes,
        bronze,
        output,
    )
    if not records:
        raise ValueError("The Company publication contains no records")
    payload = (
        "\n".join(
            json.dumps(
                row,
                default=_json_value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            for row in records
        )
        + "\n"
    ).encode()
    payload_hash = hashlib.sha256(payload).hexdigest()
    publication_key = (
        f"{landing['run_id']}:sec_company:{raw_hash}"
        + "".join(
            f":{e.origin['run_id']}:{e.table}:{e.origin['sha256']}" for e in pinned
        )
        + f":name_census:{census_hash}"
    )
    scope = {
        "mode": "bounded_sample",
        "selected_records": len(records),
        "available_company_records": parquet.metadata.num_rows,
        "whole_source_complete": False,
        "capture_run_id": landing["run_id"],
        "ticker_run_id": catalog["run_id"],
        "ciks": [r["cik"] for r in records],
        # How many records name the bronze object they were read from; stated
        # only with receipts, so a bundle prepared without them is unchanged.
        **(
            {"bronze_named": sum("bronze" in r["_origin"] for r in records)}
            if bronze_receipts_path is not None
            else {}
        ),
    }
    manifest = {
        "contract_version": 2,
        "as_of": as_of,
        "policy_digest": digest(POLICY),
        "scope": scope,
        "batches": [
            {
                "batch_id": "company:"
                + digest([publication_key, revision, payload_hash, as_of]),
                "stage": "mastering",
                "consumer": f"{SOURCE_CODE}/{digest([publication_key, revision, payload_hash, as_of])}",
                "expected_checkpoint": 0,
                "checkpoint": 1,
                "input": {
                    "path": "records.jsonl",
                    "sha256": payload_hash,
                    "record_count": len(records),
                    "source_code": SOURCE_CODE,
                    "publication": {
                        "publication_key": publication_key,
                        "revision": revision,
                        "effective_at": None,
                    },
                },
            }
        ],
    }
    files = {
        "records.jsonl": payload,
        **worker_files,
        "source.parquet": raw,
        "landing-manifest.json": manifest_bytes,
        **{e.file: e.raw for e in pinned},
        "ticker-manifest.json": catalog_manifest_bytes,
        "name-census.json": census_raw,
        **({"bronze-receipts.json": receipts_raw} if receipts_raw is not None else {}),
        "dataset.json": (canonical(CONTRACT) + "\n").encode(),
        "policy.json": (canonical(POLICY) + "\n").encode(),
        "manifest.json": (canonical(manifest) + "\n").encode(),
    }
    inventory = {
        name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        for name, data in files.items()
    }
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
