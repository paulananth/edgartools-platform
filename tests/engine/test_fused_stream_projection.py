"""Projection parity through the rebuilt native binding, without a loader."""
import io
import json
import math
import random
import struct

import pytest

from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from scripts.qualification.audit_json_sequence import ordered


def engine():
    return SourceEngine({"read":{"format":"json","limits":{"max_bytes":4096,"max_records":10},
        "context":{"index":{"type":"integer"}},"tables":{"rows":{"each":".","columns":{
            "evidence":{"value":{"path":"."}},"text":{"text":{"path":"nested","coerce":"python"}},
            "index":{"context":{"name":"index"}}}}}}})


def test_fused_projection_matches_roundtrip_for_exact_types_float_bits_and_python_text():
    rng = random.Random(43)
    values = [None, True, False, 0, -(2**63), 2**63-1, 9007199254740993, -0.0, 1e-5]
    while len(values) < 1009:
        value = struct.unpack('>d',rng.getrandbits(64).to_bytes(8,'big'))[0]
        if math.isfinite(value): values.append(value)
    rows = [{"z":value,"a":None,"nested":{"y":value,"b":[False,"é🦀"]}} for value in values]
    reader = engine()
    data = json.dumps({"records":rows},ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    actual=[]
    receipt=reader.stream_json_array(io.BytesIO(data),wrapper="records",on_reading=lambda row,n:actual.append(row),
        max_bytes=len(data),max_record=4096,max_records=len(rows),ordinal_context="index",record_encoding="python")
    expected=[reader.read(json.dumps(row,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),context={"index":n+1})
              for n,row in enumerate(rows)]
    assert receipt == {"record_count":len(rows),"expanded_bytes":len(data)}
    assert ordered([row.tables for row in actual]) == ordered([row.tables for row in expected])
    assert ordered([row.deferred for row in actual]) == ordered([row.deferred for row in expected])


@pytest.mark.parametrize('context',[{}, {'index':True}, {'index':1}])
def test_fused_empty_stream_does_not_bypass_generated_context(context):
    with pytest.raises(SourceRejected,match='invalid_context'):
        engine().stream_json_array(io.BytesIO(b'{"records":[]}'),wrapper="records",on_reading=lambda row,n:None,
            max_bytes=4096,max_record=4096,max_records=10,context=context,ordinal_context="index" if context else None)


@pytest.mark.parametrize('format,container',[('jsonl',None),('json','zip')])
def test_fused_empty_stream_refuses_an_incompatible_projection(format,container):
    read={"format":format,"tables":{"rows":{"columns":{}}}}
    if container:read['container']=container
    with pytest.raises(SourceRejected,match='contract'):
        SourceEngine({'read':read}).stream_json_array(io.BytesIO(b'{"records":[]}'),wrapper='records',
            on_reading=lambda row,n:None,max_bytes=4096,max_record=4096,max_records=10)
