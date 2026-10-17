"""Bounded native frame reading: each record exactly as Python's `json` reads it, or a refusal."""
import io
import json
import math
import random
import struct

import pytest

from edgar_warehouse.control_contract import canonical, digest
from edgar_warehouse.rules.source_engine import SourceRejected, stream_json_array
from tests.support.exact import ordered

LIMITS = {"max_bytes": 1024**2, "max_record": 4096, "max_records": 100, "max_depth": 64}


# The bodies the reader refuses: no wrapper object or list, a record that is not
# an object, a repeated key, other or repeated top-level members, trailing or
# missing data, and integers outside the signed 64-bit range (its minimum here
# is -(2**63 - 1)) or numbers past a double.
REFUSED = [b'{}', b'[]', b'{"wrong":[]}', b'{"records":{}}', b'{"records":[null]}',
           b'{"records":[[]]}', b'{"records":[{"a":1,"a":2}]}',
           b'{"records":[{"x":{"a":1,"a":2}}]}', b'{"records":[],"extra":0}',
           b'{"records":[],"records":[]}', b'{"records":[]} null', b'{"records":[{}]',
           b'{"records":[{"n":-9223372036854775808}]}',
           b'{"records":[{"n":9223372036854775808}]}',
           b'{"records":[{"n":18446744073709551616}]}',
           b'{"records":[{"n":1e400}]}']


def cases():
    yield "records", b'{"records":[{"z":1,"a":2,"nested":{"y":3,"b":4}}]}'
    values = [None, False, True, 0, 1, -(2**63 - 1), 2**63 - 1, 1.25, -0.0,
              "", "é🦀", [], {}, [1, {"n": True}], {"null": None}]
    for wrapper in ("records", "relations", "exceptions"):
        for value in values:
            yield wrapper, json.dumps({wrapper: [{"value": value}]}, ensure_ascii=False).encode()
        yield wrapper, json.dumps({wrapper: [{"x": 1}, {"x": 2}]}).encode()
        yield wrapper, json.dumps({wrapper: []}).encode()
    for data in REFUSED:
        yield "records", data
    rng = random.Random(1105)
    for _ in range(2000):
        value = struct.unpack(">d", rng.getrandbits(64).to_bytes(8, "big"))[0]
        if math.isfinite(value):
            yield "records", json.dumps({"records": [{"value": value}]}).encode()


def read(body, wrapper, **changes):
    rows = []
    receipt = stream_json_array(io.BytesIO(body), wrapper=wrapper, on_record=lambda row, n: rows.append(row),
                                **{"max_bytes": 1024**2, "max_record": 65536, "max_records": 100,
                                   "min_integer": -(2**63 - 1), **changes})
    assert receipt == {"record_count": len(rows), "expanded_bytes": len(body)}
    return rows


def test_finite_typed_numeric_and_frame_cases():
    total = 0
    for wrapper, body in cases():
        total += 1
        if body in REFUSED:
            with pytest.raises(SourceRejected):
                read(body, wrapper)
        else:
            assert digest(ordered(read(body, wrapper))) == digest(ordered(json.loads(body)[wrapper])), body
    assert total == 2066


def test_exact_comparator_detects_a_deliberate_float_rounding_fault():
    value = -3.1163038337286385e203
    rows = [{"number": value}]
    result, parsed = native(json.dumps({"records": rows}).encode())
    assert digest([row for _, row in parsed]) == digest(rows)
    parsed[0][1]["number"] = math.nextafter(value, math.inf)
    assert digest([row for _, row in parsed]) != digest(rows)


def test_python_encoded_size_boundaries():
    """A record is accepted exactly when its Python-encoded size is within the limit."""
    total = 0
    for wrapper, body in cases():
        if body in REFUSED or not (rows := json.loads(body)[wrapper]):
            continue
        size = max(len(canonical(row).encode()) for row in rows)
        for limit in (size - 1, size, size + 1):
            total += 1
            if limit < size:
                with pytest.raises(SourceRejected):
                    read(body, wrapper, max_record=limit, record_encoding="python")
            else:
                found = read(body, wrapper, max_record=limit, record_encoding="python")
                assert digest(ordered(found)) == digest(ordered(rows)), body
    assert total == 6141


def test_encoded_size_policy_is_explicit_and_rejects_unknown_policy():
    body = b'{"records":[{"v":0.00001}]}'
    assert native(body, max_record=11, record_encoding="python")[1][0][1] == {"v": 1e-5}
    with pytest.raises(SourceRejected):
        native(body, max_record=11)
    with pytest.raises(SourceRejected, match="contract"):
        native(body, record_encoding="unknown")


