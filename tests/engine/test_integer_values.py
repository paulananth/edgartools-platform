"""Scalar, lexical and aligned-record integers: Python's own integer reading, kept from the old loader."""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from edgar_warehouse.control_contract import digest
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected


VALUES = [None, '', 0, 1, -1, 0.9, -0.9, 1.9, -1.9, 9007199254740993,
    9223372036854775807, -9223372036854775808, True, False, '1.9', '1e2',
    '１_٢', '𝟘𝟘𝟜', '٠٠١', '+001', '-0', ' 1 ', '\u00a0+١\u00a0',
    '1_000', '_1', '1_', '1__2', '²', 'Ⅳ', 'bad', [], {}, '\x1c1', '0x10']


def integer(value):
    """An integer as the old loader read one: Python's `int`, else none."""
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def contract():
    return {'read': {'format': 'json', 'tables': {'rows': {'each': 'rows', 'columns': {
        'integer': {'integer': {'path': 'value', 'on_invalid': None}},
        'flag': {'integer': {'path': 'value', 'as': 'boolean', 'default': False, 'on_invalid': 'default'}}}}}}}


@pytest.mark.parametrize('value', VALUES)
def test_integer_and_boolean_output_match_loader_without_float_roundtrip(value):
    reading = SourceEngine(contract()).read(json.dumps({'rows': [{'value': value}]}).encode())
    expected = integer(value)
    row = reading.tables['rows'][0]
    assert row['integer'] == expected
    assert type(row['integer']) == type(expected)
    assert row['flag'] is bool(expected)
    assert not reading.deferred


def test_every_python_312_decimal_digit_and_adjacent_numerals():
    assert unicodedata.unidata_version == '15.0.0'
    decimal = [chr(i) for i in range(0x110000) if unicodedata.category(chr(i)) == 'Nd']
    values = decimal + [chr(ord(c) + delta) for c in decimal for delta in (-1, 1)]
    rows = SourceEngine(contract()).read(json.dumps({'rows': [{'value': v} for v in values]}).encode()).tables['rows']
    for value, row in zip(values, rows, strict=True):
        expected = integer(value)
        assert row['integer'] == expected, repr(value)
        assert row['flag'] is bool(expected), repr(value)


def test_signed_overflow_never_saturates_and_boolean_output_is_not_i64_limited():
    for value in [9223372036854775808, -9223372036854775809, 1e300]:
        with pytest.raises(SourceRejected) as error:
            SourceEngine(contract()).read(json.dumps({'rows': [{'value': value}]}).encode())
        assert error.value.code == 'integer_overflow'
    c = contract()
    del c['read']['tables']['rows']['columns']['integer']
    for value in [9223372036854775808, 1e300, '9' * 4300, '9' * 4301]:
        row = SourceEngine(c).read(json.dumps({'rows': [{'value': value}]}).encode()).tables['rows'][0]
        assert row['flag'] is bool(integer(value))


def test_existing_number_text_and_custom_boolean_return_behavior_stays_unchanged(monkeypatch):
    c = {'read': {'format': 'json', 'tables': {'rows': {'each': '.', 'columns': {
        'text': {'text': {'path': 'value'}}, 'number': {'number': {'path': 'value'}},
        'constant': {'const': {'value': True}}}}}}}
    assert SourceEngine(c).read(b'{"value":true}').tables['rows'][0] == {
        'text': 'true', 'number': None, 'constant': 'true'}
    from edgar_warehouse.rules.steps import STEPS
    monkeypatch.setitem(STEPS, 'test_boolean@1', lambda value: bool(value))
    c['read']['tables']['rows']['columns']['constant'] = {'custom': {
        'step': 'test_boolean@1', 'inputs': {'value': {'integer': {'path': 'value', 'as': 'boolean'}}}}}
    assert SourceEngine(c).read(b'{"value":true}').tables['rows'][0] == {
        'text': 'true', 'number': None, 'constant': 'true'}


def test_complete_filing_content_worker_and_verifier_without_source_loader(tmp_path):
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.workers import source_read
    fixture = Path(__file__).parent / 'fixtures' / 'filing-content.yaml'
    payload = {'filings': {'recent': {'accessionNumber': ['a', 'b'], 'size': [9007199254740993],
        'isXBRL': [0.9, True], 'isInlineXBRL': ['bad'], 'filingDate': ['2024-02-29T00:00:00Z']}}}
    store = Artifacts()
    ref = store.put_bytes((tmp_path / 'contract.yaml').as_uri(), fixture.read_bytes())
    data = store.put_bytes((tmp_path / 'capture.json').as_uri(), json.dumps(payload).encode())
    manifest = store.put(tmp_path.as_uri(), {'version': 1, 'contract': ref, 'artifacts': [data]})
    envelope = {'input': manifest, 'output': (tmp_path / 'reading.json').as_uri(), 'checks': ['source.output']}
    candidate = source_read.execute(envelope, store)
    assert source_read.verify({**envelope, 'candidate': candidate}, store) == ({'source.output': True}, [])
    empty = dict.fromkeys(files.load(fixture)['read']['tables']['filings']['columns'])
    # Exactly, types too: `==` would take a flag read as 1 for True.
    assert digest(store.json(candidate)['artifacts'][0]['tables']['filings']) == digest([
        {**empty, 'accession_number': 'a', 'filing_date': '2024-02-29', 'size': 9007199254740993,
         'is_xbrl': False, 'is_inline_xbrl': False},
        {**empty, 'accession_number': 'b', 'is_xbrl': True, 'is_inline_xbrl': False}])


@pytest.mark.parametrize('raw', ['-0', '1e2', '-9223372036854775809', '0.9999999999999999', '1.9999999999999998'])
def test_exact_json_numeric_reading_keeps_existing_text_and_number_outputs(raw):
    old = {'read': {'format': 'json', 'tables': {'rows': {'each': '.', 'columns': {
        'text': {'text': {'path': 'value'}}, 'number': {'number': {'path': 'value'}}}}}}}
    data = ('{"value":' + raw + '}').encode()
    expected = SourceEngine(old).read(data).tables['rows'][0]
    old['read']['tables']['rows']['columns']['exact'] = {'integer': {'path': 'value', 'on_overflow': None}}
    row = SourceEngine(old).read(data).tables['rows'][0]
    assert {key: row[key] for key in expected} == expected
    parsed = json.loads(data)['value']
    value = int(parsed)
    assert row['exact'] == (value if -2**63 <= value < 2**63 else None)
