"""The database hash protocol is JSONB text, distinct from compact Python JSON."""

import pytest

from edgar_warehouse.rules import source_engine


@pytest.mark.parametrize(("body", "expected"), [
    ('{"bbb":1,"a":2,"aa":3,"é":4}', '{"a": 2, "aa": 3, "é": 4, "bbb": 1}'),
    ('[1e-7,1.2300,-0.00,1e3,1.2e-2]', '[0.0000001, 1.2300, 0.00, 1000, 0.012]'),
    ('{"x":1,"x":2}', '{"x": 2}'),
    ('[true,false,null,"\\uD834\\uDD1E","\\n\\t"]', '[true, false, null, "𝄞", "\\n\\t"]'),
    ('123456789012345678901234567890', '123456789012345678901234567890'),
])
def test_literal_jsonb_bytes(body, expected):
    assert source_engine.postgres_jsonb_text(body) == expected


@pytest.mark.parametrize("body", ['"\\u0000"', '"\\ud800"', '[NaN]', '[1,]', '1e131072', '1e-16384'])
def test_invalid_postgres_json_is_refused(body):
    with pytest.raises(ValueError):
        source_engine.postgres_jsonb_text(body)


def test_object_keeps_raw_numeric_scale_and_checks_all_parts():
    assert source_engine.postgres_jsonb_object({"value": "1.2300", "a": '"é"'}) == '{"a": "é", "value": 1.2300}'
    with pytest.raises(ValueError):
        source_engine.postgres_jsonb_object({"x": '"\\u0000"'})
    with pytest.raises(ValueError):
        source_engine.postgres_jsonb_object({"x": '1,"injected":2'})
    assert source_engine.postgres_jsonb_object({"x": '{"aa": 1.2300, "bbb": 0.0000001}'}, canonical_inputs=True) == '{"x": {"aa": 1.2300, "bbb": 0.0000001}}'
    with pytest.raises(ValueError):
        source_engine.postgres_jsonb_object({"x": '1,"injected":2'}, canonical_inputs=True)


def test_authenticated_stored_parts_preserve_the_existing_publication_domain():
    # A compact MDM request's numbers may expand in stored JSONB. Publication
    # must not acquire the general formatter's arbitrary new byte restriction.
    raw = '"' + 'x' * (64 * 1024**2) + '"'
    with pytest.raises(ValueError, match="64 MiB"):
        source_engine.postgres_jsonb_text(raw)
    prepared = source_engine.postgres_jsonb_object({"x": raw}, canonical_inputs=True)
    assert prepared == '{"x": ' + raw + '}'
