"""source.read version 4 (ticket 111): one unit reads a verified reading piece by
piece, so a step after a combine is known before the run. A large reading's
pieces are its parts; a small one's inline rows are written beside the output."""
import json
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_read
from tests.support.source_chain import read


def contract(table: str, each: str, max_artifacts: int) -> dict:
    return {"execution": {"profile": "source.read", "workers": 1, "max_artifacts": max_artifacts},
            "read": {"format": "json", "limits": {"max_bytes": 1 << 20, "max_records": 1000},
                     "tables": {table: {"each": each, "columns": {"id": {"value": {"path": "id"}}}}}}}


FIRST = contract("rows", "items", 1)
RECORD = contract("record", "tables.rows", 512)


def first_reading(store: Artifacts, root: Path, count: int) -> dict:
    path = root / "input.json"
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": [{"id": f"id-{n}"} for n in range(count)]}))
    return read(store, root / "first", FIRST, [store.put_bytes(path.as_uri() + ".copy", path.read_bytes())], 1)


def by_pieces(store: Artifacts, root: Path, reading: dict) -> tuple[dict, dict, list[str]]:
    root.mkdir(parents=True, exist_ok=True)
    manifest = store.put(root.as_uri(), {"version": 4, "contract": store.put(root.as_uri(), RECORD), "pieces": reading})
    task = {"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}
    out = source_read.execute(task, store)
    assert source_read.verify({**task, "candidate": out}, store) == ({"source.output": True}, [])
    body, _ = source_read.source_readings.load(out, store, max_bytes=1 << 20, max_rows=1000)
    return task, out, [row["id"] for artifact in body["artifacts"] for row in artifact["tables"]["record"]]


def test_a_small_reading_is_read_from_its_inline_rows(tmp_path):
    store = Artifacts()
    reading = first_reading(store, tmp_path, 3)
    assert store.json(reading)["version"] == 1

    _, _, ids = by_pieces(store, tmp_path / "record", reading)

    assert ids == ["id-0", "id-1", "id-2"]


def test_a_large_reading_is_read_from_its_parts_with_the_same_rows(tmp_path, monkeypatch):
    store = Artifacts()
    monkeypatch.setattr(source_read, "OUTPUT_BYTES", 64)
    monkeypatch.setattr(source_read.source_readings, "PART_ROWS", 2)
    reading = first_reading(store, tmp_path, 5)
    assert store.json(reading)["version"] == 2

    _, _, ids = by_pieces(store, tmp_path / "record", reading)

    assert ids == [f"id-{n}" for n in range(5)]


def test_the_verifier_reads_an_inline_piece_back_by_its_hash(tmp_path):
    store = Artifacts()
    task, out, _ = by_pieces(store, tmp_path / "record", first_reading(store, tmp_path, 2))
    pieces = list((tmp_path / "record").glob("reading.json.pieces/*.json"))
    assert pieces
    pieces[0].write_text('{"version":1,"tables":{"rows":[{"id":"invented"}]},"deferred":[]}')

    with pytest.raises(ValueError):
        source_read.verify({**task, "candidate": out}, store)


def test_more_pieces_than_the_contract_allows_are_refused(tmp_path, monkeypatch):
    store = Artifacts()
    monkeypatch.setattr(source_read, "OUTPUT_BYTES", 64)
    monkeypatch.setattr(source_read.source_readings, "PART_ROWS", 1)
    reading = first_reading(store, tmp_path, 3)
    monkeypatch.setitem(RECORD["execution"], "max_artifacts", 2)

    with pytest.raises(ValueError, match="bounded artifact count"):
        by_pieces(store, tmp_path / "record", reading)
