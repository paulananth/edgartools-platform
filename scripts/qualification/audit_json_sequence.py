"""Finite typed/refusal parity of native framing against historical GLEIF JSON."""
from __future__ import annotations

import argparse
import io
import json
import math
import random
import struct
from pathlib import Path

from edgar_warehouse.control_contract import canonical, digest
from edgar_warehouse.mdm.clean.gleif_source import _BoundedReader, _json_records
from edgar_warehouse.rules.source_engine import stream_json_array


def cases():
    yield "records", b'{"records":[{"z":1,"a":2,"nested":{"y":3,"b":4}}]}'
    values = [None, False, True, 0, 1, -(2**63 - 1), 2**63 - 1, 1.25, -0.0,
              "", "é🦀", [], {}, [1, {"n": True}], {"null": None}]
    for wrapper in ("records", "relations", "exceptions"):
        for value in values:
            yield wrapper, json.dumps({wrapper: [{"value": value}]}, ensure_ascii=False).encode()
        yield wrapper, json.dumps({wrapper: [{"x": 1}, {"x": 2}]}).encode()
        yield wrapper, json.dumps({wrapper: []}).encode()
    for data in [b'{}', b'[]', b'{"wrong":[]}', b'{"records":{}}', b'{"records":[null]}',
                 b'{"records":[[]]}', b'{"records":[{"a":1,"a":2}]}',
                 b'{"records":[{"x":{"a":1,"a":2}}]}', b'{"records":[],"extra":0}',
                 b'{"records":[],"records":[]}', b'{"records":[]} null', b'{"records":[{}]',
                 b'{"records":[{"n":-9223372036854775808}]}',
                 b'{"records":[{"n":9223372036854775808}]}',
                 b'{"records":[{"n":18446744073709551616}]}',
                 b'{"records":[{"n":1e400}]}']:
        yield "records", data
    rng = random.Random(1105)
    for _ in range(2000):
        value = struct.unpack(">d", rng.getrandbits(64).to_bytes(8, "big"))[0]
        if math.isfinite(value):
            yield "records", json.dumps({"records": [{"value": value}]}).encode()


def outcome(call):
    try:
        return {"rows": call()}
    except Exception as error:
        return {"refused": type(error).__name__}


def ordered(value):
    """Type and captured key order, including objects nested in arrays."""
    if isinstance(value, dict):
        return ["object", [[key, ordered(item)] for key, item in value.items()]]
    if isinstance(value, list):
        return ["array", [ordered(item) for item in value]]
    return [type(value).__name__, value]


def audit():
    differences = []
    total = accepted = refused = 0
    for wrapper, body in cases():
        total += 1
        old = outcome(lambda: list(_json_records(_BoundedReader(io.BytesIO(body), 1024**2, 65536), wrapper)))
        def read():
            rows = []
            receipt = stream_json_array(io.BytesIO(body), wrapper=wrapper,
                on_record=lambda row, n: rows.append(row), max_bytes=1024**2,
                max_record=65536, max_records=100, min_integer=-(2**63 - 1))
            if receipt != {"record_count": len(rows), "expanded_bytes": len(body)}:
                raise ValueError("EOF receipt differs")
            return rows
        new = outcome(read)
        accepted += "rows" in old
        refused += "refused" in old
        match = ("refused" in old and "refused" in new) or (
            "rows" in old and "rows" in new and digest(ordered(old["rows"])) == digest(ordered(new["rows"])))
        if not match:
            differences.append({"wrapper": wrapper, "body": body.decode(), "old": old, "new": new})
    return {"cases": total, "accepted": accepted, "refused": refused,
            "difference_count": len(differences), "differences": differences,
            "comparison": "typed rows, recursive captured key order and refusal decisions; exception identities excluded",
            "integer_minimum": -(2**63 - 1), "universal_equivalence": False,
            "full_archive_qualification": False, "sec_requests": 0}


def audit_record_bounds():
    """Compare limits just below, at and above Python's encoded record size."""
    differences, total = [], 0
    for wrapper, body in cases():
        try:
            rows = list(_json_records(_BoundedReader(io.BytesIO(body), 1024**2, 65536), wrapper))
        except Exception:
            continue
        if not rows:
            continue
        size = max(len(canonical(row).encode()) for row in rows)
        for limit in (size - 1, size, size + 1):
            total += 1
            parsed = []
            try:
                stream_json_array(io.BytesIO(body), wrapper=wrapper,
                    on_record=lambda row, n: parsed.append(row), max_bytes=1024**2,
                    max_record=limit, max_records=100, min_integer=-(2**63 - 1), record_encoding="python")
                accepted = True
            except Exception:
                accepted = False
            if accepted != (limit >= size) or (accepted and digest(ordered(parsed)) != digest(ordered(rows))):
                differences.append({"body": body.decode(), "limit": limit, "encoded_bytes": size, "accepted": accepted})
    return {"cases": total, "difference_count": len(differences), "differences": differences,
            "record_encoding": "python", "comparison": "typed rows, recursive captured-key order and encoded-size boundary acceptance",
            "universal_equivalence": False, "full_archive_qualification": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit()
    report["record_bounds"] = audit_record_bounds()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "differences"}))


if __name__ == "__main__":
    main()
