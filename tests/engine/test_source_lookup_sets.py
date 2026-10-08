"""Configured indexed membership: frozen scope, raw bounds and valid stream EOF."""
import io
import json

import pytest

from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected


def contract():
    return {'read': {'format': 'json', 'lookup_sets': {
        'scope': {'max_values': 3, 'max_bytes': 8, 'max_value_bytes': 4}},
        'tables': {'rows': {'each': '.',
            'select': {'member': {'lookup': 'scope', 'key': {'value': {'path': 'key'}}}},
            'columns': {'key': {'value': {'path': 'key'}}}}}}}


def stream(engine, data, scope, consume):
    return engine.stream_json_array(io.BytesIO(data), wrapper='records', on_reading=consume,
        max_bytes=1024, max_record=256, max_records=100, lookups={'scope': scope})


def test_stream_freezes_scope_once_and_matches_eager_projection_through_eof():
    engine = SourceEngine(contract())
    scope = ['A']
    rows = [{'key': 'A'}, {'key': 'B'}, {'key': None}, {'key': 'A'}]
    found = []
    def consume(reading, ordinal):
        found.append(reading)
        if ordinal == 0:
            scope[:] = ['B']
    receipt = stream(engine, json.dumps({'records': rows}).encode(), scope, consume)
    assert receipt['record_count'] == 4
    assert [reading.tables for reading in found] == [
        engine.read(json.dumps(row).encode(), lookups={'scope': ['A']}).tables for row in rows]
    assert [r['key'] for reading in found for r in reading.tables['rows']] == ['A', 'A']


@pytest.mark.parametrize('scope', [[], ['éé'], ['A', 'A', 'A']])
def test_empty_unicode_and_duplicate_scopes_keep_exact_membership(scope):
    engine = SourceEngine(contract())
    found = []
    receipt = stream(engine, b'{"records":[{"key":"A"},{"key":"a"},{"key":null}]}', scope,
                     lambda reading, ordinal: found.extend(reading.tables['rows']))
    assert receipt['record_count'] == 3
    assert found == ([{'key': 'A'}] if 'A' in scope else [])


def test_raw_duplicate_generator_bound_stops_before_reading_an_empty_stream():
    reads = []
    def values():
        for i in range(100):
            reads.append(i)
            yield 'A'
    engine = SourceEngine(contract())
    with pytest.raises(SourceRejected, match='max_values'):
        stream(engine, b'{"records":[]}', values(), lambda *_: pytest.fail('read occurred'))
    assert reads == [0, 1, 2, 3]
    reads.clear()
    with pytest.raises(SourceRejected, match='max_values'):
        engine.read(b'{}', lookups={'scope': values()})
    assert reads == [0, 1, 2, 3]


@pytest.mark.parametrize('scope', [['12345'], ['ééé'], ['1234', '5678', '9']])
def test_raw_key_and_aggregate_bytes_refuse_before_any_callback(scope):
    with pytest.raises(SourceRejected, match='limit_exceeded'):
        stream(SourceEngine(contract()), b'{"records":[]}', scope, lambda *_: pytest.fail('read occurred'))


def test_missing_extra_and_wrong_type_scopes_fail_before_stream_input_is_read():
    class Unreadable:
        def read(self, *_):
            pytest.fail('lookup validation must precede transport reads')
    engine = SourceEngine(contract())
    for lookups in (None, {}, {'wrong': []}, {'scope': [], 'extra': []}):
        with pytest.raises(SourceRejected, match='invalid_lookup'):
            engine.stream_json_array(Unreadable(), wrapper='records', on_reading=lambda *_: None,
                max_bytes=1024, max_record=256, max_records=100, lookups=lookups)
    with pytest.raises(TypeError):
        stream(engine, b'{"records":[]}', 'A', lambda *_: None)
    with pytest.raises(TypeError):
        stream(engine, b'{"records":[]}', [False], lambda *_: None)


def test_membership_does_not_hide_bad_stream_tail_or_callback_failure():
    engine = SourceEngine(contract())
    with pytest.raises(SourceRejected):
        stream(engine, b'{"records":[{"key":"missing"}]} trailing', [], lambda *_: None)
    def fail(*_):
        raise RuntimeError('deliberate callback failure')
    with pytest.raises(SourceRejected, match='stream_consumer'):
        stream(engine, b'{"records":[{"key":"A"}]}', ['A'], fail)
