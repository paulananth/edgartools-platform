"""Bind authenticated GLEIF publication authority to generic attestation.

A GLEIF record is read by its member's contract (`dataset_contract`); this module
keeps only what a publication itself must prove: its member, format and times.
"""
from __future__ import annotations

import copy
import hashlib
import zipfile

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers.source_attestation import attest_zip

from .evidence import instant
from .store import Conflict

# Hashed into every attestation's `domain_content_hash`: never change the text.
VERSION = "gleif-native-record-v1"
FORMATS = {
    "level1": ("LEI_3.1", "records"),
    "relationships": ("RR_2.1", "relations"),
    "reporting_exceptions": ("REPEX_2.1", "exceptions"),
}


def validate_metadata(member: str, metadata: dict) -> None:
    if not isinstance(metadata, dict):
        raise Conflict("Invalid GLEIF member metadata")
    if member not in FORMATS or metadata.get("cdf_version") != FORMATS[member][0]:
        raise Conflict("Unsupported GLEIF CDF version/member")
    if metadata.get("format") not in {"json.zip", "xml.zip"}:
        raise Conflict("Unsupported GLEIF archive format")
    count = metadata.get("record_count")
    if type(count) is not int or not 0 <= count <= 10_000_000:
        raise Conflict("Invalid GLEIF record count")
    try:
        date = instant(metadata["content_date"])
        mode = metadata["file_content"]
        if mode == "GLEIF_FULL_PUBLISHED" and metadata.get("delta_start") is None:
            return
        if mode == "GLEIF_DELTA_PUBLISHED" and instant(metadata["delta_start"]) < date:
            return
    except (KeyError, ValueError, TypeError) as exc:
        raise Conflict("Invalid GLEIF source time") from exc
    raise Conflict("Unsupported GLEIF publication mode or predecessor time")


def dataset_contract(member: str, *, level1_source: str | None = None) -> dict:
    """Governance input, not registration or activation. Field ranks live in policy.

    Each member's mapping is data in `rules/sources/gleif/source.yaml` (rules
    skill ticket 01). A relationship points at the Level 1 source the file
    names, at both ends; `level1_source` replaces it for a caller that
    registers Level 1 under another code.
    """
    for entry in files.source("gleif")["mdm"].values():
        contract = entry["contract"]
        if contract["adapter"]["native_member"] == member:
            if level1_source is not None:
                contract = copy.deepcopy(contract)
                for relationship in contract["adapter"].get("relationships", []):
                    relationship["target_source"] = level1_source
                    if relationship.get("source_key"):  # a link starts at Level 1 too
                        relationship["source_source"] = level1_source
            return contract
    raise ValueError("Unknown native GLEIF member")


def attest_publication(stream, *, member, metadata, expected_sha256, on_record=None,
                       max_compressed=1024**3, max_expanded=16*1024**3, max_record=1024**2):
    """Verify all captured records; authority comes from the pinned manifest."""
    validate_metadata(member, metadata)
    format_name = metadata["format"].split(".")[0]
    contract = files.load(files.ROOT / "sources" / "gleif"
                          / f"{member.replace('_', '-')}-{format_name}.yaml")
    read = contract["read"]
    spec = read["stream"]
    spec.update(max_input_bytes=max_compressed, max_bytes=max_expanded, max_record=max(1, max_record))
    read["limits"]["max_bytes"] = max(1, max_record)
    if "header_read" in spec:
        spec["max_header"] = max(1, max_record) + 65536
        spec["header_read"]["limits"]["max_bytes"] = spec["max_header"]
        predecessor = metadata.get("delta_start")
        spec["header_read"]["references"] = {
            "content_dates": {instant(metadata["content_date"]).isoformat(): {"valid": True}},
            "record_counts": {str(metadata["record_count"]): {"valid": True}},
            "file_content": {metadata["file_content"]: {
                "valid": True, "requires_delta": predecessor is not None}},
            "delta_starts": {instant(predecessor).isoformat(): {"valid": True}}
                if predecessor is not None else {},
        }
    consumer_error = None

    def consume(row, ordinal):
        nonlocal consumer_error
        if on_record is not None:
            try:
                on_record(row, ordinal)
            except BaseException as error:
                consumer_error = error
                raise

    try:
        report = attest_zip(stream, contract=contract, context={"publication_count": metadata["record_count"]},
                            expected_sha256=expected_sha256, on_record=consume)
    except (zipfile.BadZipFile, SourceRejected, StopIteration, ValueError) as exc:
        if exc is consumer_error:
            raise
        raise Conflict(f"Invalid GLEIF archive, header or bound: {exc}") from exc
    return {"adapter_version": VERSION, **report, "domain_content_hash": hashlib.sha256(
        f"{VERSION}\n{member}\n{report['canonical_source_hash']}".encode()).hexdigest()}
