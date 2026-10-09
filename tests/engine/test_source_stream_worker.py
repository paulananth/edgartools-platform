"""Actual configured streaming, immutable parts and independent verification."""
import io
import json
import struct
import zipfile

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.workers import source_read


def contract():
    return {"execution": {"profile": "source.read", "workers": 1, "max_artifacts": 2},
            "read": {"format": "json", "limits": {"max_bytes": 4096, "max_records": 100},
                     "context": {"source_index": {"type": "integer"}},
                     "tables": {"rows": {"each": ".", "columns": {
                         "n": {"value": {"path": "n"}},
                         "index": {"context": {"name": "source_index"}}}}},
                     "stream": {"wrapper": "records", "container": "none", "max_input_bytes": 65536,
                         "max_bytes": 65536, "max_record": 4096, "max_records": 100,
                         "max_depth": 64, "min_integer": -(2**63), "record_encoding": "python",
                         "ordinal_context": "source_index", "partition_bytes": 4096,
                         "partition_records": 2, "max_partitions": 10,
                         "max_spool_bytes": 65536, "max_output_rows": 100}}}


def task(tmp_path, store, bodies, rules=None):
    rules = rules or contract()
    pinned = store.put_bytes((tmp_path / "contract.yaml").as_uri(), json.dumps(rules).encode())
    refs = [store.put_bytes((tmp_path / f"source-{i}").as_uri(), body) for i, body in enumerate(bodies)]
    manifest = store.put(tmp_path.as_uri(), {"version": 1, "contract": pinned, "artifacts": refs})
    return {"input": manifest, "output": (tmp_path / "reading.json").as_uri(), "checks": ["source.output"]}


def test_configured_projection_partitions_retries_and_independent_verification(tmp_path):
    store = Artifacts()
    body = json.dumps({"records": [{"n": i} for i in range(5)]}).encode()
    envelope = task(tmp_path, store, [body])
    receipt = source_read.execute(envelope, store)
    assert source_read.execute(envelope, store) == receipt
    found = store.json(receipt)
    reading = found["artifacts"][0]
    assert found["version"] == 2 and reading["record_count"] == 5
    assert reading["expanded_bytes"] == len(body)
    assert [(p["first_ordinal"], p["record_count"]) for p in reading["partitions"]] == [(1, 2), (3, 2), (5, 1)]
    rows = [row for part in reading["partitions"] for row in store.json(part["receipt"])["tables"]["rows"]]
    assert rows == [{"n": i, "index": i + 1} for i in range(5)]
    checks, proofs = source_read.verify({**envelope, "candidate": receipt}, store)
    assert checks == {"source.output": True} and proofs == []
    part = reading["partitions"][0]["receipt"]
    from pathlib import Path
    from urllib.parse import urlparse
    Path(urlparse(part["uri"]).path).write_bytes(b"{}")
    with pytest.raises(Blocked, match="hash mismatch"):
        source_read.verify({**envelope, "candidate": receipt}, store)


@pytest.mark.parametrize("bad", [b'{"records":[{"n":1}]} null', b'{"records":[{"n":1},{"n":2,"n":3}]}'])
def test_no_partitions_or_index_publish_before_all_inputs_reach_eof(tmp_path, bad):
    store = Artifacts()
    good = b'{"records":[{"n":1},{"n":2},{"n":3}]}'
    envelope = task(tmp_path, store, [good, bad])
    with pytest.raises(SourceRejected):
        source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json").exists()
    assert not (tmp_path / "reading.json.parts").exists()


def test_zip_stream_projects_one_authenticated_member(tmp_path):
    store = Artifacts()
    buffer = io.BytesIO()
    body = b'{"records":[{"n":9007199254740993}]}'
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("captured.json", body)
    rules = contract()
    rules["read"]["stream"]["container"] = "zip"
    envelope = task(tmp_path, store, [buffer.getvalue()], rules)
    receipt = source_read.execute(envelope, store)
    reading = store.json(receipt)["artifacts"][0]
    assert reading["expanded_bytes"] == len(body)
    assert store.json(reading["partitions"][0]["receipt"])["tables"]["rows"] == [{"n": 9007199254740993, "index": 1}]


