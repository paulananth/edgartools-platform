"""Explicit PostgreSQL configuration-registration authority for governed storage."""

import hashlib
from pathlib import Path

from sqlalchemy import text

from .store import Conflict

MIGRATION = "registration_authority.sql"
SIGNATURE = "public.mdm_store_register_pin(text,text)"


def _source():
    body = (Path(__file__).parent / "migrations" / MIGRATION).read_text()
    return body, hashlib.sha256(body.encode()).hexdigest()


def require_installed(conn):
    source, checksum = _source()
    held = conn.scalar(text("SELECT checksum FROM mdm.migration WHERE name=:name"), {"name": MIGRATION})
    row = conn.execute(text("""SELECT prosrc,prosecdef,proconfig,
        EXISTS(SELECT 1 FROM aclexplode(coalesce(proacl,acldefault('f',proowner))) a
               WHERE a.grantee=0 AND a.privilege_type='EXECUTE') AS public_execute
        FROM pg_proc WHERE oid=to_regprocedure(:signature)"""), {"signature": SIGNATURE}).first()
    if (held != checksum or row is None or row[0] != source.split("$registration$")[1]
            or not row[1] or row[2] != ["search_path=pg_catalog, pg_temp"] or row[3]):
        raise Conflict("Governed storage requires the owner registration migration")


def install(engine):
    if engine.dialect.name != "postgresql":
        return
    source, checksum = _source()
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(730233)"))
        conn.execute(text("SELECT pg_advisory_xact_lock(730234)"))
        held = conn.scalar(text("SELECT checksum FROM mdm.migration WHERE name=:name"), {"name": MIGRATION})
        if held is not None:
            require_installed(conn)
            return
        conn.exec_driver_sql(source)
        conn.execute(text("INSERT INTO mdm.migration(name,checksum) VALUES(:name,:checksum)"),
                     {"name": MIGRATION, "checksum": checksum})
