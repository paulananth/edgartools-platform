"""Configured XML headers/records share the private source publication boundary."""
import copy
import io
import zipfile

import pytest

from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers import source_read
from tests.engine.test_source_stream_worker import Artifacts, contract, task


def xml_contract():
    rules = contract()
    read = rules["read"]
    read["tables"]["rows"]["columns"]["n"] = {"integer": {"path": "n.$"}}
    spec = read["stream"]
    for key in ("wrapper", "min_integer", "record_encoding"):
        del spec[key]
    spec.update(framing="xml_records", xml={"namespace": "urn:feed", "root": "Data",
        "header": "Header", "container": "Records", "record": "Record", "record_wrapper": None},
        header_read={"format": "json", "context": copy.deepcopy(read["context"]),
            "limits": {"max_bytes": 4096, "max_records": 1},
            "references": {"counts": {"2": {"valid": True}}},
            "assertions": [{"test": {"lookup": {"reference": "counts", "column": "valid",
                "key": {"text": {"path": "Count.$"}}, "on_missing": "null"}}, "reason": "pinned-count"}],
            "tables": {"header": {"each": "no_rows", "columns": {}}}})
    return rules


def document(count="2"):
    return (f"<Data xmlns='urn:feed'><Header><Count>{count}</Count></Header>"
            "<Records><Record><n>10</n></Record><Record><n>20</n></Record></Records></Data>").encode()


@pytest.mark.parametrize("compressed", [False, True])
def test_xml_projection_retries_and_independent_verification(tmp_path, compressed):
    store, rules, body = Artifacts(), xml_contract(), document()
    if compressed:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("capture.xml", body)
        body = buffer.getvalue()
        rules["read"]["stream"]["container"] = "zip"
    envelope = task(tmp_path, store, [body], rules)
    receipt = source_read.execute(envelope, store)
    assert source_read.execute(envelope, store) == receipt
    reading = store.json(receipt)["artifacts"][0]
    assert reading["record_count"] == 2
    assert store.json(reading["partitions"][0]["receipt"])["tables"]["rows"] == [
        {"n": 10, "index": 1}, {"n": 20, "index": 2}]
    assert source_read.verify({**envelope, "candidate": receipt}, store) == ({"source.output": True}, [])


@pytest.mark.parametrize("bad", [document("3"), document() + b"trailing",
    document().replace(b"<n>20</n>", b"<n>invalid</n>"),
    document().replace(b"</Data>", b"")])
def test_xml_faults_publish_no_prefix_even_after_prior_good_input(tmp_path, bad):
    store = Artifacts()
    envelope = task(tmp_path, store, [document(), bad], xml_contract())
    with pytest.raises(SourceRejected):
        source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json").exists()
    assert not (tmp_path / "reading.json.parts").exists()


def test_xml_source_count_remains_bound_to_input_context(tmp_path):
    store, rules = Artifacts(), xml_contract()
    rules["read"]["context"]["publication_count"] = {"type": "integer"}
    rules["read"]["stream"]["header_read"]["context"]["publication_count"] = {"type": "integer"}
    rules["read"]["stream"]["expected_records_context"] = "publication_count"
    envelope = task(tmp_path, store, [document()], rules)
    manifest = store.json(envelope["input"])
    ref = manifest["artifacts"][0]
    context = store.put(tmp_path.as_uri(), {"version": 1, "input": ref, "values": {"publication_count": 3}})
    envelope["input"] = store.put(tmp_path.as_uri(), {**manifest, "version": 2, "artifacts": [{"input": ref, "context": context}]})
    with pytest.raises(ValueError, match="record count"):
        source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json.parts").exists()


@pytest.mark.parametrize("fault", ["unknown_field", "wrong_context", "json_policy", "invalid_envelope"])
def test_xml_configuration_refuses_before_publication(tmp_path, fault):
    rules = xml_contract()
    spec = rules["read"]["stream"]
    if fault == "unknown_field": spec["xml"]["extra"] = True
    elif fault == "wrong_context": spec["header_read"]["context"] = {}
    elif fault == "json_policy": spec["min_integer"] = -1
    else: spec["xml"]["root"] = "bad:name"
    store = Artifacts()
    envelope = task(tmp_path, store, [document()], rules)
    with pytest.raises((SourceRejected, ValueError)):
        source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json.parts").exists()
