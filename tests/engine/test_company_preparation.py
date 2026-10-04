"""Company main reading composition; retained functions are parity oracles."""
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.loaders.bronze_submission_extractors import stage_company_loader, stage_recent_filing_loader
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
from tests.engine.test_company_address import retained as retained_address
from tests.engine.test_source_combine import envelope, group, join, plan, table
from scripts.qualification.qualify_company_main import require_tables


CONTRACT = files.source('sec.submissions.company')
CONTEXT = {'cik': 1, 'sync_run_id': 'capture', 'raw_object_id': '0' * 64,
           'load_mode': 'default', 'recent_limit': None, 'last_synced_at': '2026-10-04T00:00:00Z'}


def expected(payload, context):
    company = stage_company_loader(payload, context['cik'], context['sync_run_id'], context['raw_object_id'], context['load_mode'])[0]
    company.update(last_sync_run_id=context['sync_run_id'], last_synced_at=context['last_synced_at'])
    filings = stage_recent_filing_loader(payload, context['cik'], context['sync_run_id'], context['raw_object_id'], context['load_mode'], context['recent_limit'])
    return company, filings


@pytest.mark.parametrize('payload', [
    {}, {'name': 'é🦀', 'entityType': 'other', 'sic': 0, 'category': False},
    {'name': None, 'description': '', 'ein': '000000000', 'stateOfIncorporation': 'X0'},
    {'name': ['retain', 1], 'sicDescription': {'raw': True}, 'fiscalYearEnd': 1231},
    {'addresses': {'business': {'street1': ' raw ', 'stateOrCountry': ' de ', 'zipCode': '00123'}}},
    {'filings': {'recent': {'accessionNumber': ['a', 'b', 'c'], 'form': ['10-K', '8-K', '10-K']}}},
    {'filings': None}, {'filings': {'recent': []}},
])
def test_main_reading_preserves_company_filings_and_address(payload):
    result = SourceEngine(CONTRACT).read(json.dumps(payload).encode(), context=CONTEXT)
    company, filings = expected(payload, CONTEXT)
    require_tables(result.tables['company'], [company])
    require_tables(result.tables['filings'], filings)
    actual = result.tables['addresses']
    assert (actual[-1]['business_address'] if actual else None) == retained_address(payload)
    assert not result.deferred


@pytest.mark.parametrize('original,changed', [(False, 0), (0, 0.0), (True, 1)])
def test_qualification_detects_deliberate_json_type_substitutions(original, changed):
    expected = {'company': [{'nested': {'value': original}}]}
    substituted = {'company': [{'nested': {'value': changed}}]}
    assert expected == substituted  # Deliberate fault defeats structural equality.
    with pytest.raises(ValueError, match='JSON scalar types'):
        require_tables(substituted, expected)


def test_receipt_bound_main_read_combine_prepare_and_repeat(tmp_path):
    store = Artifacts()
    payload = {'name': 'Example', 'addresses': {'business': {'stateOrCountry': 'DE'}},
               'filings': {'recent': {'accessionNumber': ['a', 'b', 'c'], 'form': ['8-K', '10-K', '8-K']}}}
    raw = store.put_bytes((tmp_path / 'source.json').as_uri(), json.dumps(payload).encode())
    context = {**CONTEXT, 'raw_object_id': raw['sha256']}
    bound = store.put(tmp_path.as_uri(), {'version': 1, 'input': raw, 'values': context})
    contract = store.put(tmp_path.as_uri(), CONTRACT)
    manifest = store.put(tmp_path.as_uri(), {'version': 2, 'contract': contract, 'artifacts': [{'input': raw, 'context': bound}]})
    work = {'input': manifest, 'output': (tmp_path / 'reading.json').as_uri(), 'checks': ['source.output']}
    result = source_read.execute(work, store)
    assert source_read.verify({**work, 'candidate': result}, store) == ({'source.output': True}, [])
    combination = plan({
        'forms': group('main', 'filings', 'cik', 'form', distinct=True, order_by=('form',), checks={'sync_run_id': 'capture'}),
        'address': group('main', 'addresses', 'cik', 'business_address', mode='last', checks={'last_sync_run_id': 'capture'}),
    }, {'company': table('main', 'company', {'forms': join('forms'), 'business_address': join('address')}, checks={'last_sync_run_id': 'capture'})})
    combined_work = envelope(store, tmp_path, combination, {'main': result})
    combined = source_combine.execute(combined_work, store)
    assert source_combine.verify({**combined_work, 'candidate': combined}, store) == ({'source.combined': True}, [])
    assert source_combine.execute(combined_work, store) == combined
    company, _ = expected(payload, context)
    company.update(forms=['10-K', '8-K'], business_address=retained_address(payload))
    assert store.json(combined)['artifacts'][0]['tables']['company'] == [company]
    keys = {'table': 'company', 'dataset': 'sec.submissions.company.v1', 'policy': '0' * 64,
            'consumer': 'trial', 'batch_id': 'main', 'as_of': CONTEXT['last_synced_at']}
    prepare = {'input': combined, 'output': (tmp_path / 'mdm/manifest.json').as_uri(), 'keys': keys, 'checks': ['mdm.prepared']}
    prepared = mdm_prepare.execute(prepare, store)
    assert mdm_prepare.verify({**prepare, 'candidate': prepared}, store) == ({'mdm.prepared': True}, [])
    batch = store.json(prepared)['batches'][0]
    assert json.loads((tmp_path / 'mdm' / batch['input']['path']).read_bytes()) == company


def test_context_for_another_input_refuses_before_output(tmp_path):
    store = Artifacts()
    raw = store.put_bytes((tmp_path / 'source.json').as_uri(), b'{}')
    bound = store.put(tmp_path.as_uri(), {'version': 1, 'input': {**raw, 'sha256': '1' * 64}, 'values': CONTEXT})
    contract = store.put(tmp_path.as_uri(), CONTRACT)
    manifest = store.put(tmp_path.as_uri(), {'version': 2, 'contract': contract, 'artifacts': [{'input': raw, 'context': bound}]})
    output = tmp_path / 'reading.json'
    with pytest.raises(ValueError, match='exact input receipt'):
        source_read.execute({'input': manifest, 'output': output.as_uri(), 'checks': ['source.output']}, store)
    assert not output.exists()
