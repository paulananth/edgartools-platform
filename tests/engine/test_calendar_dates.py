"""Configuration must reproduce the loader's calendar conversion, not UTC instants."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected


# A filing date reads its first ten characters as an ISO date, as the old
# filing loader did (`date.fromisoformat(value[:10])`; a number is read as its
# text first); anything else is no date.
def calendar(value):
    from datetime import date
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


@pytest.mark.parametrize('value, expected', [
    (None, None), ('', None), ('2024-02-29', '2024-02-29'), ('2023-02-29', None),
    ('20240229', '2024-02-29'), ('2020-W01-1', '2019-12-30'), ('2020W011', '2019-12-30'),
    ('2020-W01', '2019-12-30'), ('2020W01', '2019-12-30'), ('0001-01-01', '0001-01-01'),
    ('9999-12-31', '9999-12-31'), ('0000-01-01', None), (' 2024-02-29', None),
    ('2024-02-29 ', '2024-02-29'), ('2024-02-29T12:00:00Z', '2024-02-29'),
    ('2024-02-29suffix', '2024-02-29'), ('🦀2024-02-29', None), ('2024-W54-1', None),
    ('garbage', None), (20240229, '2024-02-29'), ('20240229T00:00:00Z', '2024-02-29'),
    ('2020W011 suffix', '2019-12-30'), ('20240229🦀🦀', None)])
def test_configured_calendar_dates_read_the_first_ten_characters(value, expected):
    contract = files.load(Path(__file__).parent / 'fixtures' / 'filing-text-calendar.yaml')
    payload = {'filings': {'recent': {'accessionNumber': ['a'], 'filingDate': [value]}}}
    result = SourceEngine(contract).read(json.dumps(payload).encode())
    assert result.tables['filings'][0]['filing_date'] == expected
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


def test_adversarial_calendar_mutations_read_the_first_ten_characters():
    seeds = ['2024-02-29', '2023-02-29', '20240229', '2020-W01-1',
             '2020W011', '2020-W01', '2020W01', '9999-12-31', '0001-01-01']
    values = set(seeds)
    for seed in seeds:
        for index in range(len(seed)):
            for char in ' 019-Wa🦀':
                values.add(seed[:index] + char + seed[index + 1:])
        values.update(prefix + seed for prefix in (' ', '0', '🦀'))
        values.update(seed + suffix for suffix in ('T00:00:00Z', ' suffix', ' '))
    values = sorted(values)
    contract = {'read': {'format': 'json', 'tables': {'rows': {'each': 'rows',
        'columns': {'date': {'date': {'path': 'value', 'kind': 'calendar',
            'prefix_length': 10, 'on_invalid': None, 'basic_suffix': 'ignore'}}}}}}}
    rows = SourceEngine(contract).read(json.dumps({'rows': [{'value': v} for v in values]}).encode()).tables['rows']
    assert len(values) == 646
    for value, row in zip(values, rows, strict=True):
        assert row['date'] == calendar(value), value