@pytest.mark.parametrize("changes", [{"partition_bytes": 1}, {"max_spool_bytes": 1},
                                    {"max_output_rows": 1}, {"max_partitions": 1}])
def test_projection_bounds_fail_without_publishing(tmp_path, changes):
    store = Artifacts()
    rules = contract()
    rules["read"]["stream"].update(changes)
    envelope = task(tmp_path, store, [b'{"records":[{"n":1},{"n":2},{"n":3}]}'], rules)
    with pytest.raises((SourceRejected, ValueError)):
        source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json.parts").exists()


def test_unknown_stream_fields_are_refused_before_opening_the_source(tmp_path):
    rules = contract()
    rules["read"]["stream"]["surprise"] = True
    store = Artifacts()
    envelope = task(tmp_path, store, [b'{"records":[]}'], rules)
    with pytest.raises(ValueError, match="every framing"):
        source_read.execute(envelope, store)


@pytest.mark.parametrize("values", [{}, {"required": 7}, {"required": "ok", "surprise": True}])
def test_empty_array_still_validates_bound_context(tmp_path, values):
    store = Artifacts()
    rules = contract()
    rules["read"]["context"]["required"] = {"type": "text"}
    envelope = task(tmp_path, store, [b'{"records":[]}'], rules)
    manifest = store.json(envelope["input"])
    ref = manifest["artifacts"][0]
    context = store.put(tmp_path.as_uri(), {"version": 1, "input": ref, "values": values})
    manifest.update(version=2, artifacts=[{"input": ref, "context": context}])
    envelope["input"] = store.put(tmp_path.as_uri(), manifest)
    with pytest.raises(SourceRejected, match="invalid_context"):
        source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json").exists()


def test_index_byte_budget_is_checked_before_partition_publication(tmp_path, monkeypatch):
    store = Artifacts()
    envelope = task(tmp_path, store, [b'{"records":[{"n":1}]}'])
    monkeypatch.setattr(source_read, "OUTPUT_BYTES", 1)
    with pytest.raises(ValueError, match="index exceeds"):
        source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json.parts").exists()


def test_stream_contract_cannot_silently_use_the_eager_facade():
    with pytest.raises(SourceRejected, match="worker framing boundary"):
        SourceEngine(contract())


def test_partition_byte_accounting_handles_nested_unicode_and_escaped_values(tmp_path):
    store = Artifacts()
    values = [{"text": "é🦀\n\"", "array": [1, True, None]}, "\\", 9007199254740993]
    rules = contract()
    rules["read"]["stream"]["partition_records"] = 100
    first = {"version": 1, "tables": {"rows": [{"n": values[0], "index": 1}]}, "deferred": []}
    rules["read"]["stream"]["partition_bytes"] = len(json.dumps(first, ensure_ascii=False,
        separators=(",", ":"), sort_keys=True).encode())
    body = json.dumps({"records": [{"n": value} for value in values]}, ensure_ascii=False).encode()
    envelope = task(tmp_path, store, [body], rules)
    receipt = source_read.execute(envelope, store)
    parts = store.json(receipt)["artifacts"][0]["partitions"]
    assert parts[0]["record_count"] == 1
    assert parts[0]["bytes"] == rules["read"]["stream"]["partition_bytes"]
    assert source_read.verify({**envelope, "candidate": receipt}, store) == ({"source.output": True}, [])


def test_expanded_policy_can_represent_the_actual_gleif_capture_size(tmp_path):
    store = Artifacts()
    rules = contract()
    # ZIP central-directory preflight of the cached capture: this verifies
    # contract representability, not the archive's bytes or complete parsing.
    rules["read"]["stream"]["max_bytes"] = 13252301819
    envelope = task(tmp_path, store, [b'{"records":[{"n":1}]}'], rules)
    receipt = source_read.execute(envelope, store)
    assert source_read.verify({**envelope, "candidate": receipt}, store) == ({"source.output": True}, [])


