"""Configuration must reproduce the loader's calendar conversion, not UTC instants."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from edgar_warehouse.loaders.common import parse_date
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected


@pytest.mark.parametrize('value', [None, '', '2024-02-29', '2023-02-29', '20240229',
    '2020-W01-1', '2020W011', '2020-W01', '2020W01', '0001-01-01', '9999-12-31',
    '0000-01-01', ' 2024-02-29', '2024-02-29 ', '2024-02-29T12:00:00Z',
    '2024-02-29suffix', '🦀2024-02-29', '2024-W54-1', 'garbage', 20240229, '20240229T00:00:00Z',
    '2020W011 suffix', '20240229🦀🦀'])
def test_configured_calendar_dates_match_old_loader(value):
    # The old filing loader calls safe_str before parse_date; numeric inputs
    # therefore become strings. Input scalar conversion remains the engine's.
    from edgar_warehouse.loaders.common import safe_str
    contract = files.load(Path(__file__).parent / 'fixtures' / 'filing-text-calendar.yaml')
    payload = {'filings': {'recent': {'accessionNumber': ['a'], 'filingDate': [value]}}}
    result = SourceEngine(contract).read(json.dumps(payload).encode())
    expected = parse_date(safe_str([value], 0))
    assert result.tables['filings'][0]['filing_date'] == (expected.isoformat() if expected else None)
    assert not result.deferred


def test_default_instant_dates_keep_timezone_and_reject_calendar_input():
    contract = {'read': {'format': 'json', 'tables': {'rows': {'each': '.',
        'columns': {'at': {'date': {'path': 'at'}}}}}}}
    engine = SourceEngine(contract)
    assert engine.read(b'{"at":"2024-02-29T01:02:03-05:00"}').tables['rows'][0]['at'] == '2024-02-29T06:02:03+00:00'
    with pytest.raises(SourceRejected, match='invalid_value'):
        engine.read(b'{"at":"2024-02-29"}')


def test_calendar_reading_survives_immutable_worker_and_independent_reparse(tmp_path):
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.workers import source_read

    store = Artifacts()
    fixture = Path(__file__).parent / 'fixtures' / 'filing-text-calendar.yaml'
    contract = store.put_bytes((tmp_path / 'contract.yaml').as_uri(), fixture.read_bytes())
    data = store.put_bytes((tmp_path / 'capture.json').as_uri(), json.dumps({'filings': {'recent': {
        'accessionNumber': ['a', 'b'], 'filingDate': ['2024-02-29T00:00:00Z', '2023-02-29'],
        'reportDate': ['2020-W01-1']}}}).encode())
    manifest = store.put(tmp_path.as_uri(), {'version': 1, 'contract': contract, 'artifacts': [data]})
    envelope = {'input': manifest, 'output': (tmp_path / 'reading.json').as_uri(), 'checks': ['source.output']}
    candidate = source_read.execute(envelope, store)
    assert source_read.verify({**envelope, 'candidate': candidate}, store) == ({'source.output': True}, [])
    rows = store.json(candidate)['artifacts'][0]['tables']['filings']
    assert [(row['filing_date'], row['report_date']) for row in rows] == [
        ('2024-02-29', '2019-12-30'), (None, None)]
