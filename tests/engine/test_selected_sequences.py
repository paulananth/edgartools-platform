"""Selected-row semantics preserve full source safety, count and receipts."""
import copy
import json
from itertools import product
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.workers import source_read
from scripts.qualification.audit_filing_semantics import compare

CONTRACT = Path(__file__).parent / 'fixtures/filing-complete.yaml'
CONTEXT = {'cik': 320193, 'sync_run_id': 'qualification', 'raw_object_id': 'captured',
           'load_mode': 'default', 'recent_limit': None}


def test_all_450_finite_anchor_field_limit_cases_match_retained_acceptance_and_rows():
    engine = SourceEngine(files.load(CONTRACT))
    anchors = [[], ['a'], ['a', 'b'], 'ab', {}, {'x': 'a'}, None, True, 1]
    fields = [[], ['4'], [True], [{'x': 1}], None, True, 1, {}, {'x': 1}, 'é🦀']
    for anchor, field, limit in product(anchors, fields, [None, -1, 0, 1, 2]):
        case = compare(engine, {'filings': {'recent': {'accessionNumber': anchor, 'form': field}}}, limit)
        assert case['same_acceptance_and_rows'], case


def test_zero_selection_does_not_hide_full_anchor_record_limit_or_count_mismatch():
    contract = files.load(CONTRACT)
    contract['read']['limits']['max_records'] = 1
    data = {'filings': {'recent': {'accessionNumber': ['a', 'b'], 'form': None}}}
    with pytest.raises(SourceRejected, match='limit_exceeded'):
        SourceEngine(contract).read(json.dumps(data).encode(), context={**CONTEXT, 'recent_limit': 0})
    contract['read']['limits']['max_records'] = 3
    contract['read']['record_count'] = {'table': 'filings', 'path': 'count'}
    data['count'] = 2
    assert SourceEngine(contract).read(json.dumps(data).encode(), context={**CONTEXT, 'recent_limit': 0}).tables['filings'] == []
    data['count'] = 0
    with pytest.raises(SourceRejected, match='record_count'):
        SourceEngine(contract).read(json.dumps(data).encode(), context={**CONTEXT, 'recent_limit': 0})


@pytest.mark.parametrize('policy', [None, 'all'])
def test_default_field_validation_is_not_disabled_by_first_n_zero(policy):
    contract = files.load(CONTRACT)
    parallel = contract['read']['tables']['filings']['each']['parallel']
    parallel.pop('validation')
    if policy:
        parallel['validation'] = policy
    with pytest.raises(SourceRejected, match='parallel_shape'):
        SourceEngine(contract).read(b'{"filings":{"recent":{"accessionNumber":["a"],"form":null}}}', context={**CONTEXT, 'recent_limit': 0})


def test_worker_verifier_preserve_unselected_input_and_refuse_changed_count(tmp_path):
    store = Artifacts()
    contract = files.load(CONTRACT)
    contract['read']['record_count'] = {'table': 'filings', 'path': 'count'}
    ref = store.put_bytes((tmp_path / 'contract.yaml').as_uri(), json.dumps(contract).encode())
    payload = {'count': 1, 'filings': {'recent': {'accessionNumber': {'0': 'a'}, 'form': None}}}
    data = store.put_bytes((tmp_path / 'captured.json').as_uri(), json.dumps(payload).encode())
    context = store.put(tmp_path.as_uri(), {'version': 1, 'input': data, 'values': {**CONTEXT, 'recent_limit': 0}})
    manifest = store.put(tmp_path.as_uri(), {'version': 2, 'contract': ref, 'artifacts': [{'input': data, 'context': context}]})
    envelope = {'input': manifest, 'output': (tmp_path / 'reading.json').as_uri(), 'checks': ['source.output']}
    candidate = source_read.execute(envelope, store)
    reading = store.json(candidate)
    assert reading['artifacts'] == [{'input': data, 'context': context, 'tables': {'filings': []}, 'deferred': []}]
    assert source_read.verify({**envelope, 'candidate': candidate}, store) == ({'source.output': True}, [])
    forged = copy.deepcopy(reading)
    forged['artifacts'][0]['context']['sha256'] = '0' * 64
    forged_ref = store.put_bytes((tmp_path / 'forged.json').as_uri(), json.dumps(forged).encode())
    with pytest.raises(ValueError):
        source_read.verify({**envelope, 'output': forged_ref['uri'], 'candidate': forged_ref}, store)
    payload['count'] = 0
    bad = store.put_bytes((tmp_path / 'bad-count.json').as_uri(), json.dumps(payload).encode())
    bound = store.put(tmp_path.as_uri(), {'version': 1, 'input': bad, 'values': {**CONTEXT, 'recent_limit': 0}})
    bad_manifest = store.put(tmp_path.as_uri(), {'version': 2, 'contract': ref, 'artifacts': [{'input': bad, 'context': bound}]})
    with pytest.raises(SourceRejected, match='record_count'):
        source_read.execute({**envelope, 'input': bad_manifest, 'output': (tmp_path / 'bad-output.json').as_uri()}, store)
    assert not (tmp_path / 'bad-output.json').exists()
