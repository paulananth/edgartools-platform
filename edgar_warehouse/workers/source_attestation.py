"""Full-source attestation using configured native reading, without row spooling.

Callbacks may prepare provisional evidence. Only a returned report proves EOF;
this boundary supplies no publication authority or permission to commit evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import cast

from . import source_traversal


def runtime_files():
    return [Path(__file__), *source_traversal.runtime_files()]


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
    traversal = source_traversal.Traversal(contract, archive_policy="whole")
    spec = traversal.spec
    # Whole-archive validation requires a pinned integer count.
    expected_count = cast(int, traversal.validate_context(context))
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
            # Whole-source attestation ignores values contributed by lookup sets.
            declared = read.get("lookup_sets") or {}
            scan = traversal.scan(snapshot, context=context, on_reading=consume,
                                  lookups={name: [] for name in declared})
    except BaseException:
        # Native callback wrappers must not replace consumer failures, including
        # cancellation and SourceRejected/ValueError raised by the consumer.
        if consumer_error is not None:
            raise consumer_error
        raise
    return {"raw_evidence_hash": sha.hexdigest(), "canonical_source_hash": content.hexdigest(),
            "record_count": count, "compressed_bytes": size, "expanded_bytes": scan["expanded_bytes"]}
