"""Indexed scopes are authenticated worker inputs, never scalar-context payloads."""
from pathlib import Path
from urllib.parse import urlparse

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers import source_read, source_readings
from tests.engine.test_source_stream_worker import contract, task


@pytest.fixture(autouse=True)
def no_custom_steps(monkeypatch):
    monkeypatch.setattr('edgar_warehouse.rules.source_engine.STEPS', {})


def lookup_task(tmp_path, store, *, streamed=True, values=None, parquet=False):
    rules = contract()
    rules['read']['lookup_sets'] = {'wanted': {'max_values':3, 'max_bytes':8, 'max_value_bytes':4}}
    rules['read']['tables']['rows']['select'] = {'member':{'lookup':'wanted','key':{'value':{'path':'n'}}}}
    if not streamed:
        del rules['read']['stream']
        rules['read']['tables']['rows']['each'] = 'records'
    data = b'{"records":[{"n":"A"},{"n":"B"},{"n":"A"}]}'
    if parquet:
        from io import BytesIO
        import pyarrow as pa
        import pyarrow.parquet as pq
        assert not streamed
        rules['read']['format'] = 'parquet'
        rules['read']['tables']['rows']['each'] = 'rows'
        buffer = BytesIO()
        pq.write_table(pa.table({'n':['A','B','A']}), buffer)
        data = buffer.getvalue()
    envelope = task(tmp_path, store, [data], rules)
    manifest = store.json(envelope['input'])
    ref = manifest['artifacts'][0]
    context = store.put(tmp_path.as_uri(), {'version':1, 'input':ref,
        'values':{} if streamed else {'source_index':1}})
    lookup = store.put(tmp_path.as_uri(), {'version':1, 'input':ref,
        'sets':{'wanted':['A']} if values is None else values})
    manifest.update(version=3, artifacts=[{'input':ref,'context':context,'lookups':lookup}])
    envelope['input'] = store.put(tmp_path.as_uri(), manifest)
    return envelope, manifest


@pytest.mark.parametrize('streamed,parquet', [(False,False), (True,False), (False,True)])
def test_lookup_receipt_flows_through_execution_retry_verification_and_consumption(tmp_path, streamed, parquet):
    store = Artifacts()
    envelope, manifest = lookup_task(tmp_path, store, streamed=streamed, parquet=parquet)
    receipt = source_read.execute(envelope, store)
    assert source_read.execute(envelope, store) == receipt
    assert source_read.verify({**envelope,'candidate':receipt}, store) == ({'source.output':True}, [])
    found, _ = source_readings.load(receipt, store, max_bytes=1024**2, max_rows=100, allow_lookup_receipts=True)
    artifact = found['artifacts'][0]
    assert artifact['input'] == manifest['artifacts'][0]['input']
    assert artifact['lookups'] == manifest['artifacts'][0]['lookups']
    assert [row['n'] for row in artifact['tables']['rows']] == ['A','A']
    if streamed:
        assert artifact['record_count'] == 3


@pytest.mark.parametrize('sets', [{}, {'wrong':[]}, {'wanted':[], 'extra':[]},
                                {'wanted':'A'}, {'wanted':[True]}, {'wanted':['A']*4},
                                {'wanted':['ééé']}, {'wanted':['1234','5678','9']}])
def test_bad_lookup_values_refuse_before_source_bytes_are_opened(tmp_path, sets):
    class NoSourceRead(Artifacts):
        def verified_stream(self, *args, **kwargs):
            pytest.fail('invalid lookup scope opened source bytes')
    store = NoSourceRead()
    envelope, _ = lookup_task(tmp_path, store, values=sets)
    with pytest.raises(ValueError):
        source_read.execute(envelope, store)
    assert not (tmp_path/'reading.json').exists()
    assert not (tmp_path/'reading.json.parts').exists()


@pytest.mark.parametrize('mutation', ['wrong_input','wrong_version','extra_field','lookup_missing'])
def test_lookup_binding_and_manifest_shape_are_exact(tmp_path, mutation):
    store = Artifacts()
    envelope, manifest = lookup_task(tmp_path, store)
    entry = manifest['artifacts'][0]
    body = store.json(entry['lookups'])
    if mutation == 'lookup_missing':
        del entry['lookups']
    else:
        if mutation == 'wrong_input':
            body['input'] = {**body['input'], 'uri':'file:///wrong-source'}
        elif mutation == 'wrong_version':
            body['version'] = True
        else:
            body['surprise'] = None
        entry['lookups'] = store.put(tmp_path.as_uri(), body)
    envelope['input'] = store.put(tmp_path.as_uri(), manifest)
    with pytest.raises(ValueError):
        source_read.execute(envelope, store)
    assert not (tmp_path/'reading.json.parts').exists()


def test_lookup_hash_corruption_refuses_without_publication(tmp_path):
    store = Artifacts()
    envelope, manifest = lookup_task(tmp_path, store)
    Path(urlparse(manifest['artifacts'][0]['lookups']['uri']).path).write_bytes(b'{}')
    with pytest.raises(Blocked, match='hash mismatch'):
        source_read.execute(envelope, store)
    assert not (tmp_path/'reading.json.parts').exists()


@pytest.mark.parametrize('parquet', [False, True])
def test_changed_authenticated_scope_cannot_verify_an_old_candidate(tmp_path, parquet):
    store = Artifacts()
    envelope, manifest = lookup_task(tmp_path, store, streamed=not parquet, parquet=parquet)
    candidate = source_read.execute(envelope, store)
    entry = manifest['artifacts'][0]
    new_scope = store.json(entry['lookups'])
    new_scope['sets']['wanted'] = ['B']
    entry['lookups'] = store.put(tmp_path.as_uri(), new_scope)
    envelope['input'] = store.put(tmp_path.as_uri(), manifest)
    with pytest.raises((ValueError, Blocked)):
        source_read.verify({**envelope,'candidate':candidate}, store)


