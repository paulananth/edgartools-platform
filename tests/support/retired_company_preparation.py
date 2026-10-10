"""Frozen Company preparation oracle from main 67e24723; test-only."""
from __future__ import annotations
import hashlib, json, os, shutil, tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import pyarrow.parquet as pq
from edgar_warehouse.mdm.clean.company_source import (
    SOURCE_CODE, CONTRACT, POLICY, ADDRESS_READING, _read_manifest, _read_member,
    _read_bounded, _read_receipts, Conflict, canonical, project_record)
from edgar_warehouse.mdm.clean.evidence import instant
from edgar_warehouse.mdm.clean.store import digest

from edgar_warehouse.mdm.clean.name_census import entry as census_entry

def _json_value(value):
    if isinstance(value, (date, datetime)): return value.isoformat()
    raise TypeError(f"Unsupported source scalar: {type(value).__name__}")

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
            found[int(row["cik"])] = project_record(row, ADDRESS_READING, column="fields")
    return found




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


def _census_evidence(census: dict, row: dict, census_hash: str) -> dict | None:
    """What the census says of one SEC record: its name's entry and, when
    the census ran the cascade (ticket 21), the answer for its CIK. Both are
    one pinned document, so the record carries them as one value."""
    from edgar_warehouse.mdm.clean import cascade

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
    sec = census.get("sec") or {}
    if not any(
        capture.get("capture_run_id") == landing["run_id"] and capture.get("company_member_sha256") == raw_hash
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
