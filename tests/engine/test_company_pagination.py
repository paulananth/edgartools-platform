"""Raw continuation pages read with generic rules, as the old pagination loader read them."""
import json
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
from tests.support.exact import require_tables
from tests.engine.test_company_preparation import filing_row
from tests.engine.test_source_combine import envelope, group, join, plan, table

CONTRACT = files.load(Path('rules/sources/sec.submissions.company/pagination.yaml'))
CONTEXT = {'cik': 1, 'sync_run_id': 'capture', 'raw_object_id': '0' * 64, 'load_mode': 'default'}


def configured(page):
    return SourceEngine(CONTRACT).read(json.dumps(page).encode(), context=CONTEXT).tables['filings']


def row(accession, **filed):
    return filing_row(accession, CONTEXT, **filed)


@pytest.mark.parametrize('page, rows', [
    ({}, []), ({'accessionNumber': []}, []), ({'accessionNumber': ['a']}, [row('a')]),
    ({'accessionNumber': ['a', 'b'], 'form': ['10-K'], 'size': ['1,234', 'bad'], 'isXBRL': [1, 0]},
     [row('a', form='10-K', is_xbrl=True), row('b')]),
    ({'accessionNumber': ['a', 'b'], 'filingDate': ['20261001ignored', '2026-09-30T23:00:00Z'],
      'reportDate': ['bad', '2026-09-29'], 'isInlineXBRL': [-1, False]},
     [row('a', filing_date='2026-10-01', is_inline_xbrl=True),
      row('b', filing_date='2026-09-30', report_date='2026-09-29')]),
    ({'accessionNumber': 'ab', 'form': 'XY'}, [row('a', form='X'), row('b', form='Y')]),
    ({'accessionNumber': ['a', 'b'], 'primaryDocument': [{'raw': True}, ['x', 1]], 'size': [True, 12.9]},
     [row('a', size=1, primary_document="{'raw': True}"), row('b', size=12, primary_document="['x', 1]")]),
    ({'accessionNumber': ['a', 'a'], 'form': ['8-K', '10-K']}, [row('a', form='8-K'), row('a', form='10-K')]),
])
def test_raw_page_exact_typed_rows(page, rows):
    require_tables(configured(page), rows)


@pytest.mark.parametrize('field,value', [
    ('accessionNumber', None), ('accessionNumber', 3), ('accessionNumber', {'0': 'a'}),
    ('form', 3), ('form', None), ('size', 3), ('size', None),
])
def test_malformed_selected_arrays_refuse(field, value):
    page = {'accessionNumber': ['a'], field: value}
    with pytest.raises(SourceRejected):
        configured(page)


def read(store, root, name, body, payload, context):
    raw = store.put_bytes((root / f'{name}.json').as_uri(), json.dumps(payload).encode())
    bound = store.put(root.as_uri(), {'version': 1, 'input': raw, 'values': context})
    contract = store.put(root.as_uri(), body)
    manifest = store.put(root.as_uri(), {'version': 2, 'contract': contract, 'artifacts': [{'input': raw, 'context': bound}]})
    work = {'input': manifest, 'output': (root / f'{name}-reading.json').as_uri(), 'checks': ['source.output']}
    result = source_read.execute(work, store)
    assert source_read.verify({**work, 'candidate': result}, store) == ({'source.output': True}, [])
    return result


def test_recent_and_raw_pages_combine_prepare_and_keep_capture_scope(tmp_path):
    store = Artifacts()
    main_body = files.source('sec.submissions.company')
    main = read(store, tmp_path, 'main', main_body, {'name': 'Company', 'filings': {'recent': {
        'accessionNumber': ['recent'], 'form': ['10-K']}}},
        {**CONTEXT, 'recent_limit': None, 'last_synced_at': '2026-10-04T00:00:00Z'})
    page = read(store, tmp_path, 'page', CONTRACT, {'accessionNumber': ['old', 'older'], 'form': ['20-F', '10-K']}, CONTEXT)
    combination = plan({'forms': group(['main', 'page'], 'filings', 'cik', 'form', distinct=True,
        order_by=('form',), checks={'sync_run_id': 'capture'})},
        {'company': table('main', 'company', {'forms': join('forms')}, checks={'last_sync_run_id': 'capture'})})
    work = envelope(store, tmp_path, combination, {'main': main, 'page': page})
    result = source_combine.execute(work, store)
    assert source_combine.verify({**work, 'candidate': result}, store) == ({'source.combined': True}, [])
    rows = store.json(result)['artifacts'][0]['tables']['company']
    assert rows[0]['forms'] == ['10-K', '20-F']
    scope = store.json(store.json(result)['artifacts'][0]['input'])
    assert scope['readings'] == {'main': main, 'page': page}
    prepare = {'input': result, 'output': (tmp_path / 'mdm/manifest.json').as_uri(), 'checks': ['mdm.prepared'],
        'keys': {'table': 'company', 'dataset': 'sec.submissions.company.v1', 'policy': '0' * 64,
                 'consumer': 'trial', 'batch_id': 'page', 'as_of': '2026-10-04T00:00:00Z'}}
    prepared = mdm_prepare.execute(prepare, store)
    assert mdm_prepare.verify({**prepare, 'candidate': prepared}, store) == ({'mdm.prepared': True}, [])
    batch = store.json(prepared)['batches'][0]
    require_tables(json.loads((tmp_path / 'mdm' / batch['input']['path']).read_bytes()), rows[0])
    # A foreign capture cannot enter the form evidence, even with the same CIK.
    foreign = read(store, tmp_path, 'foreign', CONTRACT, {'accessionNumber': ['old'], 'form': ['20-F']},
                   {**CONTEXT, 'sync_run_id': 'foreign'})
    bad = envelope(store, tmp_path, combination, {'main': main, 'page': foreign})
    bad['output'] = (tmp_path / 'bad.json').as_uri()
    with pytest.raises(ValueError, match='row check failed'):
        source_combine.execute(bad, store)
    assert not (tmp_path / 'bad.json').exists()
