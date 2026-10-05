"""Caller facts and bounds are explicit, pinned, and independently reread."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.control_contract import Blocked
from tests.support.retired_submission_loaders.bronze_submission_extractors import stage_recent_filing_loader
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.workers import mdm_prepare, source_read

CONTRACT = Path(__file__).parent / 'fixtures/filing-complete.yaml'
PAYLOAD = {'cik': 7, 'filings': {'recent': {
    'accessionNumber': ['one', 'two'], 'form': ['10-K', '8-K'],
    'filingDate': ['2024-02-29', 'bad'], 'reportDate': ['2023-12-31'],
    'size': [9007199254740993, 'invalid'], 'isXBRL': [0.9, True],
    'isInlineXBRL': ['０', ' +１ '], 'primaryDocument': [' a.htm ', 'b.htm']}}}
VALUES = {'cik': 320193, 'sync_run_id': 'capture', 'raw_object_id': 'raw-id', 'load_mode': 'default', 'recent_limit': None}


@pytest.mark.parametrize('limit', [None, -10, -1, 0, 1, 2, 3, 9223372036854775807])
def test_all_18_columns_match_retained_loader_and_bounds(limit):
    values = {**VALUES, 'recent_limit': limit}
    expected = stage_recent_filing_loader(PAYLOAD, values['cik'], values['sync_run_id'], values['raw_object_id'], values['load_mode'], limit)
    expected = [{key: value.isoformat() if hasattr(value, 'isoformat') else value for key, value in row.items()} for row in expected]
    reading = SourceEngine(files.load(CONTRACT)).read(json.dumps(PAYLOAD).encode(), context=values)
    assert reading.tables['filings'] == expected
    assert not reading.deferred
    if expected:
        assert len(expected[0]) == 18
        assert expected[0]['cik'] != PAYLOAD['cik']


@pytest.mark.parametrize(('field', 'value'), [('cik', True), ('cik', 1.0), ('cik', 2**63), ('cik', -(2**63)-1), ('cik', '320193'), ('load_mode', None), ('load_mode', []), ('recent_limit', False), ('recent_limit', '1'), ('sync_run_id', 'é' * 2049)])
def test_context_types_and_utf8_byte_limits_fail_closed(field, value):
    with pytest.raises(SourceRejected, match='invalid_context'):
        SourceEngine(files.load(CONTRACT)).read(b'{}', context={**VALUES, field: value})


def test_missing_and_extra_context_keys_are_not_defaults_or_control_overrides():
    for values in ({}, {k: v for k, v in VALUES.items() if k != 'load_mode'}, {**VALUES, 'output': 'other.json'}):
        with pytest.raises(SourceRejected, match='invalid_context'):
            SourceEngine(files.load(CONTRACT)).read(b'{}', context=values)


def task(tmp_path, values=VALUES):
    store = Artifacts()
    contract = store.put_bytes((tmp_path / 'contract.yaml').as_uri(), CONTRACT.read_bytes())
    raw = store.put_bytes((tmp_path / 'input.json').as_uri(), json.dumps(PAYLOAD).encode())
    bound = store.put(tmp_path.as_uri(), {'version': 1, 'input': raw, 'values': values})
    manifest = store.put(tmp_path.as_uri(), {'version': 2, 'contract': contract, 'artifacts': [{'input': raw, 'context': bound}]})
    return store, {'input': manifest, 'output': (tmp_path / 'output.json').as_uri(), 'checks': ['source.output']}


def test_context_receipt_is_preserved_retried_and_independently_verified(tmp_path):
    store, envelope = task(tmp_path)
    receipt = source_read.execute(envelope, store)
    assert source_read.execute(envelope, store) == receipt
    assert source_read.verify({**envelope, 'candidate': receipt}, store) == ({'source.output': True}, [])
    output = store.json(receipt)
    entry = store.json(envelope['input'])['artifacts'][0]
    assert output['version'] == 1
    assert output['artifacts'][0]['input'] == entry['input']
    assert output['artifacts'][0]['context'] == entry['context']
    assert output['artifacts'][0]['tables']['filings'][0]['cik'] == VALUES['cik']
    # Corrupt the context, leaving the source and candidate output untouched.
    Path(entry['context']['uri'].removeprefix('file://')).write_bytes(b'{}')
    with pytest.raises(Blocked, match='hash mismatch'):
        source_read.verify({**envelope, 'candidate': receipt}, store)


@pytest.mark.parametrize('mutation', ['different-uri', 'different-hash', 'version-bool', 'missing-values', 'extra-key', 'values-list', 'duplicate-key', 'too-large'])
def test_context_binding_shape_and_bounds_reject_before_output(tmp_path, mutation):
    store, envelope = task(tmp_path)
    manifest = store.json(envelope['input'])
    entry = manifest['artifacts'][0]
    bound = store.json(entry['context'])
    if mutation == 'different-uri':
        bound['input']['uri'] += '.other'
    elif mutation == 'different-hash':
        bound['input']['sha256'] = '0' * 64
    elif mutation == 'version-bool':
        bound['version'] = True
    elif mutation == 'missing-values':
        del bound['values']
    elif mutation == 'extra-key':
        bound['output'] = 'elsewhere'
    elif mutation == 'values-list':
        bound['values'] = []
    elif mutation == 'too-large':
        bound['values']['load_mode'] = 'a' * (32 * 1024)
    data = json.dumps(bound).encode()
    if mutation == 'duplicate-key':
        data = b'{"version":1,"version":1}'
    entry['context'] = store.put_bytes((tmp_path / 'mutated-context.json').as_uri(), data)
    envelope['input'] = store.put(tmp_path.as_uri(), manifest)
    with pytest.raises((ValueError, Blocked)):
        source_read.execute(envelope, store)
    assert not (tmp_path / 'output.json').exists()


def test_version_two_requires_exact_input_and_context_receipts(tmp_path):
    store, envelope = task(tmp_path)
    manifest = store.json(envelope['input'])
    for value in ({'input': manifest['artifacts'][0]['input']}, {**manifest['artifacts'][0], 'output': 'other'}):
        envelope['input'] = store.put(tmp_path.as_uri(), {**manifest, 'artifacts': [value]})
        with pytest.raises(ValueError, match='Version-2'):
            source_read.execute(envelope, store)


def test_context_identity_survives_prepare_and_verification(tmp_path):
    store, envelope = task(tmp_path)
    manifest = store.json(envelope['input'])
    second = copy.deepcopy(manifest['artifacts'][0])
    second['context'] = store.put(tmp_path.as_uri(), {'version': 1, 'input': second['input'], 'values': {**VALUES, 'sync_run_id': 'second'}})
    manifest['artifacts'].append(second)
    envelope['input'] = store.put(tmp_path.as_uri(), manifest)
    reading = source_read.execute(envelope, store)
    prepare = {'input': reading, 'output': (tmp_path / 'mdm/manifest.json').as_uri(), 'checks': ['mdm.prepared'], 'keys': {
        'table': 'filings', 'dataset': 'qualification.filings', 'policy': '0' * 64, 'consumer': 'test/filings', 'batch_id': 'trial', 'as_of': '2026-10-03T00:00:00Z'}}
    receipt = mdm_prepare.execute(prepare, store)
    assert mdm_prepare.verify({**prepare, 'candidate': receipt}, store) == ({'mdm.prepared': True}, [])
    batches = store.json(receipt)['batches']
    assert len(batches) == 2
    assert len({batch['input']['path'] for batch in batches}) == 2
    assert len({batch['batch_id'] for batch in batches}) == 2
    assert len({batch['input']['publication']['publication_key'] for batch in batches}) == 2


def test_context_decoder_is_part_of_the_pinned_worker_runtime(tmp_path, monkeypatch):
    from edgar_warehouse.workers.__main__ import runtime
    decoder = tmp_path / 'decoder.py'
    decoder.write_bytes(Path(source_read.artifact_store.__file__).read_bytes())
    monkeypatch.setattr(source_read.artifact_store, '__file__', str(decoder))
    before = runtime(source_read)
    decoder.write_bytes(decoder.read_bytes().replace(b'raise ValueError("duplicate JSON key")', b'pass'))
    assert runtime(source_read) != before
