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


def test_find_existing_matches_glob_across_date_segments(tmp_path):
    root = StorageLocation(str(tmp_path))
    (tmp_path / "submissions" / "sec" / "cik=320193" / "main" / "2026" / "01" / "01").mkdir(parents=True)
    (tmp_path / "submissions" / "sec" / "cik=320193" / "main" / "2026" / "01" / "01" / "CIK0000320193.json").write_text("{}")

    matches = root.find_existing("submissions/sec/cik=320193/main/*/*/*/CIK0000320193.json")

    assert len(matches) == 1
    assert matches[0].endswith("CIK0000320193.json")


def test_find_existing_returns_empty_when_no_match(tmp_path):
    root = StorageLocation(str(tmp_path))

    assert root.find_existing("submissions/sec/cik=320193/main/*/*/*/CIK0000320193.json") == []
