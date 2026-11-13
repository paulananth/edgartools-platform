"""mdm.prepare reads a file one stored piece at a time and writes what the whole file would give (invented rows)."""
import hashlib
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import mdm_prepare, source_readings

AS_OF = "2026-01-02T00:00:00+00:00"
INPUT = {"uri": "file:///invented/input.json", "sha256": "0" * 64}
KEYS = {"table": "rows", "dataset": "invented.v1", "policy": "1" * 64, "consumer": "c", "batch_id": "b", "as_of": AS_OF}


def rows(count):
    return [{"id": f"{n % (count - 100):05d}", "n": n, "published": "2026-01-01T00:00:00+00:00"} for n in range(count)]


def whole(store, root, table):
    return store.put(root.as_uri(), {"version": 1, "artifacts": [{"input": INPUT, "tables": {"rows": table}}]})


def in_pieces(store, root, table):
    contract = store.put(root.as_uri(), {"invented": "contract"})
    entry = source_readings.pieces(f"{root.as_uri()}/reading.json", {"input": INPUT}, {"rows": table}, [], ["rows"],
                                   1, source_readings.publish(store))
    return store.put(root.as_uri(), {"version": 2, "contract": contract, "artifacts": [entry]}), len(entry["partitions"])


def prepared(store, root, reading, keys):
    envelope = {"input": reading, "keys": {**KEYS, **keys}, "checks": [mdm_prepare.CHECK],
                "output": f"{root.as_uri()}/manifest.json"}
    mdm_prepare.execute(envelope, store)
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(root.glob("*.json*"))
            if path.name == "manifest.json" or path.suffix == ".jsonl"}


@pytest.mark.parametrize("keys", [{}, {"distinct_on": ["id"]}, {"effective_column": "published"},
                                  {"publication_key": "p", "revision": "3"}])
def test_a_file_in_pieces_prepares_the_same_files_as_the_whole_file(tmp_path, monkeypatch, keys):
    monkeypatch.setattr(source_readings, "PART_ROWS", 300)
    store, table = Artifacts(), rows(2500)
    (tmp_path / "a").mkdir(), (tmp_path / "b").mkdir(), (tmp_path / "r").mkdir()
    reading, count = in_pieces(store, tmp_path / "r", table)
    assert count == 9
    one = prepared(store, tmp_path / "a", whole(store, tmp_path / "r", table), keys)
    assert prepared(store, tmp_path / "b", reading, keys) == one
    assert len(one) == 4 and "manifest.json" in one  # three records files and the manifest


def test_the_first_records_file_is_written_before_the_last_piece_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(source_readings, "PART_ROWS", 300)
    store, events = Artifacts(), []
    (tmp_path / "out").mkdir(), (tmp_path / "r").mkdir()
    reading, count = in_pieces(store, tmp_path / "r", rows(2500))
    read, write = store.verified, store.put_bytes

    def verified(ref, **kwargs):
        if ".parts/" in ref["uri"]:
            events.append("piece")
        return read(ref, **kwargs)

    def put_bytes(uri, data):
        if uri.endswith(".jsonl"):
            events.append("records")
        return write(uri, data)

    monkeypatch.setattr(store, "verified", verified)
    monkeypatch.setattr(store, "put_bytes", put_bytes)
    prepared(store, tmp_path / "out", reading, {})
    assert events.count("piece") == count and events.count("records") == 3
    assert events.index("records") < len(events) - 1 - events[::-1].index("piece")
    assert events[:5] == ["piece"] * 4 + ["records"]  # 1,000 rows fill a batch during the fourth piece of 300


def test_a_piece_that_states_another_time_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(source_readings, "PART_ROWS", 300)
    store, table = Artifacts(), rows(700)
    table[-1]["published"] = "2026-01-01T00:00:01+00:00"
    (tmp_path / "out").mkdir(), (tmp_path / "r").mkdir()
    reading, _ = in_pieces(store, tmp_path / "r", table)
    with pytest.raises(ValueError, match="one effective time per artifact"):
        prepared(store, tmp_path / "out", reading, {"effective_column": "published"})
