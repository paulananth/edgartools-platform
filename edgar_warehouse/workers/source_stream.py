"""Configured record projection; private partitions until every input reaches EOF.

The stream declares framing and resource bounds. All field interpretation stays
in the ordinary source contract. No source-specific loader is called here.
"""
from __future__ import annotations

import hashlib
import json
import tempfile

from .source_traversal import Traversal


def _encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True, allow_nan=False).encode()


def output(envelope, artifacts, documents, context_for, lookup_for, *, publish, max_index_bytes):
    manifest, contract, execution, inputs = documents
    traversal = Traversal(contract, archive_policy="configured")
    spec = traversal.spec
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
            traversal.validate_context(context)
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

            with artifacts.verified_stream(ref, max_bytes=spec["max_input_bytes"]) as snapshot:
                scan = traversal.scan(snapshot, context=context, lookups=lookups, on_reading=project)
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
