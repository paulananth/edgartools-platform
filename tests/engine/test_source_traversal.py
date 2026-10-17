"""Complete traversal evidence through the same interface as both callers."""
import copy
import io
from pathlib import Path

import pytest

from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers import source_attestation, source_read
from edgar_warehouse.workers.__main__ import runtime
from edgar_warehouse.workers import source_traversal
from edgar_warehouse.workers.source_traversal import Traversal
from tests.engine.test_source_stream_worker import contract, delimited_contract, zipped
from tests.engine.test_xml_stream_worker import xml_contract, document


def test_named_json_traversal_returns_complete_evidence_without_mutating_contract():
    rules = contract()
    before = copy.deepcopy(rules)
    traversal = Traversal(rules, archive_policy="configured")
    payload = b'{"records":[{"n":9007199254740993},{"n":2}]}'
    seen = []

    report = traversal.scan(io.BytesIO(payload), context={},
                            on_reading=lambda reading, index: seen.append((reading.tables, index)))

    assert report == {"record_count": 2, "expanded_bytes": len(payload)}
    assert seen == [({"rows": [{"n": 9007199254740993, "index": 1}]}, 0),
                    ({"rows": [{"n": 2, "index": 2}]}, 1)]
    assert rules == before


@pytest.mark.parametrize("framing", ["bare_json", "xml", "delimited"])
@pytest.mark.parametrize("compressed", [False, True])
def test_each_configured_framing_returns_evidence_for_plain_and_zip_inputs(framing, compressed):
    rules = contract()
    expected = [{"n": 10, "index": 1}, {"n": 20, "index": 2}]
    if framing == "xml":
        rules, payload = xml_contract(), document()
    elif framing == "delimited":
        rules, payload = delimited_contract(), b'n\tname\n10\tfirst\n20\tsecond\n'
        expected = [{"n": 10, "name": "first", "index": 1},
                    {"n": 20, "name": "second", "index": 2}]
    else:
        rules["read"]["stream"]["wrapper"] = None
        payload = b'[{"n":10},{"n":20}]'
    rules["read"]["stream"]["container"] = "zip" if compressed else "none"
    body = zipped({"capture": payload}) if compressed else payload
    found = []

    report = Traversal(rules, archive_policy="configured").scan(
        io.BytesIO(body), context={}, on_reading=lambda reading, _: found.extend(reading.tables["rows"]))

    assert report == {"record_count": 2, "expanded_bytes": len(payload)}
    assert found == expected


def test_whole_archive_policy_cannot_be_weakened_by_configured_member_selection():
    rules = contract()
    rules["read"]["context"]["total"] = {"type": "integer"}
    rules["read"]["stream"].update(container="zip", member="chosen.json", expected_records_context="total")
    body = zipped({"chosen.json": b'{"records":[{"n":1}]}', "other": b'untrusted'})
    selected = Traversal(rules, archive_policy="configured").scan(
        io.BytesIO(body), context={"total": 1}, on_reading=lambda *_: None)
    assert selected["record_count"] == 1
    with pytest.raises(ValueError, match="one unencrypted ZIP member"):
        Traversal(rules, archive_policy="whole").scan(
            io.BytesIO(body), context={"total": 1}, on_reading=lambda *_: None)


def test_compiled_traversal_reuses_private_policy_after_caller_mutation():
    rules = contract()
    traversal = Traversal(rules, archive_policy="configured")
    rules["read"]["stream"]["wrapper"] = "changed"
    traversal.spec["wrapper"] = "also_changed"
    for _ in range(2):
        assert traversal.scan(io.BytesIO(b'{"records":[]}'), context={}, on_reading=lambda *_: None) == {
            "record_count": 0, "expanded_bytes": 14}


def test_shared_dispatch_does_not_expand_attestation_format_support():
    rules = delimited_contract()
    rules["read"]["context"]["total"] = {"type": "integer"}
    rules["read"]["stream"]["expected_records_context"] = "total"
    with pytest.raises(ValueError, match="JSON or XML framing only"):
        Traversal(rules, archive_policy="whole").scan(
            io.BytesIO(zipped({"capture": b'n\tname\n1\tx\n'})),
            context={"total": 1}, on_reading=lambda *_: None)


@pytest.mark.parametrize("payload", [b'{"records":[{"n":1}]} trailing', b'{"records":[{"n":1}]'])
def test_callback_prefix_never_supplies_complete_evidence(payload):
    found = []
    with pytest.raises(SourceRejected):
        Traversal(contract(), archive_policy="configured").scan(
            io.BytesIO(payload), context={}, on_reading=lambda reading, _: found.append(reading.tables))
    assert found == [{"rows": [{"n": 1, "index": 1}]}]


@pytest.mark.parametrize("module", [source_read, source_attestation])
def test_traversal_byte_changes_alter_each_callers_runtime_fingerprint(monkeypatch, module):
    before = runtime(module)
    changed = Path(source_traversal.__file__)
    read_bytes = Path.read_bytes

    def edited(path):
        data = read_bytes(path)
        return data + b"\n# Traversal implementation edit.\n" if path == changed else data

    monkeypatch.setattr(Path, "read_bytes", edited)
    assert runtime(module) != before
