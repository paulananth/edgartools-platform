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
    "publication_key": "capture run plus exact company landing member digest",
    "effective_time": "unknown; last_synced_at is observation time only",
    "semantics": "patch",
    "completeness": "explicit bounded Company sample; no retirement by absence",
    "adapter": {
        "version": "sec-company-landing-v2",
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
            "version": "2026-09-25.9",
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
        },
    },
}
# Ticket 12: version .8 cleared both measured Company steps and the
# adversarial check. The proposal below is not an activation until the operator
# approves this exact policy digest and supplies the true approval time.
PROOF = {
    "method": "wilson_lower_bound",
    "one_sided_confidence": 0.95,
    "n": 600,
    "correct": 599,
    "lower_bound": 0.992564,
    "adversarial": {
        "fixture_sha256": "30e21122647a9085a48ac597b5b661018644de8bd52cad7755ec5c50ea424f01",
        "n": 483,
        "violations": 0,
    },
    "cohort": {
        "population_sha256": "395b7db4cfeb5ab0d4816ee4c0e68ca078b548fce3b8337c0ab671f0e0668600",
        "by_step": {
            "2": {"n": 300, "correct": 299, "lower_bound": 0.9851990393158567},
            "4": {"n": 300, "correct": 300, "lower_bound": 0.9910621278248719},
        },
        "files": {
            "12-sample.jsonl": "921e89d72cdce724cad3a9e594addd27ea92546f312e0458e1d6c1373b4d0beb",
            "12-adversarial.jsonl": "30e21122647a9085a48ac597b5b661018644de8bd52cad7755ec5c50ea424f01",
            "12-population.json": "cd005bca0296a8b671f5e637bb145cea6ea392e4398ad01e7e766b5377a4c941",
            "12-classify.py": "0a1bde95ebca00dbc6b6cda39827f5688e540cd2a35714c411162f69b0395c4a",
            "12-label-reviewed.py": "7e98a8059ead4279ce28e600c9d97c03a5539384bd362598921b5b973b725b4a",
        },
    },
    "approved_by": None,
    "approved_at": None,
    "reason": "ticket 12 Proving Run, SEC Company classification, rule .8: "
    "bronze-only hand review, each step clears 0.95, 0 adversarial violations",
}
PENDING_ACTIVATION = {
    "kind": "company",
    "family": "classification",
    "rule_id": "sec-company-candidate",
    "rule_version": "2026-09-24.8",
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


def prepare_company_bundle(
    *,
    landing_root: str,
    landing_manifest: str,
    output: str,
    limit: int,
    as_of: str,
    revision: int,
) -> dict:
    if not 1 <= limit <= 1000 or type(revision) is not int or revision < 0:
        raise ValueError(
            "Require --limit 1..1000 and a nonnegative explicit publication revision"
        )
    instant(as_of)
    root = Path(landing_root).resolve()
    manifest_path = Path(landing_manifest).resolve()
    if not manifest_path.is_relative_to(root):
        raise ValueError("Landing manifest must be inside its root")
    manifest_bytes = _read_bounded(manifest_path, 1024 * 1024)
    landing = json.loads(manifest_bytes)
    if (
        landing.get("schema_version") != 1
        or landing.get("target") != "silver_landing"
        or not landing.get("run_id")
    ):
        raise ValueError("Unsupported landing manifest contract")
    members = [t for t in landing["tables"] if t["table_name"] == "sec_company"]
    if len(members) != 1 or members[0].get("file_count") != 1:
        raise ValueError(
            "Require one explicit Company member; multi-file landing needs a partition contract"
        )
    member = members[0]
    path = (root / member["relative_path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Landing member escapes its root")
    raw = _read_bounded(path, 64 * 1024 * 1024)
    raw_hash = hashlib.sha256(raw).hexdigest()
    parquet = pq.ParquetFile(io.BytesIO(raw))
    if parquet.metadata.num_rows != member["row_count"]:
        raise Conflict("Landing member row count disagrees with its manifest")
    required = {
        "cik",
        "entity_name",
        "entity_type",
        "raw_object_id",
        "last_sync_run_id",
        "last_synced_at",
    }
    if not required <= set(parquet.schema_arrow.names):
        raise ValueError("Company landing schema is missing required evidence columns")
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
                    "_origin": {
                        "member": member["relative_path"],
                        "sha256": raw_hash,
                        "row_ordinal": len(records) + 1,
                        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
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
    publication_key = f"{landing['run_id']}:sec_company:{raw_hash}"
    scope = {
        "mode": "bounded_sample",
        "selected_records": len(records),
        "available_company_records": parquet.metadata.num_rows,
        "whole_source_complete": False,
        "capture_run_id": landing["run_id"],
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
