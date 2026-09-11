"""Shared exclusive fence for derived filing-text writes and retirement apply."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import StorageLocation

FILING_TEXT_MUTATION_LOCK_PATH = "release/filing-text-retention/mutation.lock"


def _lock_payload(owner: str) -> bytes:
    if not owner.strip():
        raise WarehouseRuntimeError("filing-text mutation lock requires an owner")
    return (
        json.dumps(
            {"owner": owner, "acquired_at": datetime.now(UTC).isoformat()},
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


@contextmanager
def filing_text_mutation_lock(
    storage_root: StorageLocation, *, owner: str
) -> Iterator[None]:
    """Hold one fail-closed lock across a derived-text write or deletion."""
    payload = _lock_payload(owner)
    destination = storage_root.join(FILING_TEXT_MUTATION_LOCK_PATH)
    if not storage_root.is_remote:
        lock_path = Path(destination)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with lock_path.open("xb") as handle:
                handle.write(payload)
        except FileExistsError as exc:
            raise WarehouseRuntimeError(
                "filing-text mutation lock is already held"
            ) from exc
        try:
            yield
        finally:
            if lock_path.read_bytes() != payload:
                raise WarehouseRuntimeError(
                    "filing-text mutation lock ownership changed before release"
                )
            lock_path.unlink()
        return

    from botocore.exceptions import ClientError

    parsed = urlsplit(destination)
    client = storage_root._s3()
    try:
        response = client.put_object(
            Bucket=parsed.netloc,
            Key=parsed.path.lstrip("/"),
            Body=payload,
            ContentType="application/json",
            IfNoneMatch="*",
        )
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = exc.response.get("Error", {}).get("Code")
        if status in {409, 412} or code in {
            "ConditionalRequestConflict",
            "PreconditionFailed",
        }:
            raise WarehouseRuntimeError(
                "filing-text mutation lock is already held"
            ) from exc
        raise
    version_id = str(response.get("VersionId") or "")
    if not version_id:
        raise WarehouseRuntimeError(
            "filing-text mutation lock did not return a VersionId"
        )
    delete_request = {
        "Bucket": parsed.netloc,
        "Key": parsed.path.lstrip("/"),
        "VersionId": version_id,
    }
    try:
        yield
    finally:
        client.delete_object(**delete_request)
