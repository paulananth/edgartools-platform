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
}
CONTRACT = {
    "provider": "SEC",
    "family": "submissions",
    "schema_version": "silver-company-v1",
    "record_key": "zero-padded 10-digit CIK",
    "publication_key": "capture run plus exact company landing member digest, "
    "plus the exact filing-list and ticker catalog member digests",
    "effective_time": "unknown; last_synced_at is observation time only",
    "semantics": "patch",
    "completeness": "explicit bounded Company sample; no retirement by absence",
    "adapter": {
        "version": "sec-company-landing-v4",
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
        },
    },
}
# Ticket 12, the Account hold-back (rule 2026-09-25.13): both Company steps
# clear the 95% bar and the fresh adversarial fixture has no violation. The
# proposal below is not an activation until the operator approves this exact
# policy digest and supplies the true approval time.
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
    "approved_by": None,
    "approved_at": None,
    "reason": "ticket 12 Proving Run, SEC Company classification, the Account "
    "hold-back: bronze-only hand review, each Company step clears 0.95, "
    "0 adversarial violations",
}
PENDING_ACTIVATION = {
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
    # The operator has not approved this digest, so no verdict acts alone.
    "automatic_rules": [],
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


@dataclass(frozen=True)
class _Pinned:
    """One landing member the Company rule reads, pinned beside the Company one."""

    field: str
    table: str
    file: str
    raw: bytes
    origin: dict
    by_cik: dict[int, list[str]]


def _pin_evidence(
    root: Path,
    landing: dict,
    manifest_bytes: bytes,
    *,
    table: str,
    required: set[str],
    collect: Callable[[dict, pq.ParquetFile], dict[int, list[str]]],
    field: str,
    file: str,
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
    )


def prepare_company_bundle(
    *,
    landing_root: str,
    landing_manifest: str,
    ticker_manifest: str,
    output: str,
    limit: int,
    as_of: str,
    revision: int,
) -> dict:
    """Pin a bounded Company sample with the evidence its rule reads.

    The Company rule reads two things the Company row does not carry
    (ticket 12): the forms a filer files, landed by the same capture
    (`sec_company_filing`), and its tickers, which SEC publishes in a catalog
    of its own landed by a separate run (`sec_company_ticker`). Each member
    is pinned beside the Company one, and its digest is part of the key.
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
                    **{e.field: e.by_cik.get(int(row["cik"]), []) for e in pinned},
                    "_origin": {
                        "member": member["relative_path"],
                        "sha256": raw_hash,
                        "row_ordinal": len(records) + 1,
                        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                        **{e.field: e.origin for e in pinned},
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
    publication_key = f"{landing['run_id']}:sec_company:{raw_hash}" + "".join(
        f":{e.origin['run_id']}:{e.table}:{e.origin['sha256']}" for e in pinned
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
