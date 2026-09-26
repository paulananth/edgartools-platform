"""Bounded SEC Company landing adapter and immutable local input preparation.

Preparation neither activates source coverage nor allocates/binds identities.
The generated contract and policy are reviewable governance inputs.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pyarrow.parquet as pq

from ..policies import load_kinds
from .evidence import instant
from .matching import FAMILY
from .name_census import entry as census_entry
from .names import edgar_jurisdiction
from .store import Conflict, canonical, digest

SOURCE_CODE = "sec.submissions.company.v1"
FIELDS = {
    "name": "entity_name",
    "sic": "sic",
    "sic_description": "sic_description",
    # SEC's own field, as SEC writes it ("CA", "DC", "E9"). Jurisdiction is
    # GLEIF's, a separate field, so the two never compete (operator,
    # 2026-09-24).
    "state_of_incorporation": "state_of_incorporation",
    "fiscal_year_end": "fiscal_year_end",
    "description": "description",
    "address": {
        "components": {
            "street": "business_address.street",
            "street2": "business_address.street2",
            "city": "business_address.city",
            "region": "business_address.region",
            "postcode": "business_address.postal_code",
            "country": "business_address.country",
        }
    },
}
CONTRACT = {
    "provider": "SEC",
    "family": "submissions",
    "schema_version": "silver-company-v1",
    "record_key": "zero-padded 10-digit CIK",
    "publication_key": "capture run plus exact company landing member digest, "
    "plus the exact filing-list, business-address and ticker catalog member "
    "digests, plus the Name Census digest",
    "effective_time": "unknown; last_synced_at is observation time only",
    "semantics": "patch",
    "completeness": "explicit bounded Company sample; no retirement by absence",
    "adapter": {
        "version": "sec-company-landing-v6",
        "retain_deferred": True,
        "source_record_provenance": True,
        "field_shape": "nullable_text",
        "record_key": ["cik"],
        "record_key_format": "sec_cik",
        # The measured Company classification rule, not a lookup table: SEC
        # types a foreign issuer "other", as it does an individual (ticket 12).
        "classification": {
            "kind": "company",
            "rule_id": "sec-company-candidate",
            "version": "2026-09-25.13",
        },
        "identifiers": {"cik": "cik"},
        "identifier_formats": {"cik": "sec_cik"},
        "fields": FIELDS,
        "provenance": {
            "landing_sha256": "_origin.sha256",
            "landing_manifest_sha256": "_origin.manifest_sha256",
            "raw_object_id": "raw_object_id",
            "capture_run_id": "last_sync_run_id",
            "observed_at": "last_synced_at",
            "filing_landing_sha256": "_origin.forms.sha256",
            "ticker_landing_sha256": "_origin.tickers.sha256",
            "ticker_run_id": "_origin.tickers.run_id",
            "address_landing_sha256": "_origin.business_address.sha256",
        },
        # What the SEC-to-GLEIF matching rules compare, kept with the record
        # and out of its fields: address as a Company field is ticket 09's
        # decision (company mastering ticket 08).
        "matching": {
            "business_postal_code": "business_address.postal_code",
            "business_country": "business_address.country",
            "name_census": "name_census",
        },
    },
}
# Ticket 12, the Account hold-back (rule 2026-09-25.13): both Company steps
# clear the 95% bar and the fresh adversarial fixture has no violation.
# The operator approved the frozen inactive-policy digest
# 31fdbef91859cd8f7423a827ae29156c190b013cff14cde184f3585a2c56f63f
# on 2026-09-25. The approval timestamp below is when that reply was processed.
PROOF = {
    "method": "wilson_lower_bound",
    "one_sided_confidence": 0.95,
    "n": 600,
    "correct": 600,
    "lower_bound": 0.995511,
    "adversarial": {
        "fixture_sha256": "ebe220479915a56f86f5c57edc2665f5ad6d40f55d112b7849899941beed49f1",
        "n": 328,
        "violations": 0,
    },
    "cohort": {
        "population_sha256": "395b7db4cfeb5ab0d4816ee4c0e68ca078b548fce3b8337c0ab671f0e0668600",
        "ticker_catalog_sha256": "836140c5ca9817b673e76f4c4cf25dda6650215683c1705e9fbe00b2e8f16fbf",
        "by_step": {
            "8": {"n": 300, "correct": 300, "lower_bound": 0.9910621278248719},
            "10": {"n": 300, "correct": 300, "lower_bound": 0.9910621278248719},
        },
        "files": {
            "12-13-adversarial.jsonl": "ebe220479915a56f86f5c57edc2665f5ad6d40f55d112b7849899941beed49f1",
            "12-13-held.jsonl": "989057c5f33177c1a53c182a757d00b6909df61a852bf9e2b6b0bd746d345fcc",
            "12-13-label.py": "3858117cf62df1de0d6adfac6cd348da5a36e4d9587bcf82b69f358a90ed9e12",
            "12-13-population.json": "b6023c5ef814ff496137ddd51c395582d07d316038ad23eb40a96bf64a741a49",
            "12-13-sample.jsonl": "d276df62557c30106d8f49c52f23c0ea72c4795c664e96983c7569f91dd6ad97",
            "12-classify.py": "0a1bde95ebca00dbc6b6cda39827f5688e540cd2a35714c411162f69b0395c4a",
            "12-measure-13.py": "6fc1e10772f89f369513d74d80927670dce71e7b937e149951a50311aaf66ceb",
        },
    },
    "approved_by": "operator",
    "approved_at": "2026-09-25T17:09:33Z",
    "reason": "ticket 12 Proving Run, SEC Company classification, the Account "
    "hold-back: bronze-only hand review, each Company step clears 0.95, "
    "0 adversarial violations",
}
APPROVED_ACTIVATION = {
    "kind": "company",
    "family": "classification",
    "rule_id": "sec-company-candidate",
    "rule_version": "2026-09-25.13",
    "verdict": "company",
    "activation": "measured",
    "proof": PROOF,
}
POLICY = {
    "version": "sec-company-local-v2",
    "automatic_rules": [APPROVED_ACTIVATION],
    "required_consumers": ["journal", "export", "graph"],
    # Each kind's rules are data, one file per kind, loaded rather than
    # restated here (operator, 2026-09-24).
    "kinds": load_kinds(),
}


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
    return {cik: [t for _, t in sorted(pairs)] for cik, pairs in listed.items()}


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
    States (`names.edgar_jurisdiction`). Silver keeps `stateOrCountry` only,
    not SEC's separate `countryCode`, so a foreign filer that SEC files under
    `countryCode` alone (Shell) has no country here (ticket 08).
    """
    found: dict[int, dict] = {}
    for batch in parquet.iter_batches(batch_size=10_000):
        for row in batch.to_pylist():
            if row["last_sync_run_id"] != landing["run_id"]:
                raise Conflict("Address row belongs to a different capture run")
            if row["cik"] is None or row["address_type"] != "business":
                continue
            place = edgar_jurisdiction(row["state_or_country"])
            found[int(row["cik"])] = {
                "street": row["street1"] or None,
                "street2": row["street2"] or None,
                "city": row["city"] or None,
                "region": row["state_or_country"] or None,
                "postal_code": row["zip_code"] or None,
                "country": place.split("-")[0] if place else None,
            }
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
                    "name_census": census_entry(
                        census, row["entity_name"], census_digest=census_hash
                    ),
                    "_origin": {
                        "member": member["relative_path"],
                        "sha256": raw_hash,
                        "row_ordinal": len(records) + 1,
                        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                        **{e.field: e.origin for e in pinned},
                        "name_census_sha256": census_hash,
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
    from .name_census import build

    filers, population = census_filers(
        landing_root=landing_root, landing_manifest=landing_manifest
    )
    metadata = json.loads(Path(gleif_metadata).read_text())
    with Path(gleif_archive).open("rb") as archive:
        census = build(
            filers=filers,
            sec_population=population,
            gleif_archive=archive,
            gleif_metadata=metadata,
            gleif_sha256=gleif_sha256,
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
# pinned GLEIF Golden Copy (2026-09-11 16:00 UTC) and passing. The operator
# approved them as declared rules (policy fingerprint `983352e8...`,
# 2026-09-25 15:21 ET); they sit in `policies/company.json`, inactive. The
# proofs carry no approval: switching a rule on is a separate decision.
_RESEARCH_FILES_08 = {
    "08-labelling-standard.md": "9b6b734ee50c7c6b85cdb5d8d6792a880313a35b3108b8fc7c294310baa84dfa",
    "08-rules.json": "0422274b9db81ee027c3af7f2a294563265fe5a8e7fc6096a0e5b9e203139e5e",
}
NAME_PROOFS = {
    # The Name-and-state rule.
    "sec-gleif-name-jurisdiction": {
        "method": "wilson_lower_bound",
        "one_sided_confidence": 0.95,
        "n": 300,
        "correct": 300,
        "lower_bound": 0.991062,
        "adversarial": {
            "fixture_sha256": "18b948b361ec72c1938004961f58e90461d1db4a273acdbc0c1d92629636cb8a",
            "n": 257,
            "violations": 0,
        },
        "cohort": {
            "coverage_sha256": "3b51d0ac8b0b531768466c4a246bbb2e94b3856d1a0658525a7245b4e5e1f698",
            "gleif_golden_copy_sha256": "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a",
            "sec_filers": 76230,
            "files": {
                **_RESEARCH_FILES_08,
                "08-1-adversarial.jsonl": "18b948b361ec72c1938004961f58e90461d1db4a273acdbc0c1d92629636cb8a",
                "08-1-label.py": "df7bc5cd449ec7e87dadba3d8cdb28ae7ec640799bce9fba64ab02896b25a055",
                "08-1-population.json": "c978d0f0ae5f9f0ad431a1533760fa230539ad5e96a007f9cc86d7cda01705b5",
                "08-1-sample.jsonl": "1e535c09d0b0e42d5ebea725eb36111b9978008bb5ef576098d9253de5ad38ee",
                "08-measure-1.py": "ffec26f741692f2ca03764d534857ecf9f42dad6352addc93bb1a6601e504622",
            },
        },
        "approved_by": None,
        "approved_at": None,
        "reason": "ticket 08 Proving Run, the Name-and-state rule: hand-read "
        "bronze and GLEIF pairs, 300/300, 0 adversarial violations",
    },
    # The Postcode rule with state veto.
    "sec-gleif-name-postal": {
        "method": "wilson_lower_bound",
        "one_sided_confidence": 0.95,
        "n": 300,
        "correct": 300,
        "lower_bound": 0.991062,
        "adversarial": {
            "fixture_sha256": "fb25320ce2f8201130cbc94c651ece8bd8539bb9adef34b3e7eed475b72168fa",
            "n": 315,
            "violations": 0,
        },
        "cohort": {
            "coverage_sha256": "97e5d11824dc146f5446d3482c2a5214137a98bb18ec85c9674ca27e6a966509",
            "gleif_golden_copy_sha256": "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a",
            "sec_filers": 76230,
            "files": {
                **_RESEARCH_FILES_08,
                "08-2-adversarial.jsonl": "fb25320ce2f8201130cbc94c651ece8bd8539bb9adef34b3e7eed475b72168fa",
                "08-2-label.py": "a6e799362c3f333329cb93037a6c01e21277b6e93d526034cc88d7736f015fbe",
                "08-2-population.json": "3c44839448092dea6d2f1cdff7707cfd56e29efc6e102fdf42536f9620e63028",
                "08-2-sample.jsonl": "c7aabc53fdd6a5e881c73945970ef59259758943b188c4b5cc9ee927669b6a70",
                "08-measure-2.py": "fe5988c90b5e0726c8be364eeb2e8ab8670acfb9cad5e40f11db96b523430cbf",
            },
        },
        "approved_by": None,
        "approved_at": None,
        "reason": "ticket 08 Proving Run, the Postcode rule with state veto: "
        "fresh draw excluding every earlier CIK, 300/300, 0 adversarial "
        "violations",
    },
}


def name_matching_policy(*, active: bool) -> dict:
    """The live Company policy, with its matching rules' activations if `active`.

    The rules are declared in `policies/company.json` and inactive. With
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
                if rule["family"] == FAMILY
            ),
        ]
    return body
