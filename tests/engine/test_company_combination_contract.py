"""Shipped Company blueprint: raw configured main/pages/catalogs to prepared rows.

Retained parsing is an independent test oracle only. These cases do not claim
census/provenance policy, source activation, full population or installed mastering.
"""
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
from tests.engine.test_company_address import retained as retained_address
from tests.engine.test_company_preparation import expected, CONTEXT
from tests.support.ticker_catalog_oracle import parse_rows
from tests.support.retired_submission_loaders.bronze_submission_extractors import stage_pagination_filing_loader
from tests.engine.test_source_combine import envelope
from scripts.qualification.qualify_company_main import require_tables

ROOT = files.ROOT / 'sources/sec.submissions.company'


def read(store, root, name, rules, payload, context, *, more_payloads=()):
    artifacts = []
    for index, body in enumerate([payload, *more_payloads]):
        raw = store.put_bytes((root / f'{name}-{index}.json').as_uri(), json.dumps(body).encode())
        values = {**context}
        if 'raw_object_id' in values:
            values['raw_object_id'] = raw['sha256']
        bound = store.put(root.as_uri(), {'version': 1, 'input': raw, 'values': values})
        artifacts.append({'input': raw, 'context': bound})
    contract = store.put(root.as_uri(), rules)
    manifest = store.put(root.as_uri(), {'version': 2, 'contract': contract, 'artifacts': artifacts})
    work = {'input': manifest, 'output': (root / f'{name}-reading.json').as_uri(), 'checks': ['source.output']}
    receipt = source_read.execute(work, store)
    assert source_read.verify({**work, 'candidate': receipt}, store) == ({'source.output': True}, [])
    return receipt, values


def blueprint():
    rules = files.load(ROOT / 'combine.yaml')
    for spec in [*rules['combine']['groups'].values(), *rules['combine']['tables'].values()]:
        spec['checks'] = {column: {'APPROVED_COMPANY_CAPTURE_RUN': 'capture',
            'APPROVED_CATALOG_CAPTURE_RUN': 'catalog'}[pin] for column, pin in spec['checks'].items()}
    return rules


def captures(store, root, *, pages=True, foreign=None):
    main_payload = {'name': 'Example', 'addresses': {'business': {'street1': 'Raw', 'stateOrCountry': 'X0'}},
        'filings': {'recent': {'accessionNumber': ['r1', 'r2', 'r3'], 'form': ['S-8 POS', '10-K', '10-K']}}}
    page_payloads = [{'accessionNumber': ['p1', 'p2', 'p3'], 'form': ['S-8', '20-F', '']},
        {'accessionNumber': ['p4', 'p5'], 'form': ['6-K', '20-F']}]
    catalogs = {'catalog_exchange': {'fields': ['cik', 'ticker', 'exchange'],
        'data': [[1, 'B', 'NYSE'], [1, 'A', 'NYSE'], [None, 'IGNORED', None]]},
        'catalog_tickers': {'0': {'cik_str': 1, 'ticker': 'A'},
            '1': {'cik_str': 1, 'ticker': 'C'}, '2': {'cik_str': 2, 'ticker': 'OTHER'}}}
    refs = {}
    main_context = {**CONTEXT, 'sync_run_id': 'foreign' if foreign == 'main' else 'capture'}
    refs['main'], actual_context = read(store, root, 'main', files.source('sec.submissions.company'), main_payload, main_context)
    if pages:
        page_context = {key: CONTEXT[key] for key in ('cik', 'sync_run_id', 'raw_object_id', 'load_mode')}
        page_context['sync_run_id'] = 'foreign' if foreign == 'pages' else 'capture'
        refs['pages'], _ = read(store, root, 'pages', files.load(ROOT / 'pagination.yaml'), page_payloads[0], page_context, more_payloads=page_payloads[1:])
    for name, payload in catalogs.items():
        context = {'sync_run_id': 'foreign' if foreign == name else 'catalog',
            'last_synced_at': CONTEXT['last_synced_at'], 'source_name': name}
        refs[name], _ = read(store, root, name, files.load(ROOT / 'catalog.yaml'), payload, context)
    return refs, main_payload, page_payloads, catalogs, actual_context


