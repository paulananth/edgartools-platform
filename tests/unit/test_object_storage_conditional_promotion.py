from __future__ import annotations

import io
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import (
    ImmutableContentConflictError,
    PromotionConflictError,
    StorageLocation,
)


class _DeletingS3Client:
    def __init__(self) -> None:
        self.deletes: list[dict[str, str]] = []

    def delete_object(self, **kwargs):
        self.deletes.append(kwargs)
        return {}


class _ReadableObjectStore:
    def __init__(self, objects: dict[str, bytes], etags: dict[str, str]) -> None:
        self.objects = objects
        self.etags = etags

    def exists(self, path: str) -> bool:
        return path in self.objects

    def info(self, path: str) -> dict[str, str]:
        return {"ETag": self.etags[path]}

    def open(self, path: str, mode: str):
        assert mode == "rb"
        return io.BytesIO(self.objects[path])


class _RecordingS3Client:
    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        return {"ETag": '"new-etag"', "VersionId": "version-2"}


class _RejectingS3Client:
    def put_object(self, **kwargs):
        raise ClientError(
            {
                "Error": {"Code": "PreconditionFailed", "Message": "ETag changed"},
                "ResponseMetadata": {"HTTPStatusCode": 412},
            },
            "PutObject",
        )


class _StatefulS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts: list[dict[str, object]] = []

    def get_object(self, *, Bucket: str, Key: str):
        object_key = (Bucket, Key)
        if object_key not in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "NoSuchKey", "Message": "Not found"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "GetObject",
            )
        return {"Body": io.BytesIO(self.objects[object_key])}

    def put_object(self, **kwargs):
        object_key = (str(kwargs["Bucket"]), str(kwargs["Key"]))
        if kwargs.get("IfNoneMatch") == "*" and object_key in self.objects:
            raise ClientError(
                {
                    "Error": {
                        "Code": "PreconditionFailed",
                        "Message": "Already exists",
                    },
                    "ResponseMetadata": {"HTTPStatusCode": 412},
                },
                "PutObject",
            )
        self.puts.append(kwargs)
        self.objects[object_key] = bytes(kwargs["Body"])
        return {"ETag": '"new-etag"', "VersionId": f"version-{len(self.puts)}"}


def test_remote_immutable_write_reuses_identical_object_without_another_put(
    monkeypatch,
):
    client = _StatefulS3Client()
    monkeypatch.setattr("boto3.client", lambda service: client)
    storage = StorageLocation("s3://bucket/warehouse/bronze")

    artifact_key = "filings/sec/accession/primary.xml"
    first = storage.write_immutable_bytes(artifact_key, b"immutable")
    second = storage.write_immutable_bytes(artifact_key, b"immutable")

    assert first == "s3://bucket/warehouse/bronze/filings/sec/accession/primary.xml"
    assert second == first
    assert len(client.puts) == 1
    assert client.puts[0]["IfNoneMatch"] == "*"


def test_remote_immutable_write_rejects_different_content_at_existing_key(monkeypatch):
    client = _StatefulS3Client()
    monkeypatch.setattr("boto3.client", lambda service: client)
    storage = StorageLocation("s3://bucket/warehouse/bronze")

    storage.write_immutable_bytes("filings/sec/accession/primary.xml", b"immutable")

    with pytest.raises(ImmutableContentConflictError, match="different content") as excinfo:
        storage.write_immutable_bytes("filings/sec/accession/primary.xml", b"changed")

    # Ticket 25 bullet 1: both are retained, not just the original -- the
    # conflicting payload is quarantined to a second, content-addressed
    # object rather than discarded or silently overwriting the first.
    assert len(client.puts) == 2
    stored_key = ("bucket", "warehouse/bronze/filings/sec/accession/primary.xml")
    assert client.objects[stored_key] == b"immutable"
    error = excinfo.value
    quarantine_key = (
        "bucket",
        f"warehouse/bronze/{error.quarantine_relative_path}",
    )
    assert client.objects[quarantine_key] == b"changed"
    assert error.relative_path == "filings/sec/accession/primary.xml"
    assert error.new_content_hash in error.quarantine_relative_path


def test_local_immutable_write_rejects_different_content_at_existing_key(tmp_path):
    storage = StorageLocation(str(tmp_path))

    storage.write_immutable_bytes("filings/sec/accession/primary.xml", b"immutable")

    with pytest.raises(ImmutableContentConflictError, match="different content") as excinfo:
        storage.write_immutable_bytes("filings/sec/accession/primary.xml", b"changed")

    original = tmp_path / "filings" / "sec" / "accession" / "primary.xml"
    assert original.read_bytes() == b"immutable"

    error = excinfo.value
    quarantine = tmp_path / error.quarantine_relative_path
    assert quarantine.read_bytes() == b"changed"
    assert error.relative_path == "filings/sec/accession/primary.xml"
    assert error.existing_content_hash != error.new_content_hash


