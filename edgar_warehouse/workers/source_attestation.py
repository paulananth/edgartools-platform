"""Full-source attestation using configured native reading, without row spooling.

Callbacks may prepare provisional evidence. Only a returned report proves EOF;
this boundary supplies no publication authority or permission to commit evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import zipfile

from .source_stream import stream_policy


def attest_zip(stream, *, contract, context, expected_sha256, on_record=None):
    """Authenticate one private ZIP snapshot and every configured source record.

The explicit attestation declaration names the record and ordinal columns.
Scope selection is removed on a private contract copy: an attestation hashes
all source facts, including facts outside an approved mastering cohort.
"""
    contract = copy.deepcopy(contract)
    declaration = contract.get("attestation")
    if (not isinstance(declaration, dict)
            or set(declaration) != {"table", "record_column", "ordinal_column"}
            or any(not isinstance(v, str) or not v for v in declaration.values())):
        raise ValueError("Attestation declares exact table, record and ordinal columns")
    table = declaration["table"]
    read = contract["read"]
    if set(read["tables"]) != {table}:
        raise ValueError("Attestation requires one declared record table")
    columns = read["tables"][table]["columns"]
    if any(declaration[key] not in columns for key in ("record_column", "ordinal_column")):
        raise ValueError("Attestation column is absent from the configured table")
    read["tables"][table].pop("select", None)
    spec, engine, header_engine = stream_policy(contract)
    expected_name = spec.get("expected_records_context")
    expected_count = context.get(expected_name)
    if (spec["container"] != "zip" or expected_name is None
            or type(expected_count) is not int or not 0 <= expected_count <= spec["max_records"]):
        raise ValueError("Attestation requires a ZIP and bounded pinned record count")
    ordinal = spec["ordinal_context"]
    if ordinal is None or ordinal in context:
        raise ValueError("Attestation generates the configured ordinal context")
    engine.validate_context({**context, ordinal: 1})
    sha, content = hashlib.sha256(), hashlib.sha256()
    size, count = 0, 0
    consumer_error = None

    def consume(reading, index):
        nonlocal count, consumer_error
        rows = reading.tables[table]
        if reading.deferred or len(rows) != 1:
            raise ValueError("Source attestation must read every record")
        row = rows[0]
        if type(row[declaration["ordinal_column"]]) is not int or row[declaration["ordinal_column"]] != index + 1:
            raise ValueError("Source attestation ordinal mismatch")
        record = row[declaration["record_column"]]
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode()
        if len(encoded) > spec["max_record"]:
            raise ValueError("Source attestation record exceeds bound")
        if count >= expected_count:
            raise ValueError("Source attestation record count mismatch")
        content.update(encoded + b"\n")
        if on_record is not None:
            try:
                on_record(record, index)
            except BaseException as error:
                consumer_error = error
                raise
        count += 1

    try:
        with tempfile.TemporaryFile() as snapshot:
            while raw := stream.read(1024**2):
                size += len(raw)
                if size > spec["max_input_bytes"]:
                    raise ValueError("Compressed source size exceeds bound")
                snapshot.write(raw)
                sha.update(raw)
            if sha.hexdigest() != expected_sha256:
                raise ValueError("Source archive hash mismatch")
            snapshot.seek(0)
            with zipfile.ZipFile(snapshot) as archive:
                members = archive.infolist()
                if len(members) != 1 or members[0].is_dir() or members[0].flag_bits & 1:
                    raise ValueError("Source requires one unencrypted ZIP member")
                if members[0].file_size > spec["max_bytes"]:
                    raise ValueError("Expanded source size exceeds bound")
                with archive.open(members[0]) as source:
                    arguments = {key: spec[key] for key in
                                 ("max_bytes", "max_record", "max_depth")}
                    arguments.update(max_records=expected_count, context=context,
                                     ordinal_context=ordinal, on_reading=consume)
                    if header_engine is None:
                        scan = engine.stream_json_array(source, wrapper=spec["wrapper"],
                            min_integer=spec["min_integer"], record_encoding=spec["record_encoding"],
                            **arguments)
                    else:
                        scan = engine.stream_xml_records(source, envelope=spec["xml"],
                            header_engine=header_engine, max_header=spec.get("max_header"), **arguments)
                    if count != expected_count or scan["expanded_bytes"] != members[0].file_size:
                        raise ValueError("Source record count or expanded length mismatch")
    except BaseException:
        # Native callback wrappers must not replace consumer failures, including
        # cancellation and SourceRejected/ValueError raised by the consumer.
        if consumer_error is not None:
            raise consumer_error
        raise
    return {"raw_evidence_hash": sha.hexdigest(), "canonical_source_hash": content.hexdigest(),
            "record_count": count, "compressed_bytes": size, "expanded_bytes": scan["expanded_bytes"]}
