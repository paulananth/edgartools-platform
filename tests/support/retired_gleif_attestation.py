"""Historical attestation oracle; never imported by production code."""
import hashlib
import tempfile
import zipfile
from collections.abc import Callable
from typing import BinaryIO
from edgar_warehouse.rules import files as rules_files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.mdm.clean.gleif_source import VERSION, validate_metadata
from edgar_warehouse.mdm.clean.evidence import instant
from edgar_warehouse.mdm.clean.store import Conflict, canonical

def inspect_archive(
    stream: BinaryIO,
    *,
    member: str,
    metadata: dict,
    expected_sha256: str,
    on_record: Callable[[dict, int], None] | None = None,
    max_compressed: int = 1024**3,
    max_expanded: int = 16 * 1024**3,
    max_record: int = 1024**2,
) -> dict:
    """Verify through EOF. Callbacks may prepare evidence, never commit it.

    JSON metadata must come from the verified publication manifest. It is not
    inferred from the ZIP filename. A private compressed snapshot prevents a
    changed file between hashing and parsing from authenticating different bytes.
    """
    validate_metadata(member, metadata)
    sha, size, count = hashlib.sha256(), 0, 0
    content = hashlib.sha256()
    consumer_error = None
    with tempfile.TemporaryFile() as snapshot:
        while raw := stream.read(1024**2):
            size += len(raw)
            if size > max_compressed:
                raise Conflict("GLEIF compressed size exceeds bound")
            snapshot.write(raw)
            sha.update(raw)
        if sha.hexdigest() != expected_sha256:
            raise Conflict("GLEIF archive hash mismatch")
        snapshot.seek(0)
        try:
            with zipfile.ZipFile(snapshot) as archive:
                files = archive.infolist()
                if len(files) != 1 or files[0].is_dir() or files[0].flag_bits & 1:
                    raise Conflict("GLEIF requires one unencrypted ZIP member")
                if files[0].file_size > max_expanded:
                    raise Conflict("GLEIF expanded size exceeds bound")
                with archive.open(files[0]) as source:
                    def consume(row, ordinal):
                        nonlocal count, consumer_error
                        encoded = canonical(row).encode()
                        if len(encoded) > max_record:
                            raise Conflict("GLEIF record exceeds bound")
                        content.update(encoded + b"\n")
                        if count >= metadata["record_count"]:
                            raise Conflict("GLEIF record count mismatch")
                        if on_record:
                            try:
                                on_record(row, ordinal)
                            except BaseException as error:
                                consumer_error = error
                                raise
                        count += 1

                    # Full-source attestation and the Name Census need all
                    # records. This copied reading grants no mastering scope.
                    format_name = metadata["format"].split(".")[0]
                    contract = rules_files.load(
                        rules_files.ROOT / "sources" / "gleif"
                        / f"{member.replace('_', '-')}-{format_name}.yaml"
                    )
                    read = contract["read"]
                    framing = read.pop("stream")
                    table = member
                    read["tables"][table].pop("select")
                    read["limits"]["max_bytes"] = max(1, max_record)
                    engine = SourceEngine(contract)

                    def consume_reading(reading, ordinal):
                        rows = reading.tables[table]
                        if reading.deferred or len(rows) != 1:
                            raise Conflict("GLEIF source attestation must read every record")
                        row = rows[0]
                        if row["source_index"] != ordinal + 1:
                            raise Conflict("GLEIF source ordinal mismatch")
                        consume(row["record"], ordinal)

                    context = {"publication_count": metadata["record_count"]}
                    arguments = dict(
                        max_bytes=max_expanded, max_record=max(1, max_record),
                        max_records=min(metadata["record_count"], framing["max_records"]),
                        max_depth=framing["max_depth"], context=context,
                        ordinal_context=framing["ordinal_context"],
                        on_reading=consume_reading,
                    )
                    try:
                        if format_name == "json":
                            receipt = engine.stream_json_array(
                                source, wrapper=framing["wrapper"],
                                min_integer=framing["min_integer"],
                                record_encoding=framing["record_encoding"], **arguments,
                            )
                        else:
                            header = framing["header_read"]
                            max_header = max(1, max_record) + 65536
                            header["limits"]["max_bytes"] = max_header
                            predecessor = metadata.get("delta_start")
                            header["references"] = {
                                "content_dates": {instant(metadata["content_date"]).isoformat(): {"valid": True}},
                                "record_counts": {str(metadata["record_count"]): {"valid": True}},
                                "file_content": {metadata["file_content"]: {
                                    "valid": True, "requires_delta": predecessor is not None}},
                                "delta_starts": {instant(predecessor).isoformat(): {"valid": True}}
                                    if predecessor is not None else {},
                            }
                            receipt = engine.stream_xml_records(
                                source, envelope=framing["xml"], max_header=max_header,
                                header_engine=SourceEngine({"read": header}), **arguments,
                            )
                    except SourceRejected:
                        if consumer_error is not None:
                            raise consumer_error
                        raise
                    expanded = receipt["expanded_bytes"]
                    if count != metadata["record_count"] or expanded != files[0].file_size:
                        raise Conflict("GLEIF record count or expanded length mismatch")

        except (
            zipfile.BadZipFile,
            SourceRejected,
            StopIteration,
            ValueError,
        ) as exc:
            if isinstance(exc, SourceRejected) and exc is consumer_error:
                raise
            raise Conflict(f"Invalid GLEIF archive, header or bound: {exc}") from exc
    return {
        "adapter_version": VERSION,
        "raw_evidence_hash": sha.hexdigest(),
        "canonical_source_hash": content.hexdigest(),
        "record_count": count,
        # All native record content remains domain evidence, including fields
        # with no approved master projection. The tagged interpretation retains
        # those facts without hashing ZIP paths, timestamps or compression.
        "domain_content_hash": hashlib.sha256(
            f"{VERSION}\n{member}\n{content.hexdigest()}".encode()
        ).hexdigest(),
        "compressed_bytes": size,
        "expanded_bytes": expanded,
    }


