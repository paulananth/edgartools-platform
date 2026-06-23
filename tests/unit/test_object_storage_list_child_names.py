"""Tests for StorageLocation.list_child_names (local filesystem backend)."""
from __future__ import annotations

from edgar_warehouse.infrastructure.object_storage import StorageLocation


def test_list_child_names_returns_immediate_children(tmp_path):
    root = StorageLocation(str(tmp_path))
    (tmp_path / "submissions" / "sec" / "cik=320193").mkdir(parents=True)
    (tmp_path / "submissions" / "sec" / "cik=789019").mkdir(parents=True)

    names = root.list_child_names("submissions/sec")

    assert sorted(names) == ["cik=320193", "cik=789019"]


def test_list_child_names_returns_empty_when_path_missing(tmp_path):
    root = StorageLocation(str(tmp_path))

    assert root.list_child_names("submissions/sec") == []


def test_list_child_names_returns_empty_when_dir_empty(tmp_path):
    root = StorageLocation(str(tmp_path))
    (tmp_path / "submissions" / "sec").mkdir(parents=True)

    assert root.list_child_names("submissions/sec") == []