def test_local_immutable_write_conflict_is_idempotent_on_replay(tmp_path):
    """A replayed conflict (same new bytes arriving twice) quarantines the
    same content-addressed object cleanly rather than raising a second,
    unrelated error on the quarantine write itself."""

    storage = StorageLocation(str(tmp_path))
    storage.write_immutable_bytes("filings/sec/accession/primary.xml", b"immutable")

    with pytest.raises(ImmutableContentConflictError) as first:
        storage.write_immutable_bytes("filings/sec/accession/primary.xml", b"changed")
    with pytest.raises(ImmutableContentConflictError) as second:
        storage.write_immutable_bytes("filings/sec/accession/primary.xml", b"changed")

    assert first.value.quarantine_relative_path == second.value.quarantine_relative_path


def test_remote_promotion_atomically_requires_the_canonical_etag(monkeypatch):
    """A remote promotion must bind the write itself to the hydrated ETag."""
    objects = {
        "s3://bucket/warehouse/silver/sec/silver.duckdb": b"canonical",
        "s3://bucket/warehouse/silverstage/token/silver/sec/silver.duckdb": b"merged",
    }
    store = _ReadableObjectStore(
        objects,
        {"s3://bucket/warehouse/silver/sec/silver.duckdb": "old-etag"},
    )
    client = _RecordingS3Client()
    monkeypatch.setattr("fsspec.filesystem", lambda *args, **kwargs: store)
    monkeypatch.setattr("boto3.client", lambda service: client)

    result = StorageLocation("s3://bucket/warehouse").promote_staged(
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
    assert result.previous_version.etag == "old-etag"
    assert result.new_version.etag == "new-etag"
    assert result.new_version.version_id == "version-2"


def test_remote_first_promotion_atomically_requires_an_absent_canonical_key(monkeypatch):
    staged_path = "s3://bucket/warehouse/silverstage/token/silver/sec/silver.duckdb"
    store = _ReadableObjectStore({staged_path: b"first"}, {})
    client = _RecordingS3Client()
    monkeypatch.setattr("fsspec.filesystem", lambda *args, **kwargs: store)
    monkeypatch.setattr("boto3.client", lambda service: client)

    StorageLocation("s3://bucket/warehouse").promote_staged(
        "silverstage/token/silver/sec/silver.duckdb",
        "silver/sec/silver.duckdb",
        expected_etag=None,
    )

    assert client.puts[0]["IfNoneMatch"] == "*"
    assert "IfMatch" not in client.puts[0]


def test_remote_promotion_reports_atomic_precondition_failure_as_retryable_conflict(monkeypatch):
    staged_path = "s3://bucket/warehouse/silverstage/token/silver/sec/silver.duckdb"
    objects = {
        "s3://bucket/warehouse/silver/sec/silver.duckdb": b"newer-canonical",
        staged_path: b"merged",
    }
    store = _ReadableObjectStore(
        objects,
        {"s3://bucket/warehouse/silver/sec/silver.duckdb": "old-etag"},
    )
    monkeypatch.setattr("fsspec.filesystem", lambda *args, **kwargs: store)
    monkeypatch.setattr("boto3.client", lambda service: _RejectingS3Client())

    with pytest.raises(PromotionConflictError) as exc_info:
        StorageLocation("s3://bucket/warehouse").promote_staged(
            "silverstage/token/silver/sec/silver.duckdb",
            "silver/sec/silver.duckdb",
            expected_etag="old-etag",
        )

    assert exc_info.value.expected_etag == "old-etag"
    assert objects[staged_path] == b"merged"


def test_local_delete_object_removes_the_file(tmp_path):
    storage = StorageLocation(str(tmp_path))
    storage.write_bytes("silverstage/token/silver/sec/silver.duckdb", b"staged")
    target = Path(storage.join("silverstage/token/silver/sec/silver.duckdb"))
    assert target.exists()

    storage.delete_object("silverstage/token/silver/sec/silver.duckdb")

    assert not target.exists()


def test_local_delete_object_is_a_noop_for_a_missing_file(tmp_path):
    storage = StorageLocation(str(tmp_path))
    # No prior write -- must not raise.
    storage.delete_object("silverstage/does-not-exist/silver.duckdb")


def test_remote_delete_object_calls_s3_delete_object(monkeypatch):
    client = _DeletingS3Client()
    monkeypatch.setattr("boto3.client", lambda service: client)
    storage = StorageLocation("s3://bucket/warehouse")

    storage.delete_object("silverstage/token/silver/sec/silver.duckdb")

    assert client.deletes == [
        {"Bucket": "bucket", "Key": "warehouse/silverstage/token/silver/sec/silver.duckdb"}
    ]


def test_remote_delete_object_passes_an_etag_precondition(monkeypatch):
    client = _DeletingS3Client()
    monkeypatch.setattr("boto3.client", lambda service: client)
    storage = StorageLocation("s3://bucket/warehouse")

    storage.delete_object("release/cleanup.lock", expected_etag="owner-etag")

    assert client.deletes == [
        {
            "Bucket": "bucket",
            "Key": "warehouse/release/cleanup.lock",
            "IfMatch": "owner-etag",
        }
    ]
