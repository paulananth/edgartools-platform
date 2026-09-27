"""Bounded record normalization using the source reading frozen by Rules."""
from __future__ import annotations

import base64

from sqlalchemy import text

from .artifacts import json_value
from .config import Blocked, digest, reference


def normalize_input(book, spec: dict, export: dict, mdm_engine, policy_digest: str) -> dict:
    """Read exact NDJSON bytes; neither discover inputs nor select a source callback."""
    from edgar_warehouse.mdm.clean.activation import check_policy
    from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
    from edgar_warehouse.mdm.clean.evidence import deferred_record

    if (not isinstance(spec, dict) or set(spec) != {"source_code", "artifact", "publication", "record_count"}
            or not isinstance(spec["source_code"], str) or not spec["source_code"]
            or type(spec["record_count"]) is not int or not 1 <= spec["record_count"] <= 1000):
        raise Blocked("Source input requires a dataset, artifact, publication and 1..1000 records")
    ref = reference(spec["artifact"])
    publication = spec["publication"]
    if (not isinstance(publication, dict) or set(publication) - {"publication_key", "revision", "effective_at"}
            or not {"publication_key", "revision"} <= set(publication)
            or not isinstance(publication["publication_key"], str) or not publication["publication_key"]
            or type(publication["revision"]) is not int or publication["revision"] < 0):
        raise Blocked("Source input requires immutable publication identity and revision")
    code = spec["source_code"]
    frozen = (export.get("registration") or {}).get("datasets", {}).get(code)
    declared = export["body"].get("mdm", {}).get(code)
    if not frozen or not declared:
        raise Blocked("Source input has no reading in the frozen Rules registration")
    with mdm_engine.connect() as conn:
        contract = conn.scalar(text("SELECT body FROM mdm_v2.dataset_mapping WHERE source_code=:c AND mapping_version=:v"),
                               {"c": code, "v": frozen["mapping_version"]})
        policy = conn.scalar(text("SELECT body FROM mdm_v2.policy WHERE digest=:d"), {"d": policy_digest})
    if (not contract or digest(contract) != frozen["digest"]
            or {k: v for k, v in contract.items() if k != "registry_evidence"} != declared["contract"]):
        raise Blocked("Frozen dataset reading is missing or differs from its registration")
    if not policy or digest(policy) != policy_digest:
        raise Blocked("Frozen mastering policy is missing or corrupt")
    check_policy(policy)
    adapter = contract.get("adapter")
    if not isinstance(adapter, dict):
        raise Blocked("Source reading has no supported mapping adapter")
    raw = book.artifacts.verified(ref, max_bytes=16 * 1024**2)
    assertions, deferred, occurrences = [], [], []
    for ordinal, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        if len(assertions) + len(deferred) >= spec["record_count"]:
            raise Blocked("Source input exceeds its declared record_count")
        origin = {**publication, "artifact_sha256": ref["sha256"], "member": ref["uri"],
                  "record_locator": f"{ref['sha256']}:line:{ordinal}"}
        try:
            row = json_value(line)
        except (ValueError, UnicodeError):
            row = {"raw_bytes_base64": base64.b64encode(line).decode("ascii")}
            problem = UnsupportedRecord("invalid_json_record")
        else:
            problem = None
        try:
            if problem:
                raise problem
            found = normalize(row, source_code=code, contract=contract, publication=origin,
                              mapping_version=frozen["mapping_version"], policy=policy)
            assertions.append(found)
            bronze = (row.get("_origin") or {}).get("bronze")
            if bronze is not None:
                if not isinstance(bronze, dict):
                    raise Blocked("Invalid bronze occurrence")
                occurrences.append({"assertion_id": found["assertion_id"], "object": bronze.get("object"),
                                    "sha256": bronze.get("sha256"), "locator": bronze.get("locator")})
        except UnsupportedRecord as exc:
            if not adapter.get("retain_deferred", False):
                raise Blocked(f"Source record cannot be normalized: {exc.reason}") from exc
            deferred.append(deferred_record(
                source_code=code, publication_key=origin["publication_key"],
                record_locator=origin["record_locator"], schema_version=contract["schema_version"],
                reason=exc.reason, raw_record=row, probable_kind=exc.probable_kind,
                provenance={"artifact_sha256": ref["sha256"], "member": ref["uri"],
                            "adapter_version": adapter["version"], **exc.detail}))
    if len(assertions) + len(deferred) != spec["record_count"]:
        raise Blocked("Source input record_count mismatch")
    return {"assertions": assertions, "deferred": deferred, "occurrences": occurrences}
