"""Typed storage adapter with path-safety guards."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from edgar_warehouse.application.errors import WarehouseRuntimeError

ALLOWED_REMOTE_PROTOCOLS = frozenset({"s3"})


@contextlib.contextmanager
def _put_object_body(source: "bytes | Path"):
    """Yield (body, extra_put_object_kwargs) for a conditional S3 put.

    A ``bytes`` source passes through unchanged with no extra kwargs --
    this preserves the exact ``put_object`` call shape (no ``ContentLength``
    key) that existing callers assert byte-for-byte
    (test_object_storage_conditional_promotion.py). A ``Path`` source opens
    a real file handle and supplies an explicit ``ContentLength`` so
    ``promote_staged`` can hand botocore a stream instead of buffering the
    whole file into memory first (seed-universe-narrow-hydrate ticket 06 --
    this is the boundary that OOM'd a production `seed-universe` task after
    an unrelated merge-scoping fix had already made the merge step itself
    provably correct).
    """
    if isinstance(source, Path):
        handle = source.open("rb")
        try:
            yield handle, {"ContentLength": source.stat().st_size}
        finally:
            handle.close()
    else:
        yield source, {}


class ImmutableContentConflictError(WarehouseRuntimeError):
    """Different bytes arrived for one immutable Bronze identity (Ticket 25 bullet 1).

    Raised by ``write_immutable_bytes`` when a new payload does not match the
    content already stored at ``relative_path`` -- this only happens for an
    identity-keyed path (e.g. one accession/document), never a content-hash-
    keyed path (where different bytes always land at a different key by
    construction). The new payload is never silently discarded and never
    silently replaces the existing one: it is written, unchanged, to
    ``quarantine_relative_path`` -- a content-addressed sibling location keyed
    by its own hash, so it is genuinely retained -- before this is raised.
    Neither arrival order nor a mutable "latest" pointer picks a winner here;
    a caller with ledger access is expected to catch this and record a
    conflict (``acquisition/conflict.py``) for operator repair.
    """

    def __init__(
        self,
        relative_path: str,
        existing_content_hash: str,
        new_content_hash: str,
        quarantine_relative_path: str,
    ) -> None:
        self.relative_path = relative_path
        self.existing_content_hash = existing_content_hash
        self.new_content_hash = new_content_hash
        self.quarantine_relative_path = quarantine_relative_path
        super().__init__(
            f"immutable object {relative_path!r} already exists with different "
            f"content (existing={existing_content_hash!r}, new={new_content_hash!r}); "
            f"new content quarantined at {quarantine_relative_path!r}"
        )


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
        object.__setattr__(self, "_s3_client", None)

    def _s3(self) -> Any:
        """Lazily create and cache one boto3 S3 client for this instance's lifetime.

        A fresh boto3.client("s3") per call discards its connection pool, so
        every request pays a cold TCP+TLS handshake instead of reusing a warm
        keep-alive connection. Measured live against the real prod bronze
        bucket (ticket 69): 184ms/call fresh vs 52.6ms/call reused -- this
        was the dominant cost in the per-document artifact-fetch loop
        (bronze_filing_artifacts.py calls write_immutable_bytes once per
        document, thousands of times per run), not the SEC fetch itself.
        Single-threaded call sites only (no concurrency in this loop), so
        instance-level caching needs no locking.
        """
        if self._s3_client is None:
            import boto3

            object.__setattr__(self, "_s3_client", boto3.client("s3"))
        return self._s3_client

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

    def download_file(self, relative_path: str, local_path: "Path", chunk_size: int = 8 * 1024 * 1024) -> str:
        """Stream storage to a local file without loading it fully into memory.

        Mirrors ``upload_file``'s streaming pattern in the opposite direction.
        Raises ``FileNotFoundError`` if the source object does not exist.
        """
        import shutil
        relative = sanitize_relative_path(relative_path)
        source = self.join(relative)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if self.is_remote:
            protocol = _protocol_for_uri(self.root)
            _assert_protocol_allowed(protocol)
            import fsspec
            fs = fsspec.filesystem(protocol, **_remote_storage_options(source))
            with fs.open(source, "rb") as src, local_path.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=chunk_size)
            return str(local_path)
        source_path = Path(source)
        shutil.copy2(str(source_path), str(local_path))
        return str(local_path)

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

    def write_staged_bytes(self, canonical_relative_path: str, payload: "bytes | Path") -> str:
        """Write payload under a fresh, immutable staging key.

        The staging key embeds a random token so it never collides with the
        canonical key or with any other concurrent staged write. Returns the
        relative staging path (pass it to ``promote_staged``).

        ``payload`` may be raw bytes or a local ``Path`` -- passing a ``Path``
        streams the write instead of buffering the whole file into memory
        (seed-universe-narrow-hydrate ticket 06).
        """
        import uuid

        canonical_relative = sanitize_relative_path(canonical_relative_path)
        staged_relative = f"silverstage/{uuid.uuid4().hex}/{canonical_relative}"
        self.write_bytes(staged_relative, payload)
        return staged_relative

    def write_immutable_bytes(self, relative_path: str, payload: bytes) -> str:
        """Create an immutable object once, or reuse identical existing content.

        The conditional create prevents a retry, replay, or concurrent writer
        from creating another S3 version for the same logical artifact key.
        Existing content is read and compared byte-for-byte; a different payload
        at the same key fails closed instead of overwriting immutable data.
        """
        relative = sanitize_relative_path(relative_path)
        destination = self.join(relative)
        if self.is_remote:
            import base64
            import hashlib
            from urllib.parse import urlsplit

            from botocore.exceptions import ClientError

            parsed = urlsplit(destination)
            client = self._s3()
            checksum_sha256 = base64.b64encode(
                hashlib.sha256(payload).digest()
            ).decode("ascii")
            request = {
                "Bucket": parsed.netloc,
                "Key": parsed.path.lstrip("/"),
                "Body": payload,
                "ChecksumSHA256": checksum_sha256,
                "IfNoneMatch": "*",
            }
            try:
                client.put_object(**request)
                return destination
            except ClientError as exc:
                status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                code = exc.response.get("Error", {}).get("Code")
                if status not in {409, 412} and code not in {
                    "ConditionalRequestConflict",
                    "PreconditionFailed",
                }:
                    raise

            response = client.get_object(
                Bucket=parsed.netloc,
                Key=parsed.path.lstrip("/"),
            )
            body = response["Body"]
            import hashlib

            offset = 0
            content_matches = True
            existing_hasher = hashlib.sha256()
            try:
                while chunk := body.read(1024 * 1024):
                    existing_hasher.update(chunk)
                    end = offset + len(chunk)
                    if payload[offset:end] != chunk:
                        content_matches = False
                        break
                    offset = end
                # A mismatch can be detected before the existing object is
                # fully read (early break above) -- finish hashing whatever
                # remains so existing_content_hash reflects the real stored
                # object, not just the bytes compared before the break.
                while chunk := body.read(1024 * 1024):
                    existing_hasher.update(chunk)
            finally:
                body.close()
            if content_matches and offset == len(payload):
                return destination
            raise self._quarantine_conflict(relative, payload, existing_hasher.hexdigest())

        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination_path.open("xb") as handle:
                handle.write(payload)
            return str(destination_path)
        except FileExistsError:
            import hashlib

            existing_bytes = destination_path.read_bytes()
            if existing_bytes == payload:
                return str(destination_path)
            raise self._quarantine_conflict(
                relative, payload, hashlib.sha256(existing_bytes).hexdigest()
            )

    def _quarantine_conflict(
        self, relative: str, payload: bytes, existing_hash: str
    ) -> "ImmutableContentConflictError":
        """Write ``payload`` to a content-addressed quarantine sibling and
        build (not raise -- so callers keep their own ``raise ... from``
        context) the conflict error describing it. See
        ``ImmutableContentConflictError``'s own docstring.

        Takes ``existing_hash`` from the caller rather than re-reading the
        existing object itself: the local branch already has the bytes in
        hand, and the remote branch already streamed them once for the
        byte-for-byte compare -- a second remote read here would be both
        wasteful and, for a caller whose test/runtime environment only mocks
        the specific client already in use, a real path to an unrelated
        failure (confirmed live: an unconditional ``read_bytes`` re-read hit
        a real network call under a test that only mocks ``boto3.client``,
        not ``fsspec``).
        """
        import hashlib

        new_hash = hashlib.sha256(payload).hexdigest()
        quarantine_relative = sanitize_relative_path(f"{relative}.conflict/{new_hash}")
        # Reuses this same method: a quarantine path is itself content-addressed
        # by the new payload's own hash, so it can never collide with anything
        # else (a replay of the same conflict is idempotent -- matching content
        # at a matching key returns cleanly, same as any other immutable write).
        self.write_immutable_bytes(quarantine_relative, payload)
        return ImmutableContentConflictError(
            relative_path=relative,
            existing_content_hash=existing_hash,
            new_content_hash=new_hash,
            quarantine_relative_path=quarantine_relative,
        )

    def promote_staged(
        self,
        staged_relative_path: str,
        canonical_relative_path: str,
        *,
        expected_etag: str | None,
        payload: "bytes | Path | None" = None,
    ) -> "PromotionResult":
        """Promote a staged object onto the canonical key -- but only if
        canonical's current version/ETag still equals ``expected_etag``. For
        S3, the precondition is attached to the PutObject request itself; a
        separate check followed by an ordinary write is not concurrency-safe.

        Raises ``PromotionConflictError`` (leaving the staged object in place
        for inspection/retry) if canonical changed since ``expected_etag`` was
        read. Never silently last-writer-wins.

        ``payload`` -- when the caller still has the exact bytes or local file
        it just staged, pass it here to promote directly instead of
        re-downloading the object this same call just uploaded
        (seed-universe-narrow-hydrate ticket 06). Omitted (the default),
        this reads the staged object back from storage -- the original
        behavior, needed by any caller that only has the staged *path*, not
        the original payload (e.g. a promotion retried in a later process).
        """
        canonical_relative = sanitize_relative_path(canonical_relative_path)
        previous = self.read_object_version(canonical_relative)
        if previous.etag != expected_etag:
            raise PromotionConflictError(
                canonical_relative, expected_etag, previous.etag, staged_relative_path
            )

        source: "bytes | Path" = (
            payload
            if payload is not None
            else read_bytes(self.join(sanitize_relative_path(staged_relative_path)))
        )
        canonical_path_str = self.join(canonical_relative)
        if self.is_remote:
            from urllib.parse import urlsplit

            from botocore.exceptions import ClientError

            destination = urlsplit(canonical_path_str)
            with _put_object_body(source) as (body, extra_kwargs):
                request: dict[str, Any] = {
                    "Bucket": destination.netloc,
                    "Key": destination.path.lstrip("/"),
                    "Body": body,
                    **extra_kwargs,
                }
                if expected_etag is None:
                    request["IfNoneMatch"] = "*"
                else:
                    request["IfMatch"] = expected_etag
                try:
                    response = self._s3().put_object(**request)
                except ClientError as exc:
                    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
                    if status in {404, 409, 412}:
                        actual = self.read_object_version(canonical_relative)
                        raise PromotionConflictError(
                            canonical_relative,
                            expected_etag,
                            actual.etag,
                            staged_relative_path,
                        ) from exc
                    raise
            raw_etag = response.get("ETag")
            new_version = ObjectVersion(
                exists=True,
                etag=str(raw_etag).strip('"') if raw_etag else None,
                version_id=response.get("VersionId"),
            )
        else:
            canonical_path_str = self.write_bytes(canonical_relative, source)
            new_version = self.read_object_version(canonical_relative)
        return PromotionResult(
            canonical_path=canonical_path_str,
            staged_relative_path=staged_relative_path,
            previous_version=previous,
            new_version=new_version,
        )

    def stage_and_promote(
        self,
        canonical_relative_path: str,
        payload: "bytes | Path",
        *,
        expected_etag: str | None,
    ) -> "PromotionResult":
        """Write ``payload`` to a fresh staging key, then promote it onto
        ``canonical_relative_path`` guarded by ``expected_etag``.

        Extracted (decoupled-bronze-pipeline ticket 09's Answer) from what
        was three call sites independently writing this same two-step
        sequence by hand -- one of which (``_publish_shard_if_remote``) had
        drifted to a blind overwrite with no ETag guard at all (ticket 01's
        finding). A single shared helper means that gap can't recur at a
        fourth call site. See ``promote_staged`` for the concurrency
        contract this preserves.

        ``payload`` may be a local ``Path``, in which case it is streamed to
        the staging key and then reused directly for promotion, without ever
        re-downloading the object this call just uploaded
        (seed-universe-narrow-hydrate ticket 06).
        """
        staged_relative = self.write_staged_bytes(canonical_relative_path, payload)
        return self.promote_staged(
            staged_relative, canonical_relative_path, expected_etag=expected_etag, payload=payload
        )

    def delete_object(self, relative_path: str) -> None:
        """Delete one object. Best-effort: missing objects are not an error.

        `promote_staged` never deletes the staged object it just promoted
        (deliberately, so a `PromotionConflictError` leaves it in place for
        inspection/retry) -- callers that know a promotion succeeded use this
        to clean up their own staged object explicitly (release-readiness
        ticket 65). A bucket lifecycle rule is the backstop for the conflict
        case and for anything a caller doesn't clean up itself.
        """
        relative = sanitize_relative_path(relative_path)
        destination = self.join(relative)
        if self.is_remote:
            from urllib.parse import urlsplit

            parsed = urlsplit(destination)
            self._s3().delete_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
            return
        Path(destination).unlink(missing_ok=True)

    def write_bytes(self, relative_path: str, payload: "bytes | Path") -> str:
        """Write ``payload`` to storage.

        A ``Path`` payload delegates to the already-streaming ``upload_file``
        (no full-buffer read of the source file) instead of being read fully
        into memory first (seed-universe-narrow-hydrate ticket 06).
        """
        if isinstance(payload, Path):
            return self.upload_file(relative_path, payload)
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


def object_exists(storage_path: str) -> bool:
    """Targeted existence check for one absolute storage path.

    Callers that already have a candidate storage_path (e.g. from a
    sec_raw_object row) and only need to confirm it's still really there --
    as opposed to `StorageLocation.find_existing`'s glob search, which
    requires knowing the object's containing accession/CIK prefix in
    advance and cannot find an object legitimately stored under a
    *different* accession's prefix (content-hash dedup, see
    silver_protection.py's sec_raw_object provenance_columns).
    """
    protocol = _protocol_for_uri(storage_path)
    if protocol is None:
        return Path(storage_path).exists()
    _assert_protocol_allowed(protocol)
    import fsspec

    fs = fsspec.filesystem(protocol, **_remote_storage_options(storage_path))
    return bool(fs.exists(storage_path))


def write_uri_bytes(storage_path: str, payload: bytes) -> str:
    """Write bytes to an absolute local path or remote URI (e.g. s3://bucket/key)."""
    protocol = _protocol_for_uri(storage_path)
    if protocol is None:
        destination = Path(storage_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return str(destination)
    _assert_protocol_allowed(protocol)
    import fsspec

    fs = fsspec.filesystem(protocol, **_remote_storage_options(storage_path))
    parent = storage_path.rsplit("/", 1)[0]
    if parent and parent != storage_path:
        try:
            fs.makedirs(parent, exist_ok=True)
        except Exception:
            # S3 fs often does not need explicit makedirs; ignore best-effort failures.
            pass
    with fs.open(storage_path, "wb") as handle:
        handle.write(payload)
    return storage_path


def write_uri_text(storage_path: str, payload: str) -> str:
    return write_uri_bytes(storage_path, payload.encode("utf-8"))


def list_uri_child_names(storage_prefix: str) -> list[str]:
    """List immediate child names under an absolute local path or remote URI prefix."""
    prefix = storage_prefix if storage_prefix.endswith("/") else f"{storage_prefix}/"
    protocol = _protocol_for_uri(prefix)
    if protocol is None:
        base = Path(prefix)
        if not base.is_dir():
            return []
        return sorted(child.name for child in base.iterdir())
    _assert_protocol_allowed(protocol)
    import fsspec

    fs = fsspec.filesystem(protocol, **_remote_storage_options(prefix))
    if not fs.exists(prefix.rstrip("/")) and not fs.exists(prefix):
        return []
    try:
        entries = fs.ls(prefix, detail=False)
    except FileNotFoundError:
        return []
    return sorted({entry.rstrip("/").rsplit("/", 1)[-1] for entry in entries})
