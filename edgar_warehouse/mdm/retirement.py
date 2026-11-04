"""Owner retirement of superseded routines after governed storage is ready."""

import hashlib
from pathlib import Path

from sqlalchemy import text

from .store import Conflict


MIGRATION = "028_retire_business_routines.sql"


def require_retired(conn):
    """A new normal caller refuses an unfinished owner retirement."""
    if conn.scalar(text("SELECT checksum FROM mdm.migration WHERE name=:name"),
                   {"name": MIGRATION}) != _migration()[1]:
        raise Conflict("Governed storage requires owner routine retirement")


def _migration():
    source = (Path(__file__).parents[1] / "migrations" / MIGRATION).read_text()
    return source, hashlib.sha256(source.encode()).hexdigest()


def retire(engine):
    """Keep retained data and integrity guards; refuse unknown dependencies.

    This is part of explicit governed owner installation. A populated legacy
    store still needs its separately qualified data migration; retirement is
    never an implicit conversion of its records.
    """
    if engine.dialect.name != "postgresql":
        return
    from .prepared_registry import storage_ready

    source, checksum = _migration()
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(730233)"))
        conn.execute(text("SELECT pg_advisory_xact_lock(730234)"))
        if storage_ready(conn) is None:
            raise Conflict("Routine retirement requires complete governed storage")
        if conn.scalar(text("SELECT EXISTS(SELECT 1 FROM mdm.batch)")):
            raise Conflict("Populated legacy MDM requires a qualified data migration")
        saved = conn.scalar(
            text("SELECT checksum FROM mdm.migration WHERE name=:name"),
            {"name": MIGRATION},
        )
        if saved is not None:
            if saved != checksum:
                raise Conflict("Installed retirement migration checksum differs")
            return
        conn.execute(text(source))
        conn.execute(
            text("INSERT INTO mdm.migration(name,checksum) VALUES(:name,:checksum)"),
            {"name": MIGRATION, "checksum": checksum},
        )
