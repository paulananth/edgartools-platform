"""Configured header-driven catalog evidence; retained parsing is an oracle."""
import json
from pathlib import Path
import pytest
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.silver_landing_store import _parse_company_ticker_rows
from scripts.qualification.qualify_company_main import require_tables

CONTRACT = files.load(Path('rules/sources/sec.submissions.company/catalog.yaml'))
CONTEXT = {'sync_run_id': 'catalog', 'source_name': 'company_tickers_exchange',
           'last_synced_at': '2026-10-05T00:00:00Z'}


def expected(payload):
    return [{**row, 'source_rank': rank, 'source_name': CONTEXT['source_name'],
             'last_sync_run_id': CONTEXT['sync_run_id'], 'last_synced_at': CONTEXT['last_synced_at']}
            for rank, row in enumerate(_parse_company_ticker_rows(payload), 1)]


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


@pytest.mark.parametrize('payload,code', [
    ({'fields': ['cik', 'ticker'], 'data': [[1, '']]}, 'check_failed'),
    ({'fields': ['cik', 'ticker'], 'data': [[None, 'A']]}, 'check_failed'),
    ({'fields': ['cik', 'ticker'], 'data': [['bad', 'A']]}, 'invalid_value'),
    ({'fields': ['cik', 'ticker'], 'data': [[1]]}, 'matrix_length'),
    ({'fields': ['cik', 'cik'], 'data': []}, 'matrix_header'),
])
def test_catalog_fails_closed_on_unqualified_rows(payload, code):
    with pytest.raises(SourceRejected) as error:
        SourceEngine(CONTRACT).read(json.dumps(payload).encode(), context=CONTEXT)
    assert error.value.code == code
