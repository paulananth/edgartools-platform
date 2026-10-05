"""Bounded native frame reading; the old GLEIF reader is an independent oracle."""
import io
import json
import math

import pytest

from edgar_warehouse.control_contract import digest
from edgar_warehouse.mdm.clean.gleif_source import _BoundedReader, _json_records
from edgar_warehouse.rules.source_engine import SourceRejected, stream_json_array
from scripts.qualification.audit_json_sequence import audit

LIMITS = {"max_bytes": 1024**2, "max_record": 4096, "max_records": 100, "max_depth": 64}


def test_finite_typed_numeric_and_frame_audit_matches_historical_reader():
    result = audit()
    assert result["cases"] == 2065
    assert result["difference_count"] == 0, result["differences"]


def test_exact_comparator_detects_a_deliberate_float_rounding_fault():
    value = -3.1163038337286385e203
    rows = [{"number": value}]
    result, parsed = native(json.dumps({"records": rows}).encode())
    assert digest([row for _, row in parsed]) == digest(rows)
    parsed[0][1]["number"] = math.nextafter(value, math.inf)
    assert digest([row for _, row in parsed]) != digest(rows)


def native(body, **changes):
    rows = []
    result = stream_json_array(io.BytesIO(body), wrapper="records", on_record=lambda row, n: rows.append((n, row)),
                               **{**LIMITS, **changes})
    return result, rows


def test_streaming_preserves_exact_types_order_and_eof_receipt():
    rows = [{"n": 2**63 - 1, "flag": True, "float": 1.25, "null": None, "array": [], "object": {}, "text": "é🦀"},
            {"n": -(2**63 - 1), "text": "9223372036854775808"}]
    body = json.dumps({"records": rows}, ensure_ascii=False).encode()
    result, found = native(body)
    assert result == {"record_count": 2, "expanded_bytes": len(body)}
    assert [n for n, _ in found] == [0, 1]
    assert digest([row for _, row in found]) == digest(rows)
    old = list(_json_records(_BoundedReader(io.BytesIO(body), LIMITS["max_bytes"], LIMITS["max_record"]), "records"))
    assert digest(old) == digest(rows)


def test_explicit_integer_minimum_matches_the_historical_decoder_boundary():
    body = b'{"records":[{"n":-9223372036854775808}]}'
    assert native(body)[1][0][1]["n"] == -(2**63)
    with pytest.raises(SourceRejected):
        native(body, min_integer=-(2**63 - 1))
    with pytest.raises(Exception):
        list(_json_records(_BoundedReader(io.BytesIO(body), LIMITS["max_bytes"], LIMITS["max_record"]), "records"))


@pytest.mark.parametrize("body", [b'{}', b'[]', b'{"other":[]}', b'{"records":{}}',
    b'{"records":[null]}', b'{"records":[[]]}', b'{"records":[{"a":1,"a":2}]}',
    b'{"records":[{"n":9223372036854775808}]}', b'{"records":[{"n":18446744073709551616}]}',
    b'{"records":[{"n":1e400}]}', b'{"records":[]} null', b'{"records":[{}]'])
def test_native_and_historical_frame_refusals(body):
    with pytest.raises(SourceRejected):
        native(body)
    with pytest.raises(Exception):
        list(_json_records(_BoundedReader(io.BytesIO(body), LIMITS["max_bytes"], LIMITS["max_record"]), "records"))


def test_oversized_record_is_refused_before_emission_or_full_read():
    stream = io.BytesIO(json.dumps({"records": [{"text": "x" * 200000}]}).encode())
    emitted = []
    with pytest.raises(SourceRejected, match="limit_exceeded"):
        stream_json_array(stream, wrapper="records", on_record=lambda row, n: emitted.append(row), **LIMITS)
    assert not emitted and stream.tell() < len(stream.getbuffer())


def test_whitespace_headroom_matches_historical_bounded_reader():
    body = b'{"records":[{' + b' ' * 1000 + b'}]}'
    result, rows = native(body, max_record=2)
    old = list(_json_records(_BoundedReader(io.BytesIO(body), LIMITS["max_bytes"], 2), "records"))
    assert [row for _, row in rows] == old == [{}]
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
