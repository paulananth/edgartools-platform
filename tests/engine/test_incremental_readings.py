"""Complete authenticated traversal, with one decoded partition at a time."""
import copy
from pathlib import Path
from urllib.parse import urlparse

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_readings
from tests.engine.test_partitioned_reading_consumers import stream


def chunks(ref, store, **bounds):
    return source_readings.iter_load(ref, store, max_bytes=bounds.get("max_bytes", 32 * 1024**2),
                                    max_rows=bounds.get("max_rows", 2000),
                                    allow_lookup_receipts=bounds.get("allow_lookup_receipts", False))


def test_incremental_rows_and_evidence_equal_materialized_reading(tmp_path):
    store = Artifacts()
    ref = stream(store, tmp_path / "source", count=1005)
    expected, expected_size = source_readings.load(ref, store, max_bytes=32 * 1024**2, max_rows=2000)
    rows, sizes = [], []
    for header, index, artifact, size in chunks(ref, store):
        assert index == 0
        assert header == {"version": 2, "reading": ref, "contract": store.json(ref)["contract"]}
        assert {k: v for k, v in artifact.items() if k not in ("tables", "deferred", "partition")} == {
            k: v for k, v in expected["artifacts"][0].items() if k not in ("tables", "deferred", "partitions")}
        assert artifact["partition"] in expected["artifacts"][0]["partitions"]
        assert len(artifact["tables"]["rows"]) <= 3
        rows.extend(artifact["tables"]["rows"])
        sizes.append(size)
    assert rows == expected["artifacts"][0]["tables"]["rows"]
    assert sizes == sorted(set(sizes))
    assert sizes[-1] == expected_size


