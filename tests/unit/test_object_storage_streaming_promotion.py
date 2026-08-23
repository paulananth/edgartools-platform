"""Streaming Path payload support for staged writes and promotion.

seed-universe-narrow-hydrate ticket 06: ``write_bytes``/``write_staged_bytes``/
``promote_staged``/``stage_and_promote`` previously accepted only ``bytes``,
forcing every caller to fully buffer a payload into memory before calling
them -- the root cause of a live seed-universe OOM (canonical silver.duckdb
re-download + merged-file read + promote_staged's own internal re-read, all
non-streaming). These tests lock in the ``bytes | Path`` widening: a ``Path``
payload streams through (no full in-memory buffer, no redundant re-download
of an object the caller already has on disk), while every existing bytes
caller's behavior -- including the exact ``put_object`` call shape asserted
in test_object_storage_conditional_promotion.py -- is unchanged.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from edgar_warehouse.infrastructure.object_storage import (
    ObjectVersion,
    StorageLocation,
)


class _ReadableObjectStore:
    def __init__(self, objects: dict[str, bytes], etags: dict[str, str]) -> None:
        self.objects = objects
        self.etags = etags
        self.open_calls: list[str] = []

    def exists(self, path: str) -> bool:
        return path in self.objects

    def info(self, path: str) -> dict[str, str]:
        return {"ETag": self.etags[path]}

    def open(self, path: str, mode: str):
        self.open_calls.append(path)
        assert mode == "rb"
        return io.BytesIO(self.objects[path])


class _RecordingS3Client:
    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []

    def put_object(self, **kwargs):
        # Consume the Body now (as botocore would) so the caller's file
        # handle is proven readable, then record what was actually sent.
        body = kwargs.get("Body")
        content = body.read() if hasattr(body, "read") else body
        recorded = dict(kwargs)
        recorded["Body"] = content
        self.puts.append(recorded)
        return {"ETag": '"new-etag"', "VersionId": "version-2"}


def test_write_bytes_streams_a_path_without_reading_it_fully_into_memory(tmp_path, monkeypatch):
    source = tmp_path / "source.bin"
    payload = b"x" * (1024 * 64)
    source.write_bytes(payload)

    def _forbidden_read_bytes(self):
        raise AssertionError("write_bytes must not fully buffer a Path payload via Path.read_bytes()")

    monkeypatch.setattr(Path, "read_bytes", _forbidden_read_bytes)

    storage = StorageLocation(str(tmp_path / "dest-root"))
    result = storage.write_bytes("silver/sec/silver.duckdb", source)

    with open(result, "rb") as handle:
        assert handle.read() == payload


def test_write_staged_bytes_accepts_a_path_payload(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"staged-content")

    storage = StorageLocation(str(tmp_path / "dest-root"))
    staged_relative = storage.write_staged_bytes("silver/sec/silver.duckdb", source)

    assert Path(storage.join(staged_relative)).read_bytes() == b"staged-content"


def test_promote_staged_with_path_payload_streams_and_skips_the_staged_reread(monkeypatch, tmp_path):
    """When the caller already has the local file, promote_staged must not
    re-download the object it (or its caller) just uploaded."""
    local_payload = tmp_path / "merged.duckdb"
    local_payload.write_bytes(b"merged-content")

    store = _ReadableObjectStore(
        {"s3://bucket/warehouse/silver/sec/silver.duckdb": b"canonical"},
        {"s3://bucket/warehouse/silver/sec/silver.duckdb": "old-etag"},
    )
    client = _RecordingS3Client()
    monkeypatch.setattr("fsspec.filesystem", lambda *args, **kwargs: store)
    monkeypatch.setattr("boto3.client", lambda service: client)

    result = StorageLocation("s3://bucket/warehouse").promote_staged(
        "silverstage/token/silver/sec/silver.duckdb",
        "silver/sec/silver.duckdb",
        expected_etag="old-etag",
        payload=local_payload,
    )

    # The staged key itself was never opened for read -- proves promote_staged
    # used the caller-supplied local file instead of re-downloading.
    assert store.open_calls == []
    assert client.puts == [
        {
            "Bucket": "bucket",
            "Key": "warehouse/silver/sec/silver.duckdb",
            "Body": b"merged-content",
            "ContentLength": len(b"merged-content"),
            "IfMatch": "old-etag",
        }
    ]
    assert result.new_version.etag == "new-etag"


def test_promote_staged_bytes_payload_call_shape_is_unchanged(monkeypatch):
    """Regression guard: the pre-existing bytes-only call shape (no payload
    kwarg, no ContentLength) must be byte-for-byte identical to before this
    fix -- test_object_storage_conditional_promotion.py's
    test_remote_promotion_atomically_requires_the_canonical_etag already
    covers this; this is a second, narrower confirmation scoped to this
    file's own regression story."""
    store = _ReadableObjectStore(
        {
            "s3://bucket/warehouse/silver/sec/silver.duckdb": b"canonical",
            "s3://bucket/warehouse/silverstage/token/silver/sec/silver.duckdb": b"merged",
        },
        {"s3://bucket/warehouse/silver/sec/silver.duckdb": "old-etag"},
    )
    client = _RecordingS3Client()
    monkeypatch.setattr("fsspec.filesystem", lambda *args, **kwargs: store)
    monkeypatch.setattr("boto3.client", lambda service: client)

    StorageLocation("s3://bucket/warehouse").promote_staged(
        "silverstage/token/silver/sec/silver.duckdb",
        "silver/sec/silver.duckdb",
        expected_etag="old-etag",
    )

    assert client.puts == [
        {
            "Bucket": "bucket",
            "Key": "warehouse/silver/sec/silver.duckdb",
            "Body": b"merged",
            "IfMatch": "old-etag",
        }
    ]


def test_stage_and_promote_with_path_payload_never_rereads_the_staged_object(monkeypatch, tmp_path):
    """End-to-end: stage_and_promote's own upload must not be followed by a
    redundant full re-download of what it just uploaded, when the caller
    passes the local file it already has on disk."""
    local_payload = tmp_path / "merged.duckdb"
    local_payload.write_bytes(b"merged-content")

    written: dict[str, bytes] = {
        "s3://bucket/warehouse/silver/sec/silver.duckdb": b"canonical",
    }
    etags = {"s3://bucket/warehouse/silver/sec/silver.duckdb": "old-etag"}

    class _WritableStore(_ReadableObjectStore):
        def open(self, path: str, mode: str):
            if mode == "wb":
                buf = io.BytesIO()
                real_close = buf.close

                def _close():
                    written[path] = buf.getvalue()
                    real_close()

                buf.close = _close
                return buf
            return super().open(path, mode)

    store = _WritableStore(written, etags)
    client = _RecordingS3Client()
    monkeypatch.setattr("fsspec.filesystem", lambda *args, **kwargs: store)
    monkeypatch.setattr("boto3.client", lambda service: client)

    result = StorageLocation("s3://bucket/warehouse").stage_and_promote(
        "silver/sec/silver.duckdb", local_payload, expected_etag="old-etag"
    )

    # The staging upload happened (write_staged_bytes -> write_bytes ->
    # upload_file), but the staged object was never read back before promoting.
    staged_read_calls = [p for p in store.open_calls if p == result.staged_relative_path or "silverstage" in p]
    assert staged_read_calls == []
    assert client.puts[0]["Body"] == b"merged-content"