def test_forged_zip_expanded_length_is_refused_before_partition_publication(tmp_path):
    body = b'{"records":[{"n":1}]}'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("captured.json", body)
    data = bytearray(buffer.getvalue())
    central = data.index(b"PK\x01\x02")
    struct.pack_into("<I", data, central + 24, len(body) + 1)
    # Python's ZIP reader accepts this forged size with valid content/CRC.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.read(archive.infolist()[0]) == body
    rules = contract()
    rules["read"]["stream"]["container"] = "zip"
    store = Artifacts()
    envelope = task(tmp_path, store, [bytes(data)], rules)
    with pytest.raises(ValueError, match="expanded length"):
        source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json.parts").exists()


def test_zip_crc_corruption_is_refused_before_partition_publication(tmp_path):
    body = b'{"records":[{"n":1}]}'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("captured.json", body)
    data = buffer.getvalue().replace(body, b'{"records":[{"n":2}]}', 1)
    rules = contract()
    rules["read"]["stream"]["container"] = "zip"
    store = Artifacts()
    envelope = task(tmp_path, store, [data], rules)
    with pytest.raises(SourceRejected):
        source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json.parts").exists()


@pytest.mark.parametrize("entrypoint", ["facade", "worker"])
@pytest.mark.parametrize("with_input_bound", [False, True])
def test_malformed_read_keeps_the_native_contract_refusal(tmp_path, entrypoint, with_input_bound):
    rules = contract()
    rules["read"] = None
    if with_input_bound:
        rules["execution"]["max_input_bytes"] = 32 * 1024**2
    with pytest.raises(SourceRejected, match="contract"):
        if entrypoint == "facade":
            SourceEngine(rules)
        else:
            store = Artifacts()
            envelope = task(tmp_path, store, [b'{"records":[]}'], rules)
            source_read.execute(envelope, store)


@pytest.mark.parametrize("expected", [0, 1, 3, -1, 101, True])
def test_stream_publication_count_refuses_mismatch_before_output(tmp_path, expected):
    store = Artifacts()
    rules = contract()
    rules["read"]["context"]["publication_count"] = {"type": "integer"}
    rules["read"]["stream"]["expected_records_context"] = "publication_count"
    envelope = task(tmp_path, store, [b'{"records":[{"n":1},{"n":2}]}'], rules)
    manifest = store.json(envelope["input"])
    ref = manifest["artifacts"][0]
    context = store.put(tmp_path.as_uri(), {"version":1,"input":ref,"values":{"publication_count":expected}})
    envelope["input"] = store.put(tmp_path.as_uri(), {**manifest,"version":2,"artifacts":[{"input":ref,"context":context}]})
    with pytest.raises((ValueError, SourceRejected)):
        source_read.execute(envelope, store)
    assert not (tmp_path / "reading.json").exists()
    assert not (tmp_path / "reading.json.parts").exists()


def test_stream_publication_count_is_bound_to_input_and_checked_through_eof(tmp_path):
    store = Artifacts()
    rules = contract()
    rules["read"]["context"]["publication_count"] = {"type":"integer"}
    rules["read"]["stream"]["expected_records_context"] = "publication_count"
    envelope = task(tmp_path, store, [b'{"records":[{"n":1},{"n":2}]}'], rules)
    manifest = store.json(envelope["input"])
    ref = manifest["artifacts"][0]
    context = store.put(tmp_path.as_uri(), {"version":1,"input":ref,"values":{"publication_count":2}})
    envelope["input"] = store.put(tmp_path.as_uri(), {**manifest,"version":2,"artifacts":[{"input":ref,"context":context}]})
    receipt = source_read.execute(envelope, store)
    assert store.json(receipt)["artifacts"][0]["record_count"] == 2
    assert store.json(receipt)["artifacts"][0]["context"] == context
    assert source_read.verify({**envelope,"candidate":receipt}, store) == ({"source.output":True},[])
