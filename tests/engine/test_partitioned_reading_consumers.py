"""Storage partition boundaries preserve combination and MDM batch semantics."""
import copy
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read, source_readings
from tests.engine.test_source_stream_worker import contract, task
from tests.engine.test_source_combine import envelope, plan, table


def stream(store, root, count=5):
    rules = contract()
    rules["read"]["stream"].update(max_records=2000, max_partitions=4096,
                                  max_output_rows=2000, partition_records=3)
    body = json.dumps({"records": [{"n": i} for i in range(count)]}).encode()
    return source_read.execute(task(root, store, [body], rules), store)


def preparation(ref, root):
    return {"input": ref, "output": (root / "manifest.json").as_uri(), "checks": [mdm_prepare.CHECK],
            "keys": {"table": "rows", "dataset": "fixture.rows", "policy": "0" * 64,
                     "consumer": "trial", "batch_id": "trial", "as_of": "2026-10-05T00:00:00Z"}}


def test_streamed_and_inline_readings_produce_identical_mdm_batches_across_partition_boundaries(tmp_path):
    store = Artifacts()
    ref = stream(store, tmp_path / "source", count=1005)
    normalized, _ = source_readings.load(ref, store, max_bytes=32 * 1024**2, max_rows=2000)
    inline = store.put(tmp_path.as_uri(), normalized)
    streamed_task = preparation(ref, tmp_path / "streamed")
    inline_task = preparation(inline, tmp_path / "inline")
    streamed = mdm_prepare.execute(streamed_task, store)
    ordinary = mdm_prepare.execute(inline_task, store)
    assert store.verified(streamed) == store.verified(ordinary)
    assert [batch["input"]["record_count"] for batch in store.json(streamed)["batches"]] == [1000, 5]
    for batch in store.json(streamed)["batches"]:
        name = batch["input"]["path"]
        assert (tmp_path / "streamed" / name).read_bytes() == (tmp_path / "inline" / name).read_bytes()
    assert mdm_prepare.verify({**streamed_task, "candidate": streamed}, store) == ({mdm_prepare.CHECK: True}, [])


def test_combination_selects_partitioned_tables_in_original_source_order(tmp_path):
    store = Artifacts()
    ref = stream(store, tmp_path / "source")
    work = envelope(store, tmp_path, plan({}, {"rows": table("source", "rows", {})}), {"source": ref})
    receipt = source_combine.execute(work, store)
    rows = store.json(receipt)["artifacts"][0]["tables"]["rows"]
    assert rows == [{"n": i, "index": i + 1} for i in range(5)]
    assert source_combine.verify({**work, "candidate": receipt}, store) == ({source_combine.CHECK: True}, [])


@pytest.mark.parametrize("mutation", ["gap", "record_count", "bytes", "tables", "bool_ordinal"])
def test_partition_metadata_faults_refuse_before_any_consumer_output(tmp_path, mutation):
    store = Artifacts()
    ref = stream(store, tmp_path / "source")
    body = copy.deepcopy(store.json(ref))
    artifact = body["artifacts"][0]
    if mutation == "gap": artifact["partitions"][1]["first_ordinal"] += 1
    if mutation == "record_count": artifact["record_count"] += 1
    if mutation == "bytes": artifact["partitions"][0]["bytes"] += 1
    if mutation == "tables": artifact["table_names"] = ["missing"]
    if mutation == "bool_ordinal": artifact["partitions"][0]["first_ordinal"] = True
    forged = store.put(tmp_path.as_uri(), body)
    work = preparation(forged, tmp_path / "mdm")
    with pytest.raises(ValueError):
        mdm_prepare.execute(work, store)
    assert not (tmp_path / "mdm").exists()


def test_partition_byte_and_row_budgets_are_aggregate(tmp_path):
    store = Artifacts()
    ref = stream(store, tmp_path / "source")
    index_bytes = len(store.verified(ref))
    first_bytes = store.json(ref)["artifacts"][0]["partitions"][0]["bytes"]
    with pytest.raises(ValueError, match="byte budget"):
        source_readings.load(ref, store, max_bytes=index_bytes + first_bytes, max_rows=100)
    with pytest.raises(ValueError, match="row budget"):
        source_readings.load(ref, store, max_bytes=32 * 1024**2, max_rows=4)


def test_empty_source_keeps_declared_empty_tables_for_combination(tmp_path):
    store = Artifacts()
    ref = stream(store, tmp_path / "source", count=0)
    body, _ = source_readings.load(ref, store, max_bytes=32 * 1024**2, max_rows=100)
    assert body["artifacts"][0]["tables"] == {"rows": []}
    work = envelope(store, tmp_path, plan({}, {"rows": table("source", "rows", {})}), {"source": ref})
    receipt = source_combine.execute(work, store)
    assert store.json(receipt)["artifacts"][0]["tables"] == {"rows": []}


@pytest.mark.parametrize("consumer", ["combine", "prepare"])
def test_corrupt_partition_is_refused_by_each_consumer_before_writes(tmp_path, consumer):
    store = Artifacts()
    ref = stream(store, tmp_path / "source")
    part = store.json(ref)["artifacts"][0]["partitions"][0]["receipt"]
    Path(urlparse(part["uri"]).path).write_bytes(b"{}")
    if consumer == "combine":
        work = envelope(store, tmp_path, plan({}, {"rows": table("source", "rows", {})}), {"source": ref})
        execute = source_combine.execute
        output = tmp_path / "output"
    else:
        work = preparation(ref, tmp_path / "mdm")
        execute = mdm_prepare.execute
        output = tmp_path / "mdm"
    with pytest.raises(ValueError, match="hash mismatch"):
        execute(work, store)
    assert not output.exists()
