"""An opened Source Extract owns evidence and one bounded private traversal."""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_read, source_readings
from tests.engine.test_source_lookup_receipts import lookup_task


def test_evidence_and_lookup_values_belong_to_the_same_opened_extract(tmp_path):
    store = Artifacts()
    work, manifest = lookup_task(tmp_path, store)
    ref = source_read.execute(work, store)
    opened = source_readings.OpenedExtract(ref, store, max_bytes=1024**2, max_rows=100,
                                         max_contract_bytes=1024**2, allow_lookup_receipts=True)
    assert opened.reading == ref
    exposed = opened.reading
    exposed['sha256'] = '0' * 64
    assert opened.reading == ref
    assert opened.contract == store.json(manifest['contract'])
    assert opened.artifacts[0]['input'] == manifest['artifacts'][0]['input']
    assert opened.lookup_sets(0) == {'wanted': ['A']}
    expected_ref = deepcopy(ref)
    ref['sha256'] = '0' * 64
    events = list(opened.chunks())
    assert [row['n'] for _, _, chunk, _ in events for row in chunk['tables']['rows']] == ['A', 'A']
    assert events[0][0]['reading'] == expected_ref


def open_extract(ref, store, **bounds):
    return source_readings.OpenedExtract(ref, store, max_bytes=bounds.get('max_bytes', 1024**2),
                                         max_rows=bounds.get('max_rows', 100), max_contract_bytes=1024**2,
                                         allow_lookup_receipts=bounds.get('allow_lookup_receipts', False))


def test_evidence_and_lookup_mutation_cannot_redirect_later_chunks(tmp_path):
    store = Artifacts()
    work, manifest = lookup_task(tmp_path, store)
    ref = source_read.execute(work, store)
    opened = open_extract(ref, store, allow_lookup_receipts=True)
    opened.artifacts[0]['input']['sha256'] = '0' * 64
    opened.contract['read']['lookup_sets']['wanted']['max_values'] = 0
    values = opened.lookup_sets(0)
    values['wanted'].append('B')
    assert opened.lookup_sets(0) == {'wanted': ['A']}
    chunks = opened.chunks()
    header, _, chunk, _ = next(chunks)
    header['reading']['sha256'] = '0' * 64
    chunk['lookups']['sha256'] = '0' * 64
    rest = list(chunks)
    assert rest[-1][2]['lookups'] == manifest['artifacts'][0]['lookups']
    assert [row['n'] for _, _, part, _ in rest for row in part['tables']['rows']] == ['A']


def test_private_index_is_opened_once_and_partitions_remain_lazy(tmp_path):
    from tests.engine.test_partitioned_reading_consumers import stream

    class Observed(Artifacts):
        def verified(self, ref, **bounds):
            self.reads.append(deepcopy(ref))
            return super().verified(ref, **bounds)

    store = Observed()
    store.reads = []
    ref = stream(store, tmp_path)
    parts = store.json(ref)['artifacts'][0]['partitions']
    store.reads.clear()
    opened = open_extract(ref, store)
    assert all(part['receipt'] not in store.reads for part in parts)
    iterator = opened.chunks()
    next(iterator)
    assert parts[0]['receipt'] in store.reads and parts[1]['receipt'] not in store.reads
    # Replacing the original index after opening cannot redirect its private view.
    Path(urlparse(ref['uri']).path).write_bytes(b'{}')
    assert len(list(iterator)) == 1
    assert store.reads.count(ref) == 1


@pytest.mark.parametrize('inline,count,copies', [(False, 0, 1), (False, 5, 2), (True, 5, 1)])
def test_formats_empty_schema_and_original_artifact_indices(tmp_path, inline, count, copies):
    from tests.engine.test_partitioned_reading_consumers import stream

    store = Artifacts()
    ref = stream(store, tmp_path, count=count)
    if inline:
        body, _ = source_readings.load(ref, store, max_bytes=1024**2, max_rows=100)
    else:
        body = store.json(ref)
    body['artifacts'] *= copies
    ref = store.put(tmp_path.as_uri(), body)
    events = list(open_extract(ref, store).chunks())
    assert {index for _, index, _, _ in events} == set(range(copies))
    for index in range(copies):
        assert [r['n'] for _, i, chunk, _ in events if i == index for r in chunk['tables']['rows']] == list(range(count))
    assert all('rows' in chunk['tables'] for _, _, chunk, _ in events)


@pytest.mark.parametrize('fault', ['late_corruption', 'bytes', 'rows', 'early_stop'])
def test_prefixes_do_not_establish_complete_consumption(tmp_path, fault):
    from tests.engine.test_partitioned_reading_consumers import stream

    store = Artifacts()
    ref = stream(store, tmp_path)
    parts = store.json(ref)['artifacts'][0]['partitions']
    bounds = {'max_rows': 3} if fault == 'rows' else {}
    if fault == 'bytes':
        bounds['max_bytes'] = len(store.verified(ref)) + parts[0]['bytes']
    opened = open_extract(ref, store, **bounds)
    iterator = opened.chunks()
    assert len(next(iterator)[2]['tables']['rows']) == 3
    if fault == 'early_stop':
        iterator.close()
    else:
        if fault == 'late_corruption':
            Path(urlparse(parts[1]['receipt']['uri']).path).write_bytes(b'{}')
        with pytest.raises(ValueError):
            list(iterator)
    with pytest.raises(ValueError, match='one traversal'):
        opened.chunks()


def test_lookup_opt_in_is_explicit_and_derived_pairs_use_the_same_evidence(tmp_path):
    from tests.engine.test_source_lookup_receipts import _pair_task

    store = Artifacts()
    task = _pair_task(tmp_path, store, [{'holding': '1', 'isin': 'US0000000001'}])
    ref = source_read.execute(task, store)
    with pytest.raises(ValueError, match='explicitly bind'):
        open_extract(ref, store)
    opened = open_extract(ref, store, allow_lookup_receipts=True)
    assert opened.lookup_sets(0) == {'isin': [('1', 'US0000000001')]}
    assert [r['isin'] for _, _, chunk, _ in opened.chunks() for r in chunk['tables']['rows']] == [
        'US0000000001', None, None]


@pytest.mark.parametrize('module_name,changed_name', [('source_read', 'source_readings'),
                                                     ('mdm_merge', 'relationships')])
def test_evidence_and_relationship_edits_change_the_owning_runtime(monkeypatch, module_name, changed_name):
    from edgar_warehouse.workers import mdm_merge
    from edgar_warehouse.mdm.clean import relationships
    from edgar_warehouse.workers.__main__ import runtime

    module = {'source_read': source_read, 'mdm_merge': mdm_merge}[module_name]
    changed = Path({'source_readings': source_readings, 'relationships': relationships}[changed_name].__file__)
    before = runtime(module)
    read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda p: read_bytes(p) + (b'\n# edit\n' if p == changed else b''))
    assert runtime(module) != before
