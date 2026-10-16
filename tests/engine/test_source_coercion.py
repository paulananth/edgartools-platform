"""Declared text coercion and invalid shapes, as the old filing loader read them."""
import json
import math
import random
import struct
from pathlib import Path

import pytest

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from tests.support.sec_rows import filing_row

CONTRACT = Path(__file__).parent / 'fixtures/filing-complete.yaml'
CONTEXT = {'cik': 320193, 'sync_run_id': 'qualification', 'raw_object_id': 'captured',
           'load_mode': 'default', 'recent_limit': None}


def filing(accession, form):
    return filing_row(accession, CONTEXT, form=form)


# A value that is not text reads as Python's `str` of it, nested containers too.
@pytest.mark.parametrize('value, text', [(True, 'True'), (False, 'False'), (1.0, '1.0'), ({'x': 1}, "{'x': 1}"),
    ([1, 2], '[1, 2]'), ({}, '{}'), ([], '[]'),
    ({'z': [None, True, "a'b", 'a"b', 'a\'"b'], 'a': -0.0}, "{'z': [None, True, \"a'b\", 'a\"b', 'a\\'\"b'], 'a': -0.0}"),
    ({'$': 'text', '@language': 'en', 'item': [1]}, "{'$': 'text', '@language': 'en', 'item': [1]}"),
    ('\x00\x0b\u2028\ue000🦀', '\x00\x0b\u2028\ue000🦀')])
def test_configured_text_coerces_scalars_and_nested_containers(value, text):
    payload = {'filings': {'recent': {'accessionNumber': ['a'], 'form': [value]}}}
    assert SourceEngine(files.load(CONTRACT)).read(json.dumps(payload).encode(), context=CONTEXT).tables['filings'] == [
        filing('a', text)]


# No filings object reads no rows; a text where a list belongs is read one character per row.
@pytest.mark.parametrize('payload, expected', [
    ({'filings': None}, []), ({'filings': []}, []), ({'filings': True}, []),
    ({'filings': {'recent': None}}, []), ({'filings': {'recent': []}}, []),
    ({'filings': {'recent': {'accessionNumber': ['a', 'b', 'c'], 'form': 'é🦀'}}},
     [filing('a', 'é'), filing('b', '🦀'), filing('c', None)]),
    ({'filings': {'recent': {'accessionNumber': 'ab', 'form': '45'}}}, [filing('a', '4'), filing('b', '5')]),
])
def test_declared_invalid_object_and_unicode_character_policies(payload, expected):
    assert SourceEngine(files.load(CONTRACT)).read(json.dumps(payload).encode(), context=CONTEXT).tables['filings'] == expected


@pytest.mark.parametrize('value', [None, True, 1, 1.0, {'x': 'y'}])
def test_invalid_non_sequence_anchor_remains_an_artifact_failure(value):
    payload = {'filings': {'recent': {'accessionNumber': value}}}
    with pytest.raises(SourceRejected, match='parallel_index' if isinstance(value, dict) else 'parallel_shape'):
        SourceEngine(files.load(CONTRACT)).read(json.dumps(payload).encode(), context=CONTEXT)


def test_native_json_text_matches_python_312_numbers_and_unicode_repr():
    rng = random.Random(20261004)
    values = [None, True, False, 0, -0.0, 2**53 + 1, 2**64, 1e16, 1e-5,
              math.nextafter(0.0, 1.0), float.fromhex('0x1.fffffffffffffp+1023')]
    for _ in range(10000):
        value = struct.unpack('!d', rng.getrandbits(64).to_bytes(8, 'big'))[0]
        if math.isfinite(value):
            values.append(value)
    for _ in range(1000):
        # Nested repr exercises printable Unicode categories and quote selection.
        text = ''.join(chr(rng.randrange(0x110000)) for _ in range(8))
        if not any(0xd800 <= ord(c) <= 0xdfff for c in text):
            values.append({'z': text, 'a': [text, True, None]})
    contract = {'read': {'format': 'json', 'tables': {'rows': {
        'each': 'values', 'columns': {'value': {'text': {'path': '.', 'trim': False, 'coerce': 'python'}}}}}}}
    # JSON-decoded values are the authority, rather than pre-serialization objects.
    data = json.dumps({'values': values}, ensure_ascii=False).encode()
    expected = [None if value is None else str(value) for value in json.loads(data)['values']]
    result = SourceEngine(contract).read(data).tables['rows']
    assert [row['value'] for row in result] == expected