def test_missing_receipt_cannot_fall_back_to_undeclared_or_context_scope(tmp_path):
    store = Artifacts()
    envelope, manifest = lookup_task(tmp_path, store)
    entry = manifest['artifacts'][0]
    del entry['lookups']
    manifest['version'] = 2
    envelope['input'] = store.put(tmp_path.as_uri(), manifest)
    with pytest.raises(ValueError, match='version-3'):
        source_read.execute(envelope, store)


def test_lookup_receipt_survives_zero_rows_but_never_masks_bad_original_eof(tmp_path):
    store = Artifacts()
    envelope, manifest = lookup_task(tmp_path, store, values={'wanted':[]})
    candidate = source_read.execute(envelope, store)
    artifact = store.json(candidate)['artifacts'][0]
    assert artifact['record_count'] == 3 and artifact['lookups'] == manifest['artifacts'][0]['lookups']
    assert all(store.json(part['receipt'])['tables']['rows'] == [] for part in artifact['partitions'])
    broken = store.put_bytes((tmp_path/'broken').as_uri(), b'{"records":[{"n":"A"}]} garbage')
    entry = manifest['artifacts'][0]
    for field in ['context','lookups']:
        body = store.json(entry[field]); body['input'] = broken
        entry[field] = store.put(tmp_path.as_uri(), body)
    entry['input'] = broken
    envelope.update(input=store.put(tmp_path.as_uri(), manifest), output=(tmp_path/'broken-output').as_uri())
    with pytest.raises(SourceRejected):
        source_read.execute(envelope, store)
    assert not (tmp_path/'broken-output').exists()
    assert not (tmp_path/'broken-output.parts').exists()


@pytest.mark.parametrize('streamed', [False, True])
def test_unqualified_consumer_cannot_silently_ignore_lookup_scope_identity(tmp_path, streamed):
    store = Artifacts()
    envelope, _ = lookup_task(tmp_path, store, streamed=streamed)
    receipt = source_read.execute(envelope, store)
    with pytest.raises(ValueError, match='bind lookup receipts'):
        source_readings.load(receipt, store, max_bytes=1024**2, max_rows=100)


@pytest.mark.parametrize('streamed', [False, True])
def test_combined_scope_keeps_distinct_lookup_receipts_in_mdm_publication_identity(tmp_path, streamed):
    from edgar_warehouse.workers import source_combine, mdm_prepare
    from tests.engine.test_source_combine import envelope as combine_envelope, plan, table
    store = Artifacts()
    read_task, manifest = lookup_task(tmp_path, store, streamed=streamed)
    scopes, publications = [], []
    for trial, values in enumerate([['A'], ['A','X']]):
        entry = manifest['artifacts'][0]
        body = store.json(entry['lookups']); body['sets']['wanted'] = values
        entry['lookups'] = store.put(tmp_path.as_uri(), body)
        read_task.update(input=store.put(tmp_path.as_uri(), manifest),
                         output=(tmp_path/f'reading-{trial}.json').as_uri())
        reading = source_read.execute(read_task, store)
        combined_task = combine_envelope(store, tmp_path, plan({}, {'rows':table('main','rows',{})}), {'main':reading})
        combined_task['output'] = (tmp_path/f'combined-{trial}.json').as_uri()
        combined = source_combine.execute(combined_task, store)
        assert source_combine.verify({**combined_task, 'candidate':combined}, store) == ({'source.combined':True}, [])
        combined_body = store.json(combined)
        assert [r['n'] for r in combined_body['artifacts'][0]['tables']['rows']] == ['A','A']
        scope = combined_body['artifacts'][0]['input']
        assert store.json(scope)['readings'] == {'main':reading}
        scopes.append(scope['sha256'])
        prep = {'input':combined, 'output':(tmp_path/f'mdm-{trial}/manifest.json').as_uri(),
                'checks':['mdm.prepared'], 'keys':{'table':'rows','dataset':'fixture',
                  'policy':'0'*64,'consumer':'trial','batch_id':'lookup','as_of':'2026-10-08T00:00:00Z'}}
        prepared = mdm_prepare.execute(prep, store)
        assert mdm_prepare.verify({**prep,'candidate':prepared}, store) == ({'mdm.prepared':True}, [])
        publications.append(store.json(prepared)['batches'][0]['input']['publication']['publication_key'])
    assert len(set(scopes)) == len(set(publications)) == 2


def test_approved_input_hash_pins_work_with_version_three_and_reject_changed_source(tmp_path):
    from edgar_warehouse.rules import files
    store = Artifacts()
    envelope, manifest = lookup_task(tmp_path, store)
    rules = files.loads(store.verified(manifest['contract']).decode())
    rules['execution']['input_sha256s'] = [manifest['artifacts'][0]['input']['sha256']]
    manifest['contract'] = store.put_bytes((tmp_path/'pinned-contract.yaml').as_uri(), files.dumps(rules).encode())
    envelope['input'] = store.put(tmp_path.as_uri(), manifest)
    candidate = source_read.execute(envelope, store)
    assert source_read.verify({**envelope,'candidate':candidate}, store) == ({'source.output':True}, [])
    manifest['artifacts'][0]['input'] = store.put_bytes((tmp_path/'different').as_uri(), b'{"records":[]}')
    envelope['input'] = store.put(tmp_path.as_uri(), manifest)
    with pytest.raises(ValueError, match='approved artifact hash'):
        source_read.execute(envelope, store)