def test_only_requested_partition_is_opened_and_later_corruption_refuses(tmp_path):
    store = Artifacts()
    ref = stream(store, tmp_path / "source")
    parts = store.json(ref)["artifacts"][0]["partitions"]
    reads = []
    verify = store.verified

    def observed(receipt, **bounds):
        reads.append(receipt)
        return verify(receipt, **bounds)

    store.verified = observed
    iterator = chunks(ref, store)
    assert next(iterator)[2]["tables"]["rows"] == [{"n": i, "index": i + 1} for i in range(3)]
    assert reads == [ref, parts[0]["receipt"]]
    Path(urlparse(parts[1]["receipt"]["uri"]).path).write_bytes(b"{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        list(iterator)
    # The prefix was useful private state, but never a complete reading.
    assert reads[-1] == parts[1]["receipt"]


@pytest.mark.parametrize("target", ["index", "chunk"])
def test_consumer_metadata_mutation_cannot_redirect_authenticated_traversal(tmp_path, target):
    store = Artifacts()
    ref = stream(store, tmp_path / "source")
    original = store.json(ref)
    iterator = chunks(ref, store)
    header, _, chunk, _ = next(iterator)
    replacement = store.put(tmp_path.as_uri(), {
        "version": 1, "tables": {"rows": [{"n": 999, "index": 999}]}, "deferred": []})
    if target == "index":
        header["reading"]["sha256"] = "0" * 64
        header["contract"]["sha256"] = "0" * 64
    else:
        chunk["partition"]["receipt"] = replacement
        chunk["partition"]["bytes"] = len(store.verified(replacement))
        chunk["table_names"][:] = ["altered"]
        chunk["input"]["sha256"] = "0" * 64
    # Also test mutation through the caller's original reference.
    original_ref = copy.deepcopy(ref)
    ref["sha256"] = "0" * 64
    final = list(iterator)
    assert len(final) == 1
    next_header, _, next_chunk, _ = final[0]
    assert next_header == {"version": 2, "reading": original_ref, "contract": original["contract"]}
    assert next_chunk["partition"] == original["artifacts"][0]["partitions"][1]
    assert next_chunk["input"] == original["artifacts"][0]["input"]
    assert next_chunk["tables"]["rows"] == [{"n": i, "index": i + 1} for i in range(3, 5)]


def test_incremental_index_cap_does_not_tighten_materialized_loader(tmp_path):
    store = Artifacts()
    ref = stream(store, tmp_path / "source")
    inline, _ = source_readings.load(ref, store, max_bytes=32 * 1024**2, max_rows=2000)
    # Whitespace is valid JSON and makes the old caller budget observable.
    from edgar_warehouse.control_contract import canonical
    data = canonical(inline).encode() + b" " * source_readings.INDEX_BYTES
    large = store.put_bytes((tmp_path / "large.json").as_uri(), data)
    loaded, size = source_readings.load(large, store, max_bytes=len(data), max_rows=2000)
    assert loaded == inline and size == len(data)
    with pytest.raises(ValueError):
        list(chunks(large, store, max_bytes=len(data)))


@pytest.mark.parametrize("mutation", ["gap", "eof", "boolean", "receipt"])
def test_complete_range_accounting_refuses_before_first_partition(tmp_path, mutation):
    store = Artifacts()
    ref = stream(store, tmp_path / "source")
    body = copy.deepcopy(store.json(ref))
    artifact = body["artifacts"][0]
    if mutation == "gap": artifact["partitions"][-1]["first_ordinal"] += 1
    if mutation == "eof": artifact["record_count"] += 1
    if mutation == "boolean": artifact["partitions"][-1]["record_count"] = True
    if mutation == "receipt": artifact["partitions"][-1]["receipt"]["sha256"] = "bad"
    forged = store.put(tmp_path.as_uri(), body)
    iterator = chunks(forged, store)
    with pytest.raises(ValueError):
        next(iterator)


@pytest.mark.parametrize("budget", ["bytes", "rows"])
def test_budgets_remain_aggregate_across_artifacts(tmp_path, budget):
    store = Artifacts()
    ref = stream(store, tmp_path / "source")
    body = store.json(ref)
    body["artifacts"].append(copy.deepcopy(body["artifacts"][0]))
    duplicated = store.put(tmp_path.as_uri(), body)
    first_size = sum(part["bytes"] for part in body["artifacts"][0]["partitions"])
    bounds = {"max_bytes": len(store.verified(duplicated)) + first_size} if budget == "bytes" else {"max_rows": 5}
    iterator = chunks(duplicated, store, **bounds)
    assert next(iterator)[1] == 0
    assert next(iterator)[1] == 0
    with pytest.raises(ValueError, match=f"{budget[:-1] if budget == 'rows' else 'byte'} budget"):
        next(iterator)


def test_empty_source_still_exposes_original_identity_and_schema(tmp_path):
    store = Artifacts()
    ref = stream(store, tmp_path / "source", count=0)
    events = list(chunks(ref, store, max_rows=0))
    assert len(events) == 1
    header, index, artifact, size = events[0]
    assert index == 0 and size == len(store.verified(ref))
    assert header["reading"] == ref
    assert artifact == {**{k: v for k, v in store.json(ref)["artifacts"][0].items() if k != "partitions"},
                        "partition": None, "tables": {"rows": []}, "deferred": []}


def test_lookup_receipts_require_consumer_identity_opt_in_and_survive_iteration(tmp_path):
    store = Artifacts()
    ref = stream(store, tmp_path / "source")
    body = store.json(ref)
    receipt = store.put(tmp_path.as_uri(), {"scope": ["a"]})
    body["artifacts"][0]["lookups"] = receipt
    scoped = store.put(tmp_path.as_uri(), body)
    with pytest.raises(ValueError, match="explicitly bind"):
        list(chunks(scoped, store))
    assert all(artifact["lookups"] == receipt
               for _, _, artifact, _ in chunks(scoped, store, allow_lookup_receipts=True))


def test_inline_iteration_has_explicit_schema_and_row_bounds(tmp_path):
    store = Artifacts()
    streamed = stream(store, tmp_path / "source")
    body, _ = source_readings.load(streamed, store, max_bytes=32 * 1024**2, max_rows=2000)
    inline = store.put(tmp_path.as_uri(), body)
    assert [event[2] for event in chunks(inline, store)] == [
        {k: v for k, v in artifact.items() if k != "partitions"} for artifact in body["artifacts"]]
    with pytest.raises(ValueError, match="row budget"):
        list(chunks(inline, store, max_rows=4))
    body["artifacts"][0]["tables"]["rows"] = [None]
    malformed = store.put(tmp_path.as_uri(), body)
    with pytest.raises(ValueError, match="object rows"):
        list(chunks(malformed, store))
