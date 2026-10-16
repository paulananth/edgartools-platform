"""Company main reading composition: the Company, its filings and its address, as the old loaders read them."""
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
from tests.engine.test_company_address import retained as retained_address
from tests.engine.test_source_combine import envelope, group, join, plan, table
from tests.support.exact import require_tables


CONTRACT = files.source('sec.submissions.company')
CONTEXT = {'cik': 1, 'sync_run_id': 'capture', 'raw_object_id': '0' * 64,
           'load_mode': 'default', 'recent_limit': None, 'last_synced_at': '2026-10-04T00:00:00Z'}


COMPANY_FIELDS = ('entity_name', 'entity_type', 'sic', 'sic_description', 'state_of_incorporation',
                  'state_of_incorporation_desc', 'fiscal_year_end', 'ein', 'description', 'category')
FILING_FIELDS = ('form', 'filing_date', 'report_date', 'acceptance_datetime', 'act', 'file_number', 'film_number',
                 'items', 'size', 'primary_document', 'primary_doc_desc')


def run(context=CONTEXT):
    return {'cik': context['cik'], 'sync_run_id': context['sync_run_id'],
            'raw_object_id': context['raw_object_id'], 'load_mode': context['load_mode']}


def company_row(context=CONTEXT, **filed):
    """The Company row: each SEC field as filed (any JSON value), else none, with the capture's run facts."""
    return {**run(context), **dict.fromkeys(COMPANY_FIELDS), 'last_sync_run_id': context['sync_run_id'],
            'last_synced_at': context['last_synced_at'], **filed}


def filing_row(accession, context=CONTEXT, **filed):
    """A filing row: each field as filed, else none; a flag that is not one is false."""
    return {'accession_number': accession, **run(context), **dict.fromkeys(FILING_FIELDS),
            'is_xbrl': False, 'is_inline_xbrl': False, **filed}


@pytest.mark.parametrize('payload, company, filings', [
    ({}, {}, []),
    ({'name': 'é🦀', 'entityType': 'other', 'sic': 0, 'category': False},
     {'entity_name': 'é🦀', 'entity_type': 'other', 'sic': 0, 'category': False}, []),
    ({'name': None, 'description': '', 'ein': '000000000', 'stateOfIncorporation': 'X0'},
     {'description': '', 'ein': '000000000', 'state_of_incorporation': 'X0'}, []),
    ({'name': ['retain', 1], 'sicDescription': {'raw': True}, 'fiscalYearEnd': 1231},
     {'entity_name': ['retain', 1], 'sic_description': {'raw': True}, 'fiscal_year_end': 1231}, []),
    ({'addresses': {'business': {'street1': ' raw ', 'stateOrCountry': ' de ', 'zipCode': '00123'}}}, {}, []),
    ({'filings': {'recent': {'accessionNumber': ['a', 'b', 'c'], 'form': ['10-K', '8-K', '10-K']}}}, {},
     [filing_row('a', form='10-K'), filing_row('b', form='8-K'), filing_row('c', form='10-K')]),
    ({'filings': None}, {}, []), ({'filings': {'recent': []}}, {}, []),
])
def test_main_reading_preserves_company_filings_and_address(payload, company, filings):
    result = SourceEngine(CONTRACT).read(json.dumps(payload).encode(), context=CONTEXT)
    require_tables(result.tables['company'], [company_row(**company)])
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
    company = company_row(context, entity_name='Example', forms=['10-K', '8-K'],
                          business_address=retained_address(payload))
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
