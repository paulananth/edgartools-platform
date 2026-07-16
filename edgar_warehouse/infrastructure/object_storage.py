"""Typed storage adapter with path-safety guards."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from edgar_warehouse.application.errors import WarehouseRuntimeError

ALLOWED_REMOTE_PROTOCOLS = frozenset({"s3"})


class PromotionConflictError(WarehouseRuntimeError):
    """Raised when the canonical object changed since its version/ETag baseline was read.

    Retryable: the staged object is left in place (never deleted on conflict)
    so a caller can re-read canonical, re-merge, and retry promotion.
    """

    def __init__(
        self,
        canonical_relative_path: str,
        expected_etag: str | None,
        actual_etag: str | None,
        staged_relative_path: str,
    ) -> None:
        self.canonical_relative_path = canonical_relative_path
        self.expected_etag = expected_etag
        self.actual_etag = actual_etag
        self.staged_relative_path = staged_relative_path
        super().__init__(
            f"canonical object {canonical_relative_path!r} changed during publication "
            f"(expected ETag {expected_etag!r}, found {actual_etag!r}); staged candidate "
            f"preserved at {staged_relative_path!r} for retry"
        )


@dataclass(frozen=True)
class ObjectVersion:
    exists: bool
    etag: str | None
    version_id: str | None


@dataclass(frozen=True)
class PromotionResult:
    canonical_path: str
    staged_relative_path: str
    previous_version: "ObjectVersion"
    new_version: "ObjectVersion"


def sanitize_relative_path(relative_path: str) -> str:
    candidate = str(relative_path or "").strip().replace("\\", "/")
    if not candidate:
        raise WarehouseRuntimeError("relative storage path must not be empty")
    path = PurePosixPath(candidate)
    if path.is_absolute():
        raise WarehouseRuntimeError(f"absolute storage paths are not allowed: {relative_path}")
    cleaned_parts: list[str] = []
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise WarehouseRuntimeError(f"path traversal is not allowed: {relative_path}")
        cleaned_parts.append(part)
    if not cleaned_parts:
        raise WarehouseRuntimeError("relative storage path must not resolve to empty")
    return "/".join(cleaned_parts)


def sanitize_filename(filename: str) -> str:
    candidate = str(filename or "").strip().replace("\\", "/")
    if not candidate:
        raise WarehouseRuntimeError("document name must not be empty")
    name = PurePosixPath(candidate).name
    if name in {"", ".", ".."}:
        raise WarehouseRuntimeError(f"invalid document name: {filename}")
    return name


def _protocol_for_uri(uri: str) -> str | None:
    if "://" not in uri:
        return None
    return uri.split("://", 1)[0].lower()


def _assert_protocol_allowed(protocol: str | None) -> None:
    if protocol is None:
        return
    if protocol not in ALLOWED_REMOTE_PROTOCOLS:
        raise WarehouseRuntimeError(f"unsupported storage protocol: {protocol}")


def _remote_storage_options(storage_path: str) -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class StorageLocation:
    """A storage root that can point to a local path or approved cloud URI."""

    root: str

    def __post_init__(self) -> None:
        normalized = str(self.root or "").strip()
        if not normalized:
            raise WarehouseRuntimeError("storage root must not be empty")
        protocol = _protocol_for_uri(normalized)
        _assert_protocol_allowed(protocol)
        object.__setattr__(self, "root", normalized.rstrip("/\\"))

    @property
    def is_remote(self) -> bool:
        return "://" in self.root

    def join(self, *parts: str) -> str:
        relative = sanitize_relative_path("/".join(str(part or "").strip("/\\") for part in parts if part))
        if self.is_remote:
            return f"{self.root}/{relative}"
        return str(Path(self.root).joinpath(*PurePosixPath(relative).parts))

    def write_json(self, relative_path: str, payload: dict[str, Any]) -> str:
        return self.write_text(relative_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def write_text(self, relative_path: str, payload: str) -> str:
        return self.write_bytes(relative_path, payload.encode("utf-8"))

    def upload_file(self, relative_path: str, local_path: "Path", chunk_size: int = 8 * 1024 * 1024) -> str:
        """Stream a local file to storage without loading it fully into memory."""
        import shutil
        relative = sanitize_relative_path(relative_path)
        destination = self.join(relative)
        if self.is_remote:
            protocol = _protocol_for_uri(self.root)
            _assert_protocol_allowed(protocol)
            import fsspec
            fs = fsspec.filesystem(protocol, **_remote_storage_options(destination))
            with local_path.open("rb") as src, fs.open(destination, "wb") as dst:
                shutil.copyfileobj(src, dst, length=chunk_size)
            return destination
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(local_path), str(destination_path))
        return str(destination_path)

    def list_child_names(self, relative_path: str) -> list[str]:
        """List immediate child names (files or directories) under relative_path.

        Returns an empty list if relative_path does not exist — callers that
        need to distinguish "doesn't exist yet" from "exists but empty" should
        check existence separately.
        """
        relative = sanitize_relative_path(relative_path)
        base = self.join(relative)
        if self.is_remote:
            protocol = _protocol_for_uri(self.root)
            _assert_protocol_allowed(protocol)
            import fsspec

            fs = fsspec.filesystem(protocol, **_remote_storage_options(base))
            if not fs.exists(base):
                return []
            entries = fs.ls(base, detail=False)
            return [entry.rstrip("/").rsplit("/", 1)[-1] for entry in entries]
        base_path = Path(base)
        if not base_path.is_dir():
            return []
        return [child.name for child in base_path.iterdir()]

    def find_existing(self, relative_glob: str) -> list[str]:
        """Return full storage paths matching a glob pattern (`*` wildcards, no `**`).

        Used to locate a previously-captured object by content key (e.g. CIK) without
        knowing the exact date-keyed path segment it was written under. Returned paths
        are suitable for passing directly to read_bytes().
        """
        relative = sanitize_relative_path(relative_glob)
        pattern = self.join(relative)
        if self.is_remote:
            protocol = _protocol_for_uri(self.root)
            _assert_protocol_allowed(protocol)
            import fsspec

            fs = fsspec.filesystem(protocol, **_remote_storage_options(pattern))
            matches = fs.glob(pattern)
            return sorted(
                match if "://" in match else f"{protocol}://{match}" for match in matches
            )
        import glob as glob_module

        return sorted(glob_module.glob(pattern))

    def read_object_version(self, relative_path: str) -> "ObjectVersion":
        """Current version/ETag of an object.

        Used as the optimistic-concurrency baseline: a caller reads this
        before staging a merge candidate, then ``promote_staged`` reads it
        again immediately before committing and refuses to promote if it
        changed. Local (non-remote) storage has no real object versioning;
        an MD5 content digest (matching S3's own default single-part ETag
        scheme) stands in as a deterministic equivalent so the same
        compare-before-promote logic is exercisable in local/dev/test runs.
        """
        relative = sanitize_relative_path(relative_path)
        destination = self.join(relative)
        if self.is_remote:
            protocol = _protocol_for_uri(self.root)
            _assert_protocol_allowed(protocol)
            import fsspec

            fs = fsspec.filesystem(protocol, **_remote_storage_options(destination))
            if not fs.exists(destination):
                return ObjectVersion(exists=False, etag=None, version_id=None)
            info = fs.info(destination)
            raw_etag = info.get("ETag") or info.get("etag")
            etag = str(raw_etag).strip('"') if raw_etag else None
            version_id = info.get("VersionId") or info.get("version_id")
            return ObjectVersion(exists=True, etag=etag, version_id=version_id)

        destination_path = Path(destination)
        if not destination_path.exists():
            return ObjectVersion(exists=False, etag=None, version_id=None)
        import hashlib

        digest = hashlib.md5(destination_path.read_bytes()).hexdigest()
        return ObjectVersion(exists=True, etag=digest, version_id=None)

    def write_staged_bytes(self, canonical_relative_path: str, payload: bytes) -> str:
        """Write payload under a fresh, immutable staging key.

        The staging key embeds a random token so it never collides with the
        canonical key or with any other concurrent staged write. Returns the
        relative staging path (pass it to ``promote_staged``).
        """
        import uuid

        canonical_relative = sanitize_relative_path(canonical_relative_path)
        staged_relative = f"_staging/{uuid.uuid4().hex}/{canonical_relative}"
        self.write_bytes(staged_relative, payload)
        return staged_relative

    def promote_staged(
        self,
        staged_relative_path: str,
        canonical_relative_path: str,
        *,
        expected_etag: str | None,
    ) -> "PromotionResult":
        """Promote a staged object onto the canonical key -- but only if
        canonical's current version/ETag still equals ``expected_etag``.

        Raises ``PromotionConflictError`` (leaving the staged object in place
        for inspection/retry) if canonical changed since ``expected_etag`` was
        read. Never silently last-writer-wins.
        """
        canonical_relative = sanitize_relative_path(canonical_relative_path)
        previous = self.read_object_version(canonical_relative)
        if previous.etag != expected_etag:
            raise PromotionConflictError(
                canonical_relative, expected_etag, previous.etag, staged_relative_path
            )

        staged_bytes = read_bytes(self.join(sanitize_relative_path(staged_relative_path)))
        canonical_path_str = self.write_bytes(canonical_relative, staged_bytes)
        new_version = self.read_object_version(canonical_relative)
        return PromotionResult(
            canonical_path=canonical_path_str,
            staged_relative_path=staged_relative_path,
            previous_version=previous,
            new_version=new_version,
        )

    def write_bytes(self, relative_path: str, payload: bytes) -> str:
        relative = sanitize_relative_path(relative_path)
        destination = self.join(relative)
        if self.is_remote:
            protocol = _protocol_for_uri(self.root)
            _assert_protocol_allowed(protocol)
            import fsspec

            fs = fsspec.filesystem(protocol, **_remote_storage_options(destination))
            with fs.open(destination, "wb") as handle:
                handle.write(payload)
            return destination

        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(payload)
        return str(destination_path)


def read_bytes(storage_path: str) -> bytes:
    protocol = _protocol_for_uri(storage_path)
    if protocol is None:
        return Path(storage_path).read_bytes()
    _assert_protocol_allowed(protocol)
    import fsspec

    fs = fsspec.filesystem(protocol, **_remote_storage_options(storage_path))
    with fs.open(storage_path, "rb") as handle:
        return handle.read()
