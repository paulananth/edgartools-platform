"""Tests for StorageLocation.download_file (seed-universe-narrow-hydrate ticket 04).

_hydrate_silver_database_from_storage previously buffered the entire remote
silver.duckdb into one Python bytes value (read_bytes()) before writing it to
local disk -- the confirmed shared root cause behind four separate live OOMs
(Stage0CompanyIdentity, ComputeWindows, gold-refresh, seed-universe). This
file locks in download_file's streaming behavior: it must never hold the
whole object in memory as one value.
"""

from __future__ import annotations

import io

import pytest
from unittest.mock import MagicMock, patch

from edgar_warehouse.infrastructure.object_storage import StorageLocation


def test_download_file_local_storage_copies_file(tmp_path):
    root = StorageLocation(str(tmp_path / "root"))
    source = tmp_path / "root" / "silver" / "sec" / "silver.duckdb"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"hello world")

    dest = tmp_path / "local" / "silver.duckdb"
    result = root.download_file("silver/sec/silver.duckdb", dest)

    assert dest.read_bytes() == b"hello world"
    assert result == str(dest)


def test_download_file_missing_local_source_raises(tmp_path):
    root = StorageLocation(str(tmp_path / "root"))
    dest = tmp_path / "local" / "silver.duckdb"
    with pytest.raises(FileNotFoundError):
        root.download_file("silver/sec/silver.duckdb", dest)


class _RecordingReadHandle(io.BytesIO):
    """Tracks every read() call's requested size, so a test can assert the
    download never issues an unbounded whole-object read()."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.read_sizes: list[int | None] = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_file_remote_storage_streams_in_bounded_chunks(tmp_path):
    payload = b"x" * (5 * 1024 * 1024)
    handle = _RecordingReadHandle(payload)

    fake_fs = MagicMock()
    fake_fs.open.return_value = handle

    root = StorageLocation("s3://bucket/warehouse")
    dest = tmp_path / "local" / "silver.duckdb"

    with patch("fsspec.filesystem", return_value=fake_fs):
        result = root.download_file(
            "silver/sec/silver.duckdb", dest, chunk_size=1024 * 1024
        )

    assert dest.read_bytes() == payload
    assert result == str(dest)
    # The bug this method fixes is exactly an unbounded read() that returns
    # the whole object as one value -- assert every read() call was bounded
    # by chunk_size, never size=-1/None (the "give me everything" signature).
    assert handle.read_sizes, "expected at least one bounded read() call"
    assert all(size not in (-1, None) for size in handle.read_sizes)
    for size in handle.read_sizes[:-1]:
        assert size == 1024 * 1024


def test_download_file_raises_file_not_found_when_remote_object_missing(tmp_path):
    fake_fs = MagicMock()
    fake_fs.open.side_effect = FileNotFoundError("no such object")

    root = StorageLocation("s3://bucket/warehouse")
    dest = tmp_path / "local" / "silver.duckdb"

    with patch("fsspec.filesystem", return_value=fake_fs):
        with pytest.raises(FileNotFoundError):
            root.download_file("silver/sec/silver.duckdb", dest)