def native(body, **changes):
    rows = []
    result = stream_json_array(io.BytesIO(body), wrapper="records", on_record=lambda row, n: rows.append((n, row)),
                               **{**LIMITS, **changes})
    return result, rows


def test_nested_captured_key_order_survives_and_comparator_detects_sorting_fault():
    expected = [{"z": 1, "a": 2, "nested": {"y": 3, "b": 4}, "array": [{"q": 1, "c": 2}]}]
    _, rows = native(json.dumps({"records": expected}).encode())
    actual = [row for _, row in rows]
    assert ordered(actual) == ordered(expected)
    faulty = json.loads(json.dumps(actual, sort_keys=True))
    assert digest(faulty) == digest(expected)
    assert ordered(faulty) != ordered(expected)


def test_streaming_preserves_exact_types_order_and_eof_receipt():
    rows = [{"n": 2**63 - 1, "flag": True, "float": 1.25, "null": None, "array": [], "object": {}, "text": "é🦀"},
            {"n": -(2**63 - 1), "text": "9223372036854775808"}]
    body = json.dumps({"records": rows}, ensure_ascii=False).encode()
    result, found = native(body)
    assert result == {"record_count": 2, "expanded_bytes": len(body)}
    assert [n for n, _ in found] == [0, 1]
    assert digest([row for _, row in found]) == digest(rows)


def test_explicit_integer_minimum():
    body = b'{"records":[{"n":-9223372036854775808}]}'
    assert native(body)[1][0][1]["n"] == -(2**63)
    with pytest.raises(SourceRejected):
        native(body, min_integer=-(2**63 - 1))


@pytest.mark.parametrize("body", [b'{}', b'[]', b'{"other":[]}', b'{"records":{}}',
    b'{"records":[null]}', b'{"records":[[]]}', b'{"records":[{"a":1,"a":2}]}',
    b'{"records":[{"n":9223372036854775808}]}', b'{"records":[{"n":18446744073709551616}]}',
    b'{"records":[{"n":1e400}]}', b'{"records":[]} null', b'{"records":[{}]'])
def test_native_frame_refusals(body):
    with pytest.raises(SourceRejected):
        native(body)


def test_oversized_record_is_refused_before_emission_or_full_read():
    stream = io.BytesIO(json.dumps({"records": [{"text": "x" * 200000}]}).encode())
    emitted = []
    with pytest.raises(SourceRejected, match="limit_exceeded"):
        stream_json_array(stream, wrapper="records", on_record=lambda row, n: emitted.append(row), **LIMITS)
    assert not emitted and stream.tell() < len(stream.getbuffer())


def test_whitespace_headroom_within_a_record():
    body = b'{"records":[{' + b' ' * 1000 + b'}]}'
    result, rows = native(body, max_record=2)
    assert [row for _, row in rows] == [{}]
    assert result["expanded_bytes"] == len(body)
    large = b'{"records":[{' + b' ' * 200000 + b'}]}'
    with pytest.raises(SourceRejected):
        native(large, max_record=2)


def test_callback_refusal_stops_stream_and_cannot_return_an_eof_receipt():
    def refuse(row, n):
        raise ValueError("candidate refused")
    with pytest.raises(SourceRejected, match="stream_consumer"):
        stream_json_array(io.BytesIO(b'{"records":[{},{}]}'), wrapper="records", on_record=refuse, **LIMITS)


@pytest.mark.parametrize("changes", [{"max_depth": 0}, {"max_bytes": False}, {"max_records": -1}, {"max_record": 0}])
def test_invalid_bounds_are_refused_before_emitting_rows(changes):
    with pytest.raises(SourceRejected, match="contract"):
        native(b'{"records":[{}]}', **changes)


def test_a_bare_array_streams_when_no_wrapper_is_declared():
    """Ticket 104: a document that is itself the array, one record per element."""
    rows = []
    body = b'[{"data":[{"figi":"F1"}]},{"warning":"none"}]'
    result = stream_json_array(io.BytesIO(body), wrapper=None, on_record=lambda row, n: rows.append((n, row)), **LIMITS)
    assert result == {"record_count": 2, "expanded_bytes": len(body)}
    assert rows == [(0, {"data": [{"figi": "F1"}]}), (1, {"warning": "none"})]
    for refused in (b'{"records":[]}', b'[null]', b'[] null'):
        with pytest.raises(SourceRejected):
            stream_json_array(io.BytesIO(refused), wrapper=None, on_record=lambda row, n: None, **LIMITS)
    with pytest.raises(SourceRejected, match="wrapper"):
        stream_json_array(io.BytesIO(body), wrapper="", on_record=lambda row, n: None, **LIMITS)
