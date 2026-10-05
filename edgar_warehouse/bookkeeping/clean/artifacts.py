"""Content-addressed control manifests; exact file/S3 bytes, no discovery on resume."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import Blocked, canonical, reference


def json_value(data: bytes):
    """Strict JSON for control documents and bounded source records alike."""
    def pairs(entries):
        value = {}
        for key, item in entries:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def invalid_constant(value):
        raise ValueError(f"Non-JSON constant {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON number exceeds finite float range")
        return number

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid_constant,
                      parse_float=finite_float)


class Artifacts:
    def __init__(self, s3=None):
        self._s3 = s3

    @property
    def s3(self):
        if self._s3 is None:
            import boto3
            self._s3 = boto3.client("s3")
        return self._s3

    def read(self, uri: str, *, max_bytes: int | None = None) -> bytes:
        location = urlparse(uri)
        try:
            if location.scheme == "s3":
                stream = self.s3.get_object(Bucket=location.netloc, Key=location.path.lstrip("/"))["Body"]
                try:
                    data = stream.read() if max_bytes is None else stream.read(max_bytes + 1)
                finally:
                    stream.close()
                if max_bytes is not None and len(data) > max_bytes:
                    raise Blocked("Control document exceeds its bounded size")
                return data
            if location.scheme == "file" and location.netloc in ("", "localhost"):
                with Path(unquote(location.path)).open("rb") as stream:
                    data = stream.read() if max_bytes is None else stream.read(max_bytes + 1)
                if max_bytes is not None and len(data) > max_bytes:
                    raise Blocked("Control document exceeds its bounded size")
                return data
        except Exception as exc:
            raise Blocked(f"Artifact missing or unreadable: {uri}") from exc
        raise Blocked("Artifact URI must be file:// (offline) or s3:// (AWS)")

    def verified(self, ref: dict, *, max_bytes: int | None = None) -> bytes:
        reference(ref)
        data = self.read(ref["uri"], max_bytes=max_bytes)
        if hashlib.sha256(data).hexdigest() != ref["sha256"]:
            raise Blocked(f"Artifact hash mismatch: {ref['uri']}")
        return data

    @contextmanager
    def verified_stream(self, ref: dict, *, max_bytes: int):
        """Yield a private, hash-verified snapshot with bounded memory.

        Authentication completes before the consumer can read any bytes.
        The snapshot prevents a mutable source from changing between hash
        verification and parsing. Its disk usage is bounded by max_bytes.
        """
        reference(ref)
        if type(max_bytes) is not int or not 1 <= max_bytes <= 2**63 - 1:
            raise Blocked("Stream snapshot requires a positive signed byte bound")
        location = urlparse(ref["uri"])
        with tempfile.TemporaryFile(mode="w+b") as snapshot:
            try:
                if location.scheme == "s3":
                    source = self.s3.get_object(Bucket=location.netloc, Key=location.path.lstrip("/"))["Body"]
                elif location.scheme == "file" and location.netloc in ("", "localhost"):
                    source = Path(unquote(location.path)).open("rb")
                else:
                    raise Blocked("Artifact URI must be file:// (offline) or s3:// (AWS)")
                checksum, size = hashlib.sha256(), 0
                try:
                    while True:
                        requested = min(65536, max_bytes - size + 1)
                        chunk = source.read(requested)
                        if not isinstance(chunk, bytes) or len(chunk) > requested:
                            raise Blocked("Artifact stream violated its bounded read contract")
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > max_bytes:
                            raise Blocked("Artifact exceeds its bounded snapshot size")
                        snapshot.write(chunk)
                        checksum.update(chunk)
                finally:
                    source.close()
                if checksum.hexdigest() != ref["sha256"]:
                    raise Blocked(f"Artifact hash mismatch: {ref['uri']}")
                snapshot.seek(0)
            except Blocked:
                raise
            except Exception as exc:
                raise Blocked(f"Artifact missing or unreadable: {ref['uri']}") from exc
            yield snapshot

    def json(self, ref: dict) -> dict:
        try:
            value = json_value(self.verified(ref, max_bytes=32 * 1024**2))
            if not isinstance(value, dict):
                raise ValueError("not a document")
            return value
        except (ValueError, UnicodeError) as exc:
            raise Blocked("Corrupt control document") from exc

    def put(self, root: str, value: dict) -> dict:
        data = canonical(value).encode()
        sha = hashlib.sha256(data).hexdigest()
        uri = f"{root.rstrip('/')}/{sha}.json"
        return self.put_bytes(uri, data)

    def put_bytes(self, uri: str, data: bytes) -> dict:
        """Immutable output: a conflicting existing object is never overwritten."""
        sha = hashlib.sha256(data).hexdigest()
        location = urlparse(uri)
        if location.scheme == "file" and not location.netloc:
            path = Path(unquote(location.path))
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".bookkeeping-", dir=path.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                os.unlink(temporary)
        elif location.scheme == "s3":
            try:
                self.s3.put_object(Bucket=location.netloc, Key=location.path.lstrip("/"), Body=data, IfNoneMatch="*")
            except Exception as exc:
                if getattr(exc, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode") != 412:
                    raise
        else:
            raise Blocked("Unsupported manifest store")
        ref = {"uri": uri, "sha256": sha}
        self.verified(ref)
        return ref
