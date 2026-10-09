"""Bind authenticated GLEIF publication authority to generic attestation."""
from __future__ import annotations

import hashlib
import zipfile

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers.source_attestation import attest_zip

from .evidence import instant
from .gleif_source import VERSION, validate_metadata
from .store import Conflict


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
