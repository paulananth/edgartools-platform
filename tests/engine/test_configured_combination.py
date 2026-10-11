"""Native generic combination preserves opaque Python payloads and exact keys."""
from edgar_warehouse.rules import source_engine
from edgar_warehouse.control_contract import canonical
from tests.engine.test_source_combine import group, table, join


def test_native_payloads_keep_huge_keys_numeric_spelling_and_nested_copy():
    huge = 10**80
    payload = {'雪': [huge, -0.0, 0.0, False, 0, 0.0]}
    rows = [{'id': huge, 'payload': payload}, {'id': str(huge), 'payload': 'text'}]
    inputs = {'raw': {'artifacts': [{'tables': {'rows': rows}}]}}
    groups = {'objects': group('raw', 'rows', 'id', 'payload', mode='one')}
    config = {'max_rows': 10, 'groups': groups, 'tables': {'out': table('raw', 'rows', {'chosen': join('objects', 'id')})}}
    result = source_engine.combine_tables(config, inputs, canonical)
    assert canonical(result) == canonical({'out': [dict(rows[0], chosen=payload), dict(rows[1], chosen='text')]})
    assert result['out'][0]['chosen'] is payload
    assert rows == [{'id': huge, 'payload': payload}, {'id': str(huge), 'payload': 'text'}]


def test_native_distinct_uses_canonical_types_and_stable_numeric_order():
    values = [True, 1, 1.0, -0.0, 0.0, {'b': 2, 'a': 1}, {'a': 1, 'b': 2}]
    rows = [{'id': 'k', 'value': v, 'rank': rank} for rank, v in enumerate(values)]
    spec = group('raw', 'rows', 'id', 'value', distinct=True, order_by=('rank',))
    inputs = {'raw': {'artifacts': [{'tables': {'rows': rows}}]}}
    config = {'max_rows': 20, 'groups': {'v': spec}, 'tables': {'out': table('raw', 'rows', {'chosen': join('v', 'id')})}}
    result = source_engine.combine_tables(config, inputs, canonical)
    assert canonical(result['out'][0]['chosen']) == '[true,1,1.0,-0.0,0.0,{"a":1,"b":2}]'


def test_native_natural_integer_order_supports_unbounded_signed_integers():
    values = [10**90, -(10**90), 0, -2, -11, 2, 11]
    rows = [{'id': 'k', 'value': v} for v in values]
    spec = group('raw', 'rows', 'id', 'value')
    spec['sort_values'] = True
    inputs = {'raw': {'artifacts': [{'tables': {'rows': rows}}]}}
    config = {'max_rows': 20, 'groups': {'v': spec}, 'tables': {'out': table('raw', 'rows', {'chosen': join('v', 'id')})}}
    assert source_engine.combine_tables(config, inputs, canonical)['out'][0]['chosen'] == sorted(values)


def test_worker_preserves_first_failure_before_later_check_and_has_no_publication(tmp_path):
    import pytest
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.workers import source_combine
    from tests.engine.test_source_combine import reading, envelope, plan
    store = Artifacts()
    refs = {'raw': reading(store, tmp_path, {'rows': [{'id': True, 'value': 1, 'fence': 'ok'},
                                                    {'id': 'k', 'value': 2, 'fence': 'wrong'}]})}
    spec = group('raw', 'rows', 'id', 'value', checks={'fence': 'ok'})
    work = envelope(store, tmp_path, plan({'v': spec}, {'out': table('raw', 'rows', {})}), refs)
    with pytest.raises(ValueError, match='keys must be text, integer or null'):
        source_combine.execute(work, store)
    assert not (tmp_path / 'output').exists()


def test_worker_keeps_escaped_surrogate_metadata_until_unused_columns_are_dropped(tmp_path):
    import json
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.workers import source_combine
    store = Artifacts()
    captured = store.put(tmp_path.as_uri(), {'fixture': 'escaped metadata'})
    rows = [{'id': '\ud800', 'rank': '\ud900', 'fence': '\udfff', 'value': 'B'},
            {'id': '\ud800', 'rank': '\ud800', 'fence': '\udfff', 'value': 'A'}]
    body = {'version': 1, 'artifacts': [{'input': captured, 'tables': {'rows': rows}, 'deferred': []}]}
    raw = store.put_bytes((tmp_path / 'escaped-reading.json').as_uri(), json.dumps(body, ensure_ascii=True).encode())
    selected = group('raw', 'rows', 'id', 'value', order_by=('rank',), distinct=True,
                     checks={'fence': '\udfff'}, where={'fence': '\udfff'})
    unused = group('raw', 'rows', 'id', 'id', distinct=True)
    unused['skip_empty_text'] = True
    output = table('raw', 'rows', {'chosen': join('v', 'id')})
    output['drop'] = ['id', 'rank', 'fence']
    config = {'execution': {'profile': 'source.combine'}, 'combine': {'max_rows': 10,
              'groups': {'v': selected, 'unused': unused}, 'tables': {'out': output}}}
    contract = store.put_bytes((tmp_path / 'escaped-contract.json').as_uri(), json.dumps(config, ensure_ascii=True).encode())
    manifest = store.put(tmp_path.as_uri(), {'version': 1, 'contract': contract, 'readings': {'raw': raw}})
    work = {'input': manifest, 'output': (tmp_path / 'output.json').as_uri(), 'checks': ['source.combined'], 'keys': {}}
    result = source_combine.execute(work, store)
    assert source_combine.verify({**work, 'candidate': result}, store) == ({'source.combined': True}, [])
    assert store.json(result)['artifacts'][0]['tables'] == {'out': [
        {'value': 'B', 'chosen': ['A', 'B']}, {'value': 'A', 'chosen': ['A', 'B']}]}
