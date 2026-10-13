"""Capture document checks execute in the native configured reader."""
import pytest

from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.workers.provider_capture import _complete


def configuration(**changes):
    return dict(format='json', required=['cik', 'filings'], allow_empty=False, max_bytes=1024, **changes)


def test_presence_accepts_null_and_empty_members_without_coercing_them():
    _complete(b'{"cik":null,"filings":[]}', configuration())
    _complete(b'{"a.b":null}', dict(format='json', required=['a.b'], allow_empty=False, max_bytes=1024))
    with pytest.raises(SourceRejected):
        _complete(b'{"a":{"b":1}}', dict(format='json', required=['a.b'], allow_empty=False, max_bytes=1024))


@pytest.mark.parametrize('data', [b'[]', b'null', b'{}', b'{"cik":1}', b'{"cik":1,"filings":{}} garbage',
                                  b'{"cik":NaN,"filings":{}}'])
def test_incomplete_or_malformed_payload_fails(data):
    with pytest.raises(SourceRejected):
        _complete(data, configuration())


def test_empty_policy_and_exact_byte_bound():
    cfg = dict(format='json', required=[], allow_empty=True, max_bytes=2)
    _complete(b'{}', cfg)
    with pytest.raises(SourceRejected):
        _complete(b'{ }', cfg)
    with pytest.raises(SourceRejected):
        _complete(b'{}', {**cfg, 'allow_empty': False})


def test_duplicate_members_keep_existing_native_json_semantics():
    # Capture preserves the original bytes; the configured reader retains
    # its existing serde JSON last-member semantics.
    _complete(b'{"cik":1,"cik":2,"filings":{}}', configuration())


def test_predicate_presence_distinguishes_null_from_missing():
    contract = {'read': {'format': 'json', 'tables': {'r': {'each': '.', 'columns': {
        k: {'test': {'path': 'a.b', 'path_mode': 'member', 'kind': k}}
        for k in ('present', 'missing', 'null', 'not_null')}}}}}
    assert SourceEngine(contract).read(b'{"a.b":null}').tables['r'] == [
        dict(present=True, missing=False, null=True, not_null=False)]
    assert SourceEngine(contract).read(b'{}').tables['r'] == [
        dict(present=False, missing=True, null=True, not_null=False)]