@pytest.mark.parametrize('with_pages', [True, False])
def test_shipped_blueprint_combines_all_raw_readings_then_prepares_exact_rows(tmp_path, with_pages):
    store = Artifacts()
    refs, payload, pages, catalogs, context = captures(store, tmp_path, pages=with_pages)
    rules = blueprint()
    if not with_pages:
        rules['combine']['groups']['forms']['source'] = ['main']
    work = envelope(store, tmp_path, rules, refs)
    result = source_combine.execute(work, store)
    assert source_combine.verify({**work, 'candidate': result}, store) == ({'source.combined': True}, [])
    assert source_combine.execute(work, store) == result
    company, recent = expected(payload, context)
    historical = [row for page in pages for row in stage_pagination_filing_loader({'filings': page},
        **{key: context[key] for key in ('cik', 'sync_run_id', 'raw_object_id', 'load_mode')})] if with_pages else []
    forms = sorted({r['form'] for r in [*recent, *historical] if r['form']})
    pairs = [(rank, row['ticker']) for data in catalogs.values()
        for rank, row in enumerate(parse_rows(data), 1) if row['cik'] == 1 and row['ticker']]
    company.update(forms=forms, tickers=list(dict.fromkeys(ticker for _, ticker in sorted(pairs))),
        business_address=retained_address(payload))
    actual = store.json(result)['artifacts'][0]['tables']['company']
    require_tables(actual, [company])
    assert actual[0]['tickers'] == ['A', 'B', 'C']
    assert actual[0]['business_address']['country'] == 'GB'
    assert store.json(store.json(result)['artifacts'][0]['input'])['readings'] == refs
    prepare = {'input': result, 'output': (tmp_path / 'mdm/manifest.json').as_uri(),
        'checks': ['mdm.prepared'], 'keys': {'table': 'company', 'dataset': 'sec.submissions.company.v1',
            'policy': '0' * 64, 'consumer': 'trial', 'batch_id': 'all-inputs', 'as_of': CONTEXT['last_synced_at']}}
    prepared = mdm_prepare.execute(prepare, store)
    assert mdm_prepare.verify({**prepare, 'candidate': prepared}, store) == ({'mdm.prepared': True}, [])
    batch = store.json(prepared)['batches'][0]
    require_tables(json.loads((tmp_path / 'mdm' / batch['input']['path']).read_bytes()), company)


@pytest.mark.parametrize('foreign', ['main', 'pages', 'catalog_exchange', 'catalog_tickers'])
def test_every_input_capture_run_is_independently_fenced(tmp_path, foreign):
    store = Artifacts()
    refs, *_ = captures(store, tmp_path, foreign=foreign)
    with pytest.raises(ValueError, match='row check failed'):
        source_combine.execute(envelope(store, tmp_path, blueprint(), refs), store)
    assert not (tmp_path / 'output').exists()


def test_unbound_creator_blueprint_refuses_ordinary_capture_rows(tmp_path):
    store = Artifacts()
    refs, *_ = captures(store, tmp_path)
    with pytest.raises(ValueError, match='row check failed'):
        source_combine.execute(envelope(store, tmp_path, files.load(ROOT / 'combine.yaml'), refs), store)
    assert not (tmp_path / 'output').exists()


@pytest.mark.parametrize('fault', ['form_order', 'ticker_order', 'address_value'])
def test_deliberate_blueprint_faults_change_observable_company_evidence(tmp_path, fault):
    store = Artifacts()
    refs, *_ = captures(store, tmp_path)
    rules = blueprint()
    if fault == 'form_order':
        rules['combine']['groups']['forms']['sort_values'] = False
    elif fault == 'ticker_order':
        rules['combine']['groups']['tickers']['order_by'] = []
    else:
        rules['combine']['groups']['address']['value'] = 'cik'
    result = source_combine.execute(envelope(store, tmp_path, rules, refs), store)
    row = store.json(result)['artifacts'][0]['tables']['company'][0]
    if fault == 'form_order':
        assert row['forms'] != ['10-K', '20-F', '6-K', 'S-8', 'S-8 POS']
    elif fault == 'ticker_order':
        assert row['tickers'] != ['A', 'B', 'C']
    else:
        assert row['business_address'] == 1
