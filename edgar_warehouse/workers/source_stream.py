"""Configured record projection; private partitions until every input reaches EOF.

The stream declares framing and resource bounds. All field interpretation stays
in the ordinary source contract. No source-specific loader is called here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import zipfile
from contextlib import ExitStack

from edgar_warehouse.rules import source_engine


def _encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True, allow_nan=False).encode()


def _policy(contract):
    read = contract["read"]
    spec = read["stream"]
    maxima = {"max_input_bytes": 1024**3, "max_bytes": 8 * 1024**3,
              "max_record": 32 * 1024**2, "max_records": 10_000_000,
              "max_depth": 64, "partition_bytes": 8 * 1024**2,
              "partition_records": 100_000, "max_partitions": 4096,
              "max_spool_bytes": 1024**3, "max_output_rows": 10_000_000}
    required = {*maxima, "wrapper", "container", "min_integer", "record_encoding", "ordinal_context"}
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError("read.stream must declare every framing, partition and spool bound")
    for key, maximum in maxima.items():
        minimum = 0 if key == "max_records" else 1
        if type(spec[key]) is not int or not minimum <= spec[key] <= maximum:
            raise ValueError(f"read.stream {key} is outside its bounded range")
    if (read.get("format") != "json" or "container" in read
            or spec["container"] not in ("none", "zip")
            or not isinstance(spec["wrapper"], str) or not spec["wrapper"]
            or len(spec["wrapper"].encode()) > 128
            or type(spec["min_integer"]) is not int
            or not -(2**63) <= spec["min_integer"] <= 2**63 - 1
            or spec["record_encoding"] not in ("native", "python")):
        raise ValueError("read.stream requires JSON record projection and explicit framing policy")
    ordinal = spec["ordinal_context"]
    if ordinal is not None:
        declared = read.get("context", {}).get(ordinal) if isinstance(ordinal, str) else None
        if not isinstance(declared, dict) or declared.get("type") != "integer":
            raise ValueError("Stream ordinal_context must name a declared integer context")
    limits = read.get("limits", {})
    if (type(limits.get("max_bytes")) is not int
            or not 1 <= limits["max_bytes"] <= 32 * 1024**2
            or type(limits.get("max_records")) is not int
            or not 1 <= limits["max_records"] <= 100_000):
        raise ValueError("Record projection requires bounded read.limits")
    projection = copy.deepcopy(contract)
    del projection["read"]["stream"]
    return spec, source_engine.SourceEngine(projection)


def output(envelope, artifacts, documents, context_for, *, publish, max_index_bytes):
    manifest, contract, execution, inputs = documents
    spec, engine = _policy(contract)
    if execution["workers"] != 1:
        raise ValueError("Streamed source.read uses one worker to bound private spool storage")
    # A single private spool bounds disk across all inputs, including failures.
    # Published partitions contain no unvalidated prefix of a damaged archive.
    with tempfile.TemporaryFile(mode="w+b") as spool:
        staged, readings = [], []
        total_rows = 0
        for entry in inputs:
            ref, context, evidence = context_for(manifest, entry, artifacts)
            ordinal = spec["ordinal_context"]
            if ordinal is not None and ordinal in context:
                raise ValueError("Stream ordinal context is generated, never supplied by a caller")
            engine.validate_context({**context, **({ordinal: 1} if ordinal is not None else {})})
            parts, pending_count, first = [], 0, 0
            pending = {"version": 1, "tables": {name: [] for name in contract["read"]["tables"]}, "deferred": []}
            pending_size = len(_encode(pending))

            def flush():
                nonlocal pending, pending_count, pending_size
                if not pending_count:
                    return
                data = _encode(pending)
                if len(data) != pending_size:
                    raise ValueError("Projected partition size differs from incremental accounting")
                if len(data) > spec["partition_bytes"]:
                    raise ValueError("Projected record exceeds the partition byte bound")
                if len(staged) >= spec["max_partitions"] or spool.tell() + len(data) > spec["max_spool_bytes"]:
                    raise ValueError("Stream projection exceeds partition or private spool bound")
                offset = spool.tell()
                spool.write(data)
                sha = hashlib.sha256(data).hexdigest()
                receipt = {"uri": f"{envelope['output']}.parts/{sha}.json", "sha256": sha}
                parts.append({"receipt": receipt, "first_ordinal": first,
                              "record_count": pending_count, "bytes": len(data)})
                staged.append((offset, len(data), receipt))
                pending = {"version": 1, "tables": {name: [] for name in pending["tables"]}, "deferred": []}
                pending_count = 0
                pending_size = len(_encode(pending))

            def project(row, index):
                nonlocal pending_count, pending_size, first, total_rows
                values = {**context, **({ordinal: index + 1} if ordinal is not None else {})}
                result = engine.read(json.dumps(row, ensure_ascii=False, separators=(",", ":"),
                                                allow_nan=False).encode(), context=values)
                total_rows += sum(len(rows) for rows in result.tables.values()) + len(result.deferred)
                if total_rows > spec["max_output_rows"]:
                    raise ValueError("Stream projection exceeds output row bound")
                # Exact incremental array sizes avoid re-encoding every prefix.
                additions = [(pending["tables"][name], rows) for name, rows in result.tables.items()]
                additions.append((pending["deferred"], result.deferred))
                sizes = [sum(len(_encode(row)) for row in rows) for _, rows in additions]
                def extra_size():
                    return sum(size + (len(rows) if current else max(0, len(rows) - 1))
                               for (current, rows), size in zip(additions, sizes))
                if pending_count and (pending_count >= spec["partition_records"]
                                      or pending_size + extra_size() > spec["partition_bytes"]):
                    flush()
                    additions = [(pending["tables"][name], rows) for name, rows in result.tables.items()]
                    additions.append((pending["deferred"], result.deferred))
                size = pending_size + extra_size()
                if size > spec["partition_bytes"]:
                    raise ValueError("Projected record exceeds the partition byte bound")
                if not pending_count:
                    first = index + 1
                for current, rows in additions:
                    current.extend(rows)
                pending_size, pending_count = size, pending_count + 1

            with artifacts.verified_stream(ref, max_bytes=spec["max_input_bytes"]) as snapshot, ExitStack() as stack:
                stream = snapshot
                if spec["container"] == "zip":
                    archive = stack.enter_context(zipfile.ZipFile(snapshot))
                    members = archive.infolist()
                    if len(members) != 1 or members[0].is_dir() or members[0].flag_bits & 1:
                        raise ValueError("Stream ZIP requires exactly one unencrypted file")
                    if members[0].file_size > spec["max_bytes"]:
                        raise ValueError("Stream ZIP member exceeds expanded byte bound")
                    stream = stack.enter_context(archive.open(members[0]))
                scan = source_engine.stream_json_array(stream, wrapper=spec["wrapper"], on_record=project,
                    **{key: spec[key] for key in ("max_bytes", "max_record", "max_records", "max_depth",
                                                  "min_integer", "record_encoding")})
            flush()
            readings.append({"input": ref, **evidence, **scan, "partitions": parts})
        encoded = _encode({"version": 2, "contract": manifest["contract"], "artifacts": readings})
        if len(encoded) > max_index_bytes:
            raise ValueError("Streamed reading index exceeds verifier byte budget")
        # Every source reached EOF before the first externally visible write.
        for offset, size, receipt in staged:
            spool.seek(offset)
            data = spool.read(size)
            if publish:
                found = artifacts.put_bytes(receipt["uri"], data)
                if found != receipt:
                    raise ValueError("Written partition receipt differs from staged bytes")
            elif artifacts.verified(receipt, max_bytes=spec["partition_bytes"]) != data:
                raise ValueError("Written partition differs from independent configured projection")
        return encoded
