"""Bounded SEC Company landing adapter and immutable local input preparation.

Preparation neither activates source coverage nor allocates/binds identities.
The generated contract and policy are reviewable governance inputs.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pyarrow.parquet as pq

from edgar_warehouse.rules import files as rules_files

from .evidence import instant
from .matching import FAMILY, active_rules
from .name_census import entry as census_entry
from .names import edgar_jurisdiction
from .store import Conflict, canonical, digest

SOURCE_CODE = "sec.submissions.company.v1"
# The mapping and the merge rules are data in `rules/`, edited and reviewed as
# files (rules skill ticket 01): the Dataset Contract in
# `rules/sources/sec.submissions.company/source.yaml`, the Mastering Policy in
# `rules/merge/`. The names below stay importable.
CONTRACT = rules_files.mdm_contract("sec.submissions.company", SOURCE_CODE)
FIELDS = CONTRACT["adapter"]["fields"]
POLICY = rules_files.policy()
APPROVED_ACTIVATION = next(
    rule for rule in POLICY["automatic_rules"] if rule["rule_id"] == "sec-company-candidate"
)
PROOF = APPROVED_ACTIVATION["proof"]


def _read_bounded(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError(
            "Source file exceeds preparation budget; partition its publication"
        )
    return raw


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported source scalar: {type(value).__name__}")


def _read_manifest(root: Path, manifest: str) -> tuple[dict, bytes]:
    path = Path(manifest).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Landing manifest must be inside its root")
    raw = _read_bounded(path, 1024 * 1024)
    landing = json.loads(raw)
    if (
        landing.get("schema_version") != 1
        or landing.get("target") != "silver_landing"
        or not landing.get("run_id")
    ):
        raise ValueError("Unsupported landing manifest contract")
    return landing, raw


def _read_member(
    root: Path, landing: dict, table_name: str, required: set[str]
) -> tuple[dict, bytes, pq.ParquetFile]:
    """The one pinned file a landing run wrote for `table_name`, checked."""
    members = [t for t in landing["tables"] if t["table_name"] == table_name]
    if len(members) != 1 or members[0].get("file_count") != 1:
        raise ValueError(
            f"Require one explicit {table_name} member; multi-file landing needs "
            "a partition contract"
        )
    member = members[0]
    path = (root / member["relative_path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Landing member escapes its root")
    raw = _read_bounded(path, 64 * 1024 * 1024)
    parquet = pq.ParquetFile(io.BytesIO(raw))
    if parquet.metadata.num_rows != member["row_count"]:
        raise Conflict("Landing member row count disagrees with its manifest")
    if not required <= set(parquet.schema_arrow.names):
        raise ValueError(
            f"{table_name} landing schema is missing required evidence columns"
        )
    return member, raw, parquet


def _catalog_tickers(landing: dict, parquet: pq.ParquetFile) -> dict[int, list[str]]:
    """Each CIK's tickers in SEC's catalog, in the catalog's rank order.

    The catalog lists listed securities only, so a CIK it omits has none.
    """
    listed: dict[int, list[tuple]] = {}
    for batch in parquet.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Ticker row belongs to a different catalog run")
            if row["cik"] is None or not row["ticker"]:
                continue
            listed.setdefault(int(row["cik"]), []).append(
                (row["source_rank"], row["ticker"])
            )
    # One catalog run lands both SEC ticker lists: each ticker once (ticket 18).
    return {
        cik: list(dict.fromkeys(t for _, t in sorted(pairs)))
        for cik, pairs in listed.items()
    }


def _filed_forms(landing: dict, parquet: pq.ParquetFile) -> dict[int, list[str]]:
    """Each CIK's distinct forms, from the capture that landed its Company row."""
    filed: dict[int, set[str]] = {}
    for batch in parquet.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Filing row belongs to a different capture run")
            if row["cik"] is None or not row["form"]:
                continue
            filed.setdefault(int(row["cik"]), set()).add(row["form"])
    return {cik: sorted(forms) for cik, forms in filed.items()}


def _business_addresses(landing: dict, parquet: pq.ParquetFile) -> dict[int, dict]:
    """Each CIK's business address postcode and country, from its own capture.

    SEC writes a state code where a country belongs; a state means the United
    States (`names.edgar_jurisdiction`). A foreign address carries its EDGAR
    country code in `countryCode` instead and leaves `stateOrCountry` empty
    (Shell: "X0"); the two never both hold a value, so the country is read
    from the first, else the second, as the matching rules were measured
    (ticket 14). A landing written before silver kept `country_code` has no
    such column and reads as it always did.
    """
    found: dict[int, dict] = {}
    for batch in parquet.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Address row belongs to a different capture run")
            if row["cik"] is None or row["address_type"] != "business":
                continue
            found[int(row["cik"])] = business_address(row)
    return found


