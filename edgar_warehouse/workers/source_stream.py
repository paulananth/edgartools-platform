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
from . import source_readings


def _encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True, allow_nan=False).encode()


def _policy(contract):
    read = contract["read"]
    spec = read["stream"]
    maxima = {"max_input_bytes": 1024**3, "max_bytes": 16 * 1024**3,
              "max_record": 32 * 1024**2, "max_records": 10_000_000,
              "max_depth": 64, "partition_bytes": 8 * 1024**2,
              "partition_records": 100_000, "max_partitions": 4096,
              "max_spool_bytes": 1024**3, "max_output_rows": 10_000_000}
    framing = spec.get("framing", "json_array") if isinstance(spec, dict) else None
    if framing not in ("json_array", "xml_records"):
        raise ValueError("Unknown configured stream framing")
    required = {*maxima, "container", "ordinal_context"}
    required |= ({"wrapper", "min_integer", "record_encoding"} if framing == "json_array"
                 else {"framing", "xml", "header_read"})
    if (not isinstance(spec, dict) or not required <= set(spec)
            or set(spec) - required - {"expected_records_context", "framing"} -
                ({"max_header"} if framing == "xml_records" else set())):
        raise ValueError("read.stream must declare every framing, partition and spool bound")
    for key, maximum in maxima.items():
        minimum = 0 if key == "max_records" else 1
        if type(spec[key]) is not int or not minimum <= spec[key] <= maximum:
            raise ValueError(f"read.stream {key} is outside its bounded range")
    if (read.get("format") != "json" or "container" in read
            or spec["container"] not in ("none", "zip")):
        raise ValueError("read.stream requires JSON record projection and explicit framing policy")
    if framing == "json_array" and (not isinstance(spec["wrapper"], str) or not spec["wrapper"]
            or len(spec["wrapper"].encode()) > 128
            or type(spec["min_integer"]) is not int
            or not -(2**63) <= spec["min_integer"] <= 2**63 - 1
            or spec["record_encoding"] not in ("native", "python")):
        raise ValueError("JSON array stream requires explicit numeric and wrapper policy")
    header_engine = None
    if framing == "xml_records":
        if "max_header" in spec and (type(spec["max_header"]) is not int
                or not 1 <= spec["max_header"] <= 32 * 1024**2):
            raise ValueError("read.stream max_header is outside its bounded range")
        xml = spec.get("xml")
        fields = {"namespace", "root", "header", "container", "record", "record_wrapper"}
        if (not isinstance(xml, dict) or set(xml) != fields
                or any(not isinstance(xml[name], str) or not 1 <= len(xml[name].encode()) <= 512
                       for name in fields - {"record_wrapper"})
                or (xml["record_wrapper"] is not None and
                    (not isinstance(xml["record_wrapper"], str) or not 1 <= len(xml["record_wrapper"].encode()) <= 128))):
            raise ValueError("XML stream requires a bounded explicit envelope")
        header_read = spec.get("header_read")
        if (not isinstance(header_read, dict) or header_read.get("format") != "json"
                or "container" in header_read or "stream" in header_read
                or header_read.get("context", {}) != read.get("context", {})):
            raise ValueError("XML header uses configured JSON assertions with the same context")
        header_engine = source_engine.SourceEngine({"read": header_read})
    elif "xml" in spec or "header_read" in spec:
        raise ValueError("XML envelope/header policy requires XML framing")
    ordinal = spec["ordinal_context"]
    if ordinal is not None:
        declared = read.get("context", {}).get(ordinal) if isinstance(ordinal, str) else None
        if not isinstance(declared, dict) or declared.get("type") != "integer":
            raise ValueError("Stream ordinal_context must name a declared integer context")
    expected = spec.get("expected_records_context")
    if "expected_records_context" in spec:
        declared = read.get("context", {}).get(expected) if isinstance(expected, str) else None
        if not isinstance(declared, dict) or declared.get("type") != "integer":
            raise ValueError("Stream expected_records_context must name a declared integer context")
    limits = read.get("limits", {})
    if (type(limits.get("max_bytes")) is not int
            or not 1 <= limits["max_bytes"] <= 32 * 1024**2
            or type(limits.get("max_records")) is not int
            or not 1 <= limits["max_records"] <= 100_000):
        raise ValueError("Record projection requires bounded read.limits")
    projection = copy.deepcopy(contract)
    del projection["read"]["stream"]
    engine = source_engine.SourceEngine(projection)
    source_readings.table_names(list(read["tables"]))
    return spec, engine, header_engine


def output(envelope, artifacts, documents, context_for, lookup_for, *, publish, max_index_bytes):
    manifest, contract, execution, inputs = documents
    spec, engine, header_engine = _policy(contract)
    if execution["workers"] != 1:
        raise ValueError("Streamed source.read uses one worker to bound private spool storage")
    # A single private spool bounds disk across all inputs, including failures.
    # Published partitions contain no unvalidated prefix of a damaged archive.
    with tempfile.TemporaryFile(mode="w+b") as spool:
        staged, readings = [], []
        total_rows = 0
        for entry in inputs:
            ref, context, evidence = context_for(manifest, entry, artifacts)
            lookups, lookup_evidence = lookup_for(manifest, entry, artifacts, contract)
            evidence.update(lookup_evidence)
            if header_engine is not None and contract["read"].get("lookup_sets"):
                raise ValueError("Indexed stream lookup receipts currently require JSON framing")
            ordinal = spec["ordinal_context"]
            if ordinal is not None and ordinal in context:
                raise ValueError("Stream ordinal context is generated, never supplied by a caller")
            engine.validate_context({**context, **({ordinal: 1} if ordinal is not None else {})})
            expected_name = spec.get("expected_records_context")
            expected_count = context.get(expected_name) if expected_name is not None else None
            if expected_name is not None and (type(expected_count) is not int
                    or not 0 <= expected_count <= spec["max_records"]):
                raise ValueError("Stream expected record count is outside its declared bound")
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

            def project(result, index):
                nonlocal pending_count, pending_size, first, total_rows
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
                if header_engine is None:
                    scan = engine.stream_json_array(stream, wrapper=spec["wrapper"], on_reading=project,
                        context=context, ordinal_context=ordinal, lookups=lookups,
                        **{key: spec[key] for key in ("max_bytes", "max_record", "max_records", "max_depth",
                                                      "min_integer", "record_encoding")})
                else:
                    scan = engine.stream_xml_records(stream, envelope=spec["xml"], header_engine=header_engine,
                        on_reading=project, context=context, ordinal_context=ordinal,
                        max_header=spec.get("max_header"),
                        **{key: spec[key] for key in ("max_bytes", "max_record", "max_records", "max_depth")})
                if expected_count is not None and scan["record_count"] != expected_count:
                    raise ValueError("Stream record count differs from pinned context")
                if spec["container"] == "zip" and scan["expanded_bytes"] != members[0].file_size:
                    raise ValueError("Stream ZIP expanded length differs from declared member size")
            flush()
            readings.append({"input": ref, **evidence, **scan,
                             "table_names": list(contract["read"]["tables"]), "partitions": parts})
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
