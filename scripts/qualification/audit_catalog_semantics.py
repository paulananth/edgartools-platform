"""Finite offline catalog branch/type/refusal audit; not universal equivalence."""
from __future__ import annotations
import argparse
import itertools
import json
from pathlib import Path
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from scripts.qualification.qualify_company_main import require_tables
from tests.support.ticker_catalog_oracle import parse_rows

CONTEXT = {'sync_run_id': 'catalog', 'source_name': 'company_tickers_exchange',
           'last_synced_at': '2026-10-05T00:00:00Z'}


def cases():
    yield from [None, [], False, {}, {'fields': None, 'data': []}, {'fields': [], 'data': []}]
    values = [None, False, True, 0, 1, -1, 9.9, '', ' ', '123', '1,234', 'bad', [], {}, [1],
              {'x': True}, '００１', 9223372036854775807]
    for cik, ticker, exchange in itertools.product(values, repeat=3):
        yield {'fields': ['cik', 'ticker', 'exchange'], 'data': [[cik, ticker, exchange]]}
        yield {'z': None, 'b': {'cik_str': cik, 'ticker': ticker, 'exchange': exchange}}
    for headers in [[], ['cik', 'ticker'], ['cik_str', 'ticker'], ['ticker', 'cik'],
                    ['cik', 'ticker', 'ticker'], ['cik', 'cik_str', 'ticker'],
                    [None, 0, {}, 'cik', 'ticker'], ['cik', 'ticker', '']]:
        for row in [None, {}, [], [1], [1, 'A'], [1, 'A', 'B'], [0, 2, 'B'], [False, None, 'B'],
                    [None, 0, {}, 1, 'A']]:
            yield {'fields': headers, 'data': [None, row, [2, 'following']]}
    for entry in [{}, {'cik_str': 1}, {'cik_str': 1, 'ticker': None}, {'cik_str': 1, 'ticker': False}]:
        for fields, data in itertools.product([None, [], {}, ''], repeat=2):
            yield {'fields': fields, 'data': data, 'row': entry}


def expected(payload):
    return [{**row, 'source_rank': rank, 'source_name': CONTEXT['source_name'],
             'last_sync_run_id': CONTEXT['sync_run_id'], 'last_synced_at': CONTEXT['last_synced_at']}
            for rank, row in enumerate(parse_rows(payload), 1)]


def audit():
    body = files.load(files.ROOT / 'sources/sec.submissions.company/catalog.yaml')
    engine = SourceEngine(body)
    total = accepted = refused = 0
    for payload in cases():
        total += 1
        try:
            rows = expected(payload)
        except (TypeError, ValueError, OverflowError):
            old = False
        else:
            old = True
        try:
            reading = engine.read(json.dumps(payload).encode(), context=CONTEXT)
        except SourceRejected:
            new = False
        else:
            new = True
        if old != new: raise ValueError(f'Case {total} has different refusal decisions: {payload!r}')
        if old:
            if reading.deferred: raise ValueError('Skipped parser rows must not create deferred mastering evidence')
            require_tables(reading.tables['tickers'], rows)
            accepted += 1
        else:
            refused += 1
    return {'cases': total, 'accepted': accepted, 'refused': refused, 'differences': 0,
            'comparison': 'canonical typed JSON and refusal decision',
            'oracle': 'silver_landing_store.py at e76fb929, archived in tests/support/ticker_catalog_oracle.py',
            'universal_equivalence': False,
            'explicit_boundaries': ['32 MiB bytes', '100000 input rows', '128 headers', '128 UTF-8 bytes per header',
                                    'signed 64-bit CIK output', 'finite JSON numbers and supported Unicode']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__': main()
