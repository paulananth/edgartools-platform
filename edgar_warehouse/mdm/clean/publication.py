"""Idempotent consumer adapters for the versioned Clean MDM contract."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import text

from .store import Conflict, canonical


def migrate_mirror(engine, *, application_role: str) -> dict:
    if engine.dialect.name != "postgresql":
        raise ValueError("Mirror requires PostgreSQL 16")
    path = Path(__file__).parents[1] / "migrations" / "024_clean_mdm_mirror.sql"
    source = path.read_text()
    checksum = hashlib.sha256(source.encode()).hexdigest()
    role = engine.dialect.identifier_preparer.quote(application_role)
    with engine.begin() as conn:
        if int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
            raise ValueError("Mirror requires PostgreSQL 16")
        conn.execute(text("SELECT pg_advisory_xact_lock(730235)"))
        installed = conn.scalar(text("SELECT to_regclass('mdm_mirror.migration')"))
        if installed:
            if (
                conn.scalar(
                    text("SELECT checksum FROM mdm_mirror.migration WHERE name=:name"),
                    {"name": path.name},
                )
                != checksum
            ):
                raise Conflict("Mirror migration checksum differs")
        else:
            conn.execute(text(source))
            conn.execute(
                text("INSERT INTO mdm_mirror.migration VALUES(:name,:checksum)"),
                {"name": path.name, "checksum": checksum},
            )
        conn.exec_driver_sql(
            f"REVOKE ALL ON ALL TABLES IN SCHEMA mdm_mirror FROM {role}"
        )
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA mdm_mirror TO {role}")
        conn.exec_driver_sql(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA mdm_mirror TO {role}"
        )
        conn.exec_driver_sql(
            f"GRANT EXECUTE ON FUNCTION mdm_mirror.deliver(text,text,jsonb) TO {role}"
        )
    return {
        "migration": path.name,
        "checksum": checksum,
        "installed": not bool(installed),
    }


class JournalMirror:
    def __init__(self, engine):
        self.engine = engine

    def publish(self, key, payload, expected_hash):
        with self.engine.begin() as conn:
            conn.execute(
                text("SELECT mdm_mirror.deliver(:key,:hash,CAST(:payload AS jsonb))"),
                {"key": key, "hash": expected_hash, "payload": canonical(payload)},
            )

    def verify(self, key, payload, expected_hash):
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT payload,payload_hash FROM mdm_mirror.event WHERE delivery_key=:key"
                ),
                {"key": key},
            ).one()
            if row.payload != payload or row.payload_hash != expected_hash:
                raise Conflict("Mirror read-back mismatch")
            return row.payload_hash


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
