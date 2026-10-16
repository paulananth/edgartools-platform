"""Configured header-driven catalog evidence: rows, rank and refusals, as the old ticker parser read them."""
import json
from pathlib import Path
import pytest
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from tests.support.exact import require_tables

CONTRACT = files.load(Path('rules/sources/sec.submissions.company/catalog.yaml'))
CONTEXT = {'sync_run_id': 'catalog', 'source_name': 'company_tickers_exchange',
           'last_synced_at': '2026-10-05T00:00:00Z'}


def expected(rows):
    """(cik, ticker, exchange) per row, in the catalog's order, with its rank and the capture's facts."""
    return [{'cik': cik, 'ticker': ticker, 'exchange': exchange, 'source_rank': rank,
             'source_name': CONTEXT['source_name'], 'last_sync_run_id': CONTEXT['sync_run_id'],
             'last_synced_at': CONTEXT['last_synced_at']}
            for rank, (cik, ticker, exchange) in enumerate(rows, 1)]


@pytest.mark.parametrize('payload, rows', [
    ({'fields': ['cik', 'ticker', 'exchange'], 'data': []}, []),
    ({'fields': ['cik', 'name', 'ticker', 'exchange'], 'data': [[1, 'A', 'A', 'NYSE'], [1, 'A', 'A-B', None]]},
     [(1, 'A', 'NYSE'), (1, 'A-B', None)]),
    ({'fields': ['exchange', 'ticker', 'cik'], 'data': [['', 'B', '2'], ['Nasdaq', 'A', 1]]},
     [(2, 'B', None), (1, 'A', 'Nasdaq')]),
    ({'fields': ['cik', 'ticker'], 'data': [[1, 'A']]}, [(1, 'A', None)]),
])
def test_header_catalog_rows_rank_and_context(payload, rows):
    reading = SourceEngine(CONTRACT).read(json.dumps(payload).encode(), context=CONTEXT)
    assert reading.deferred == []
    require_tables(reading.tables['tickers'], expected(rows))


# A row with no CIK or ticker is skipped; a CIK that is not a number refuses
# the catalog; the keyed form takes each entry's `cik_str`, its ticker as text.
@pytest.mark.parametrize('payload, rows', [
    ({'fields': ['cik', 'ticker'], 'data': [[1, '']]}, []),
    ({'fields': ['cik', 'ticker'], 'data': [[None, 'A']]}, []),
    ({'fields': ['cik', 'ticker'], 'data': [[1]]}, []),
    ({'fields': ['cik', 'cik'], 'data': []}, []),
    ({'fields': ['cik', 'ticker', 'ticker'], 'data': [None, [1, 'first', 'last'], [2, 'A']]},
     [(1, 'last', None), (2, 'A', None)]),
    ({'b': {'cik_str': 1, 'ticker': None}, 'a': {'cik_str': 2}, 'z': None}, [(1, 'None', None), (2, '', None)]),
    ({'fields': None, 'data': [], 'row': {'cik_str': 1, 'ticker': False}}, [(1, 'False', None)]),
    (None, []), ([], []),
])
def test_accept_and_skip_decisions(payload, rows):
    require_tables(SourceEngine(CONTRACT).read(json.dumps(payload).encode(), context=CONTEXT).tables['tickers'],
                   expected(rows))


def test_a_cik_that_is_not_a_number_refuses_the_catalog():
    with pytest.raises(SourceRejected):
        SourceEngine(CONTRACT).read(json.dumps({'fields': ['cik', 'ticker'], 'data': [['bad', 'A']]}).encode(),
                                    context=CONTEXT)


@pytest.mark.parametrize('fault', ['rank', 'fallback', 'duplicates'])
def test_deliberate_faults_change_the_rows(fault):
    import copy
    body = copy.deepcopy(CONTRACT)
    table = body['read']['tables']['tickers']
    payload = {'fields': ['cik', 'ticker'], 'data': [[1, ''], [2, 'A']]}
    rows = [(2, 'A', None)]
    if fault == 'rank':
        table['ordinal'] = 'source'
    elif fault == 'fallback':
        payload = {'fields': ['cik', 'cik_str', 'ticker'], 'data': [[0, 2, 'A']]}
        table['columns']['cik']['choose']['then']['choose']['condition']['test']['kind'] = 'not_null'
    else:
        payload = {'fields': ['cik', 'ticker', 'ticker'], 'data': [[1, 'first', 'last']]}
        rows = [(1, 'last', None)]
        table['each']['choose']['then']['matrix']['duplicates'] = 'reject'
    require_tables(SourceEngine(CONTRACT).read(json.dumps(payload).encode(), context=CONTEXT).tables['tickers'], expected(rows))
    with pytest.raises((ValueError, SourceRejected)):
        require_tables(SourceEngine(body).read(json.dumps(payload).encode(), context=CONTEXT).tables['tickers'], expected(rows))
