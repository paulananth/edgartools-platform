from __future__ import annotations

import io

import pytest
from botocore.exceptions import ClientError

from edgar_warehouse.infrastructure.object_storage import PromotionConflictError, StorageLocation


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


def test_remote_promotion_atomically_requires_the_canonical_etag(monkeypatch):
    """A remote promotion must bind the write itself to the hydrated ETag."""
    objects = {
        "s3://bucket/warehouse/silver/sec/silver.duckdb": b"canonical",
        "s3://bucket/warehouse/_staging/token/silver/sec/silver.duckdb": b"merged",
    }
    store = _ReadableObjectStore(
        objects,
        {"s3://bucket/warehouse/silver/sec/silver.duckdb": "old-etag"},
    )
    client = _RecordingS3Client()
    monkeypatch.setattr("fsspec.filesystem", lambda *args, **kwargs: store)
    monkeypatch.setattr("boto3.client", lambda service: client)

    result = StorageLocation("s3://bucket/warehouse").promote_staged(
        "_staging/token/silver/sec/silver.duckdb",
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
    staged_path = "s3://bucket/warehouse/_staging/token/silver/sec/silver.duckdb"
    store = _ReadableObjectStore({staged_path: b"first"}, {})
    client = _RecordingS3Client()
    monkeypatch.setattr("fsspec.filesystem", lambda *args, **kwargs: store)
    monkeypatch.setattr("boto3.client", lambda service: client)

    StorageLocation("s3://bucket/warehouse").promote_staged(
        "_staging/token/silver/sec/silver.duckdb",
        "silver/sec/silver.duckdb",
        expected_etag=None,
    )

    assert client.puts[0]["IfNoneMatch"] == "*"
    assert "IfMatch" not in client.puts[0]


def test_remote_promotion_reports_atomic_precondition_failure_as_retryable_conflict(monkeypatch):
    staged_path = "s3://bucket/warehouse/_staging/token/silver/sec/silver.duckdb"
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
            "_staging/token/silver/sec/silver.duckdb",
            "silver/sec/silver.duckdb",
            expected_etag="old-etag",
        )

    assert exc_info.value.expected_etag == "old-etag"
    assert objects[staged_path] == b"merged"
