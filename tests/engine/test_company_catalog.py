"""Configured header-driven catalog evidence; retained parsing is an oracle."""
import json
from pathlib import Path
import pytest
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from tests.support.ticker_catalog_oracle import parse_rows
from scripts.qualification.qualify_company_main import require_tables

CONTRACT = files.load(Path('rules/sources/sec.submissions.company/catalog.yaml'))
CONTEXT = {'sync_run_id': 'catalog', 'source_name': 'company_tickers_exchange',
           'last_synced_at': '2026-10-05T00:00:00Z'}


def expected(payload):
    return [{**row, 'source_rank': rank, 'source_name': CONTEXT['source_name'],
             'last_sync_run_id': CONTEXT['sync_run_id'], 'last_synced_at': CONTEXT['last_synced_at']}
            for rank, row in enumerate(parse_rows(payload), 1)]


@pytest.mark.parametrize('payload', [
    {'fields': ['cik', 'ticker', 'exchange'], 'data': []},
    {'fields': ['cik', 'name', 'ticker', 'exchange'], 'data': [[1, 'A', 'A', 'NYSE'], [1, 'A', 'A-B', None]]},
    {'fields': ['exchange', 'ticker', 'cik'], 'data': [['', 'B', '2'], ['Nasdaq', 'A', 1]]},
    {'fields': ['cik', 'ticker'], 'data': [[1, 'A']]},
])
def test_header_catalog_matches_retained_rows_rank_and_context(payload):
    reading = SourceEngine(CONTRACT).read(json.dumps(payload).encode(), context=CONTEXT)
    assert reading.deferred == []
    require_tables(reading.tables['tickers'], expected(payload))


@pytest.mark.parametrize('payload', [
    {'fields': ['cik', 'ticker'], 'data': [[1, '']]},
    {'fields': ['cik', 'ticker'], 'data': [[None, 'A']]},
    {'fields': ['cik', 'ticker'], 'data': [['bad', 'A']]},
    {'fields': ['cik', 'ticker'], 'data': [[1]]},
    {'fields': ['cik', 'cik'], 'data': []},
    {'fields': ['cik', 'ticker', 'ticker'], 'data': [None, [1, 'first', 'last'], [2, 'A']]},
    {'b': {'cik_str': 1, 'ticker': None}, 'a': {'cik_str': 2}, 'z': None},
    {'fields': None, 'data': [], 'row': {'cik_str': 1, 'ticker': False}},
    None, [],
])
def test_legacy_accept_skip_and_refusal_decisions_are_preserved(payload):
    try:
        rows = expected(payload)
    except (TypeError, ValueError, OverflowError):
        with pytest.raises(SourceRejected):
            SourceEngine(CONTRACT).read(json.dumps(payload).encode(), context=CONTEXT)
    else:
        require_tables(SourceEngine(CONTRACT).read(json.dumps(payload).encode(), context=CONTEXT).tables['tickers'], rows)


@pytest.mark.parametrize('fault', ['rank', 'fallback', 'duplicates'])
def test_deliberate_faults_disprove_retained_equivalence(fault):
    import copy
    body = copy.deepcopy(CONTRACT)
    table = body['read']['tables']['tickers']
    payload = {'fields': ['cik', 'ticker'], 'data': [[1, ''], [2, 'A']]}
    if fault == 'rank':
        table['ordinal'] = 'source'
    elif fault == 'fallback':
        payload = {'fields': ['cik', 'cik_str', 'ticker'], 'data': [[0, 2, 'A']]}
        table['columns']['cik']['choose']['then']['choose']['condition']['test']['kind'] = 'not_null'
    else:
        payload = {'fields': ['cik', 'ticker', 'ticker'], 'data': [[1, 'first', 'last']]}
        table['each']['choose']['then']['matrix']['duplicates'] = 'reject'
    require_tables(SourceEngine(CONTRACT).read(json.dumps(payload).encode(), context=CONTEXT).tables['tickers'], expected(payload))
    with pytest.raises((ValueError, SourceRejected)):
        require_tables(SourceEngine(body).read(json.dumps(payload).encode(), context=CONTEXT).tables['tickers'], expected(payload))
