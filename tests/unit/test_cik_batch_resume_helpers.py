"""CIK-batch resume helpers shared with the default Clean and Merge Filings resume.

Originally Ticket 20's release-batch tests; silver-merge-engine-migration Ticket 11
deleted release mode and kept only the helpers batch_silver_resume still uses."""

from __future__ import annotations

import json
from pathlib import Path


from edgar_warehouse.application.relationship_bulk_load import (
    batch_identity_for_ciks,
    build_remaining_cik_batches,
    list_done_batch_identities,
    parse_cik_batches_jsonl,
)
from edgar_warehouse.infrastructure.object_storage import (
    list_uri_child_names,
    write_uri_text,
)


def test_batch_identity_is_stable_and_order_independent() -> None:
    assert batch_identity_for_ciks([3, 1, 2]) == batch_identity_for_ciks(["2", "1", "3"])
    assert len(batch_identity_for_ciks([1, 2])) == 16


def test_build_remaining_cik_batches_drops_done() -> None:
    batches = [
        {"cik_list": "1,2"},
        {"cik_list": "3,4"},
        {"cik_list": "5"},
    ]
    done = {batch_identity_for_ciks([1, 2]), batch_identity_for_ciks([5])}
    remaining = build_remaining_cik_batches(batches, done)
    assert remaining == [{"cik_list": "3,4"}]


def test_parse_cik_batches_jsonl_and_marker_names(tmp_path: Path) -> None:
    identity = batch_identity_for_ciks([10, 20])
    rows = parse_cik_batches_jsonl('{"cik_list":"10,20"}\n{"cik_list":"30"}\n')
    assert len(rows) == 2
    done = list_done_batch_identities([f"{identity}.json", "not-a-marker.txt", "zz.json"])
    assert done == {identity}


def test_list_uri_child_names_local(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "b.json").write_text("{}", encoding="utf-8")
    names = list_uri_child_names(str(tmp_path))
    assert set(names) == {"a.json", "b.json"}


def test_write_uri_text_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "marker.json"
    write_uri_text(str(target), '{"ok":true}\n')
    assert json.loads(target.read_text(encoding="utf-8"))["ok"] is True


