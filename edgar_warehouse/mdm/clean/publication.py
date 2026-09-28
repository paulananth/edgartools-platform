"""Idempotent consumer adapters for the versioned Clean MDM contract."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .store import Conflict, canonical



class LocalContractSink:
    """Offline contract verification only; this is not an AWS export deployment.

    Each immutable generation contains the same envelope the hosted adapter
    must consume. Exclusive file creation and exact read-back tolerate retries.
    """

    def __init__(self, directory):
        self.directory = Path(directory)

    def _path(self, key):
        return self.directory / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def publish(self, key, payload, expected_hash):
        self.directory.mkdir(parents=True, exist_ok=True)
        data = canonical(
            {"key": key, "payload": payload, "hash": expected_hash}
        ).encode()
        target = self._path(key)
        # Atomic link publishes only a complete, fsynced file and never overwrites
        # an earlier delivery. A process crash leaves at most a temporary file.
        import tempfile

        fd, name = tempfile.mkstemp(prefix=".delivery-", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(name, target)
            except FileExistsError:
                pass
        finally:
            os.unlink(name)
        if target.read_bytes() != data:
            raise Conflict("Existing consumer payload disagrees")

    def verify(self, key, payload, expected_hash):
        stored = json.loads(self._path(key).read_text())
        if stored != {"key": key, "payload": payload, "hash": expected_hash}:
            raise Conflict("Consumer read-back mismatch")
        return expected_hash
