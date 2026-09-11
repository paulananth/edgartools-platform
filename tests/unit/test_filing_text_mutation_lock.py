from __future__ import annotations

from pathlib import Path

import pytest

from edgar_warehouse.filing_text_projection import extract_text_for_accession
from edgar_warehouse.infrastructure.filing_text_mutation_lock import (
    FILING_TEXT_MUTATION_LOCK_PATH,
    filing_text_mutation_lock,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def test_local_filing_text_lock_is_exclusive_and_released(tmp_path: Path) -> None:
    storage = StorageLocation(str(tmp_path))

    with filing_text_mutation_lock(storage, owner="writer:run-1"):
        assert Path(storage.join(FILING_TEXT_MUTATION_LOCK_PATH)).exists()
        with pytest.raises(
            RuntimeError, match="already held"
        ), filing_text_mutation_lock(storage, owner="apply:plan-1"):
            pass

    assert not Path(storage.join(FILING_TEXT_MUTATION_LOCK_PATH)).exists()


def test_local_filing_text_lock_releases_after_failure(tmp_path: Path) -> None:
    storage = StorageLocation(str(tmp_path))

    with pytest.raises(
        ValueError, match="boom"
    ), filing_text_mutation_lock(storage, owner="writer:run-1"):
        raise ValueError("boom")

    with filing_text_mutation_lock(storage, owner="writer:run-2"):
        assert Path(storage.join(FILING_TEXT_MUTATION_LOCK_PATH)).exists()


def test_projection_writer_honors_the_same_mutation_lock(tmp_path: Path) -> None:
    storage = StorageLocation(str(tmp_path))
    context = type("Context", (), {"storage_root": storage})()

    with filing_text_mutation_lock(storage, owner="apply:plan-1"), pytest.raises(
        RuntimeError, match="already held"
    ):
        extract_text_for_accession(
            context=context,
            db=object(),
            accession_number="0000910001-24-000001",
            sync_run_id="run-1",
        )


class _RemoteLockClient:
    def __init__(self, *, version_id: str | None) -> None:
        self.version_id = version_id
        self.puts: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> dict[str, str]:
        self.puts.append(kwargs)
        return {"VersionId": self.version_id} if self.version_id else {}

    def delete_object(self, **kwargs: object) -> None:
        self.deletes.append(kwargs)


def test_remote_filing_text_lock_requires_versioned_exact_release(monkeypatch) -> None:
    client = _RemoteLockClient(version_id=None)
    monkeypatch.setattr("boto3.client", lambda service: client)
    storage = StorageLocation("s3://bucket/warehouse")

    with pytest.raises(
        RuntimeError, match="did not return a VersionId"
    ), filing_text_mutation_lock(storage, owner="writer:run-1"):
        pytest.fail("an unversioned lock must not be considered acquired")

    assert client.deletes == []


def test_remote_filing_text_lock_releases_its_exact_version(monkeypatch) -> None:
    client = _RemoteLockClient(version_id="lock-version-1")
    monkeypatch.setattr("boto3.client", lambda service: client)
    storage = StorageLocation("s3://bucket/warehouse")

    with filing_text_mutation_lock(storage, owner="writer:run-1"):
        pass

    assert client.puts[0]["IfNoneMatch"] == "*"
    assert client.deletes == [
        {
            "Bucket": "bucket",
            "Key": "warehouse/release/filing-text-retention/mutation.lock",
            "VersionId": "lock-version-1",
        }
    ]
