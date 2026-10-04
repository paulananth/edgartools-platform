"""Configured raw business addresses; retained functions are comparison oracles."""
import json
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.loaders.bronze_submission_extractors import stage_address_loader
from edgar_warehouse.mdm.clean.company_source import business_address
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.workers import source_read, mdm_prepare

CONTRACT = files.load(Path(__file__).parent / 'fixtures/company-address.yaml')


def retained(payload):
    rows = stage_address_loader(payload, 1, 'trial', '0' * 64, 'default')
    found = [business_address(row) for row in rows if row['address_type'] == 'business']
    return found[-1] if found else None


def configured(engine, payload):
    rows = engine.read(json.dumps(payload).encode()).tables['addresses']
    return rows[0]['business_address'] if rows else None


@pytest.mark.parametrize('address', [
    {}, {'stateOrCountry': 'DE'}, {'stateOrCountry': ' de '},
    {'stateOrCountry': '', 'countryCode': 'X0'}, {'stateOrCountry': None, 'countryCode': ' x0 '},
    {'stateOrCountry': ' ', 'countryCode': 'X0'}, {'stateOrCountry': 'unknown', 'countryCode': 'X0'},
    {'stateOrCountry': 'P7', 'street1': '  raw  ', 'zipCode': '5504'},
    {'stateOrCountry': 'E9', 'street1': '', 'street2': None, 'city': '0'},
    {'street1': 0, 'street2': False, 'city': [], 'zipCode': {}},
])
def test_raw_address_matches_retained_derivation(address):
    payload = {'addresses': {'business': address, 'mailing': {'stateOrCountry': 'CA'}}}
    assert configured(SourceEngine(CONTRACT), payload) == retained(payload)


def test_every_frozen_sec_place_code_and_variants_match_retained_mapping():
    engine = SourceEngine(CONTRACT)
    for code in files.reference('sec-place-codes')['codes']:
        for field in ('stateOrCountry', 'countryCode'):
            for value in (code, code.lower(), f' {code.lower()} '):
                payload = {'addresses': {'business': {field: value}}}
                assert configured(engine, payload) == retained(payload), (field, value)


@pytest.mark.parametrize('payload', [{}, {'addresses': {}}, {'addresses': {'mailing': {}}}])
def test_absent_business_address_is_not_an_invented_empty_object(payload):
    assert configured(SourceEngine(CONTRACT), payload) is retained(payload) is None


def test_address_worker_verifier_and_preparation_preserve_exact_nested_record(tmp_path):
    store = Artifacts()
    payload = {'addresses': {'business': {'stateOrCountry': ' de ', 'street1': '  x  ', 'zipCode': '12345'}}}
    contract = store.put(tmp_path.as_uri(), CONTRACT)
    raw = store.put_bytes((tmp_path / 'source.json').as_uri(), json.dumps(payload).encode())
    manifest = store.put(tmp_path.as_uri(), {'version': 1, 'contract': contract, 'artifacts': [raw]})
    work = {'input': manifest, 'output': (tmp_path / 'reading.json').as_uri(), 'checks': ['source.output']}
    result = source_read.execute(work, store)
    assert source_read.verify({**work, 'candidate': result}, store) == ({'source.output': True}, [])
    keys = {'table': 'addresses', 'dataset': 'fixture.address', 'policy': '0' * 64,
            'consumer': 'trial', 'batch_id': 'address', 'as_of': '2026-10-04T00:00:00Z'}
    prepare = {'input': result, 'output': (tmp_path / 'mdm/manifest.json').as_uri(), 'keys': keys, 'checks': ['mdm.prepared']}
    prepared = mdm_prepare.execute(prepare, store)
    assert mdm_prepare.verify({**prepare, 'candidate': prepared}, store) == ({'mdm.prepared': True}, [])
    batch = store.json(prepared)['batches'][0]
    assert json.loads((tmp_path / 'mdm' / batch['input']['path']).read_bytes()) == {'business_address': retained(payload)}


def test_nontext_place_keys_refuse_without_destination_write(tmp_path):
    # This source contract keeps explicit typed lookup keys; arbitrary malformed
    # Python source coercions remain a retirement audit, not equivalence here.
    store = Artifacts()
    contract = store.put(tmp_path.as_uri(), CONTRACT)
    raw = store.put_bytes((tmp_path / 'source.json').as_uri(), b'{"addresses":{"business":{"stateOrCountry":12}}}')
    manifest = store.put(tmp_path.as_uri(), {'version': 1, 'contract': contract, 'artifacts': [raw]})
    work = {'input': manifest, 'output': (tmp_path / 'output.json').as_uri(), 'checks': ['source.output']}
    with pytest.raises(SourceRejected, match='lookup_key'):
        source_read.execute(work, store)
    assert not (tmp_path / 'output.json').exists()