def business_address(row: dict) -> dict:
    """One landed business address as the Company record carries it."""
    place = edgar_jurisdiction(row["state_or_country"] or row.get("country_code"))
    return {
        "street": row["street1"] or None,
        "street2": row["street2"] or None,
        "city": row["city"] or None,
        # A region only for a state or province: SEC writes a foreign country
        # in the same field ("P7", the Netherlands), which is the country
        # (ticket 18).
        "region": (row["state_or_country"] or None) if place and "-" in place else None,
        "postal_code": row["zip_code"] or None,
        "country": place.split("-")[0] if place else None,
    }


@dataclass(frozen=True)
class _Pinned:
    """One landing member the Company rule reads, pinned beside the Company one."""

    field: str
    table: str
    file: str
    raw: bytes
    origin: dict
    by_cik: dict[int, object]
    # What a record carries when the member holds nothing for its CIK.
    empty: object


def _pin_evidence(
    root: Path,
    landing: dict,
    manifest_bytes: bytes,
    *,
    table: str,
    required: set[str],
    collect: Callable[[dict, pq.ParquetFile], dict[int, object]],
    field: str,
    file: str,
    empty: object = (),
) -> _Pinned:
    member, raw, parquet = _read_member(root, landing, table, required)
    return _Pinned(
        field=field,
        table=table,
        file=file,
        raw=raw,
        origin={
            "member": member["relative_path"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "run_id": landing["run_id"],
        },
        by_cik=collect(landing, parquet),
        empty=list(empty) if isinstance(empty, tuple) else empty,
    )


# Where each captured SEC document was written: the write receipts a capture
# run records in bookkeeping (`pipeline_run.raw_writes_json`), one per
# document (path, sha256). A Company row's raw_object_id is the sha256 of its
# submissions document, so a receipt names its exact bronze object (ticket 10).
RECEIPTS_VERSION = "sec-bronze-receipts-v1"
_SHA256 = re.compile("[0-9a-f]{64}")


def bronze_receipts(run_id: str, raw_writes: list[dict]) -> dict:
    """One capture run's bronze objects, by the sha256 of their bytes.

    A run records every write, and some (filing attachments, ADV manifests)
    carry no sha256: nothing can name them by hash, so they are left out. A
    stated sha256 that is not a lowercase digest is refused. Two receipts with
    one sha256 name byte-identical copies; the first path in sort order is
    kept, so the file is the same however the run listed them.
    """
    found: dict[str, str] = {}
    for write in raw_writes:
        if not isinstance(write, dict) or write.get("sha256") is None:
            continue
        sha, path = write["sha256"], write.get("path")
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise Conflict("A bronze write receipt has no lowercase sha256")
        if not isinstance(path, str) or not path:
            raise Conflict("A bronze write receipt names no object")
        found[sha] = min(found.get(sha, path), path)
    return {
        "version": RECEIPTS_VERSION,
        "run_id": run_id,
        "receipts": [{"sha256": k, "object": found[k]} for k in sorted(found)],
    }


def write_bronze_receipts(book, *, run_id: str, output: str) -> dict:
    """Write one capture run's bronze receipts from bookkeeping; never overwrite."""
    from sqlalchemy import text

    with book.connect() as conn:
        run = (
            conn.execute(
                text(
                    "SELECT status, raw_writes_json FROM pipeline_run "
                    "WHERE pipeline_run_id=:id"
                ),
                {"id": run_id},
            )
            .mappings()
            .one_or_none()
        )
    if run is None or run["status"] != "succeeded":
        raise Conflict(f"Capture run {run_id} did not succeed")
    raw = run["raw_writes_json"]
    if not raw:
        raise Conflict(f"Capture run {run_id} recorded no bronze writes")
    body = bronze_receipts(run_id, json.loads(raw))
    data = (canonical(body) + "\n").encode()
    target = Path(output).resolve()
    if target.exists():
        if target.read_bytes() != data:
            raise Conflict("Existing bronze receipts have different content")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    return {
        "version": RECEIPTS_VERSION,
        "run_id": run_id,
        "receipts": len(body["receipts"]),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _read_receipts(path: str, run_id: str) -> tuple[bytes, dict[str, str]]:
    raw = _read_bounded(Path(path).resolve(), 256 * 1024 * 1024)
    body = json.loads(raw)
    if body.get("version") != RECEIPTS_VERSION:
        raise Conflict("Unsupported bronze receipts")
    if body.get("run_id") != run_id:
        raise Conflict("The bronze receipts belong to another capture run")
    rebuilt = bronze_receipts(
        run_id,
        [
            {"path": r.get("object"), "sha256": r.get("sha256")}
            for r in body.get("receipts", [])
        ],
    )
    if rebuilt != body:
        raise Conflict("The bronze receipts are not in their canonical form")
    return raw, {r["sha256"]: r["object"] for r in body["receipts"]}


def _census_evidence(census: dict, row: dict, census_hash: str) -> dict | None:
    """What the census says of one SEC record: its name's entry and, when
    the census ran the cascade (ticket 21), the answer for its CIK. Both are
    one pinned document, so the record carries them as one value."""
    from . import cascade

    found = census_entry(census, row["entity_name"], census_digest=census_hash)
    if "cascade" not in census:
        return found
    answer = cascade.entry(census, f"{int(row['cik']):010d}", census_digest=census_hash)
    if answer is None:
        return found  # no answer for this CIK: the record is as before
    return {**(found or {}), "cascade": answer}


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
    if (census.get("sec") or {}).get("capture_run_id") != landing["run_id"] or (
        census["sec"].get("company_member_sha256") != raw_hash
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
        _pin_evidence(
            root,
            landing,
            manifest_bytes,
            table="sec_company_filing",
            required={"cik", "form", "last_sync_run_id"},
            collect=_filed_forms,
            field="forms",
            file="filings.parquet",
        ),
        _pin_evidence(
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
            collect=_business_addresses,
            field="business_address",
            file="addresses.parquet",
            empty=None,
        ),
        _pin_evidence(
            root,
            catalog,
            catalog_manifest_bytes,
            table="sec_company_ticker",
            required={"cik", "ticker", "source_rank", "last_sync_run_id"},
            collect=_catalog_tickers,
            field="tickers",
            file="tickers.parquet",
        ),
    )
    records = []
    for batch in parquet.iter_batches(batch_size=min(limit, 1000)):
        for row in batch.to_pylist():
            if len(records) == limit:
                break
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Company row belongs to a different capture run")
            records.append(
                {
                    **row,
                    **{e.field: e.by_cik.get(int(row["cik"]), e.empty) for e in pinned},
                    "name_census": _census_evidence(census, row, census_hash),
                    "_origin": {
                        "member": member["relative_path"],
                        "sha256": raw_hash,
                        "row_ordinal": len(records) + 1,
                        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                        **{e.field: e.origin for e in pinned},
                        "name_census_sha256": census_hash,
                        # The bronze submissions document this row was read
                        # from, whole; not part of the record (ticket 10).
                        **(
                            {
                                "bronze": {
                                    "object": bronze[row["raw_object_id"]],
                                    "sha256": row["raw_object_id"],
                                    "locator": "$",
                                }
                            }
                            if row["raw_object_id"] in bronze
                            else {}
                        ),
                    },
                }
            )
        if len(records) == limit:
            break
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


def census_filers(
    *, landing_root: str, landing_manifest: str
) -> tuple[list[tuple[str, str | None, list[str]]], dict]:
    """Every SEC filer in one capture with its former names, for the Name Census.

    The census counts the whole capture, never a sample: a name that looks
    unique in a sample may not be (ticket 08). The population it returns names
    the exact members it read, so a bundle can refuse a census of another
    capture.
    """
    root = Path(landing_root).resolve()
    landing, _ = _read_manifest(root, landing_manifest)
    _, company_raw, company = _read_member(
        root, landing, "sec_company", {"cik", "entity_name", "last_sync_run_id"}
    )
    _, former_raw, former = _read_member(
        root,
        landing,
        "sec_company_former_name",
        {"cik", "former_name", "last_sync_run_id"},
    )
    earlier: dict[int, list[str]] = {}
    for batch in former.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Former-name row belongs to a different capture run")
            if row["cik"] is not None and row["former_name"]:
                earlier.setdefault(int(row["cik"]), []).append(row["former_name"])
    filers = []
    for batch in company.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Company row belongs to a different capture run")
            cik = f"{int(row['cik']):010d}"
            filers.append((cik, row["entity_name"], earlier.get(int(row["cik"]), [])))
    population = {
        "capture_run_id": landing["run_id"],
        "company_member_sha256": hashlib.sha256(company_raw).hexdigest(),
        "former_name_member_sha256": hashlib.sha256(former_raw).hexdigest(),
        "filers": len(filers),
    }
    return filers, population


_ADDRESS_COLUMNS = {
    "cik", "address_type", "street1", "street2", "city", "zip_code", "state_or_country", "last_sync_run_id",
}


def cascade_filers(*, landing_root: str, landing_manifest: str) -> tuple[list, dict]:
    """Every SEC filer in one capture as the cascade reads it (ticket 21):
    the row with its business address, through the SEC contract and its data
    quality rule, as `normalize` reads a Company record. Every filer counts,
    a Company or not: each can hold a name another would match. A filer the
    quality rule makes an exception never merges and is left out.
    """
    root = Path(landing_root).resolve()
    landing, _ = _read_manifest(root, landing_manifest)
    _, _, company = _read_member(root, landing, "sec_company", {"cik", "entity_name", "last_sync_run_id"})
    _, address_raw, addresses = _read_member(root, landing, "sec_company_address", _ADDRESS_COLUMNS)
    business = _business_addresses(landing, addresses)
    filers = []
    for batch in company.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Company row belongs to a different capture run")
            if found := cascade_filer(row, business.get(int(row["cik"]))):
                filers.append(found)
    return filers, {"address_member_sha256": hashlib.sha256(address_raw).hexdigest()}


def cascade_filer(row: dict, business: dict | None):
    """One landed Company row and its business address as the cascade reads
    it, through the SEC contract and its data quality rule; None when the
    quality rule makes it an exception, which never merges. The census and
    the proof (`21-cascade.py`) both read filers here."""
    from . import cascade
    from .adapters import UnsupportedRecord, mapped_values

    try:
        fields, matching, quality = mapped_values({**row, "business_address": business}, CONTRACT)
    except UnsupportedRecord:
        return None
    return cascade.filer_of(cascade.record(f"{int(row['cik']):010d}", fields, matching, quality))


def write_name_census(
    *,
    landing_root: str,
    landing_manifest: str,
    gleif_archive: str,
    gleif_metadata: str,
    gleif_sha256: str,
    output: str,
) -> dict:
    """Count one SEC capture and one full GLEIF Golden Copy into a census file.

    An existing census is never overwritten with different content.
    """
    from . import cascade as cascaded
    from .gleif_source import dataset_contract
    from .name_census import build

    filers, population = census_filers(
        landing_root=landing_root, landing_manifest=landing_manifest
    )
    # The cascade's passes (ticket 21), from the Company rules. The census
    # runs them only once one is switched on (ticket 20); until then it and
    # every record it feeds are as before. It runs every declared pass, in
    # order: an earlier pass's answer never depends on a later one.
    spec = cascaded.spec(POLICY)
    cascade = None
    if spec["passes"] and any(
        t["primitive"] == cascaded.TEST for _, rule in active_rules(POLICY) for t in rule["when"]
    ):
        cascade_population, pinned = cascade_filers(
            landing_root=landing_root, landing_manifest=landing_manifest
        )
        population = {**population, **pinned}
        cascade = {"spec": spec, "filers": cascade_population, "gleif_contract": dataset_contract("level1")}
    metadata = json.loads(Path(gleif_metadata).read_text())
    with Path(gleif_archive).open("rb") as archive:
        census = build(
            filers=filers,
            sec_population=population,
            gleif_archive=archive,
            gleif_metadata=metadata,
            gleif_sha256=gleif_sha256,
            cascade=cascade,
        )
    data = (canonical(census) + "\n").encode()
    target = Path(output).resolve()
    if target.exists():
        if target.read_bytes() != data:
            raise Conflict("Existing Name Census has different content")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return {
        "version": census["version"],
        "sha256": digest(census),
        "sec": census["sec"],
        "gleif": census["gleif"],
        "entries": len(census["entries"]),
    }


# Ticket 08, the SEC-to-GLEIF matching rules, measured on bronze and the
# pinned GLEIF Golden Copy and passing: declared in the Company merge rules,
# inactive. Their proofs carry no approval: switching a rule on is a separate
# decision (`rules/merge/pending-proofs.yaml`).
NAME_PROOFS = rules_files.pending_proofs()


def _is_cascade_pass(rule: dict) -> bool:
    from .cascade import TEST

    return any(t["primitive"] == TEST for t in rule["when"])


def name_matching_policy(*, active: bool) -> dict:
    """The live Company policy, with its matching rules' activations if `active`.

    The rules are declared in `rules/merge/kinds/company.yaml` and inactive. With
    `active`, it also names their measured activations; those pass the
    activation check only once the operator's approval fills each proof.
    """
    body = json.loads(canonical(POLICY))
    if active:
        body["automatic_rules"] = [
            *body["automatic_rules"],
            *(
                {
                    "kind": "company",
                    "family": FAMILY,
                    "rule_id": rule["rule_id"],
                    "rule_version": rule["version"],
                    "verdict": "bind",
                    "activation": "measured",
                    "proof": NAME_PROOFS[rule["rule_id"]],
                }
                for rule in body["kinds"]["company"]["rules"]
                # A cascade pass waits for its own proof (ticket 21); every
                # other matching rule must have one, or this fails closed.
                if rule["family"] == FAMILY and not _is_cascade_pass(rule)
            ),
        ]
    return body
