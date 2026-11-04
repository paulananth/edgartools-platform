"""Explicit PostgreSQL configuration-registration authority for governed storage."""

import hashlib
from pathlib import Path

from sqlalchemy import text

from .store import Conflict

MIGRATION = "029_registration_authority.sql"
SIGNATURE = "public.mdm_store_register_pin(text,text)"


def _source():
    body = (Path(__file__).parents[1] / "migrations" / MIGRATION).read_text()
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


def approve(conn, name, value):
    conn.execute(text("SELECT public.mdm_store_register_pin(:name,:value)"), {"name": name, "value": value})


def grant(engine, role):
    """Owner delegates only to an existing restricted configuration registrar."""
    if engine.dialect.name != "postgresql":
        raise Conflict("Delegated registration is qualified for PostgreSQL local-store setup only")
    with engine.begin() as conn:
        require_installed(conn)
        flags = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=:role"), {"role": role}).first()
        if flags is None or any(flags):
            raise Conflict("Registration requires an existing restricted governance role")
        for table in ("mdm.policy", "mdm.dataset", "mdm.dataset_mapping"):
            if not conn.scalar(text("SELECT has_table_privilege(:role,:table,'INSERT')"), {"role": role, "table": table}):
                raise Conflict("Registration requires existing configuration ownership")
        if conn.scalar(text("SELECT has_function_privilege(:role,'public.mdm_store_apply(text)','EXECUTE')"), {"role": role}):
            raise Conflict("Configuration registration and master-save duties must be separate")
        quoted = engine.dialect.identifier_preparer.quote(role)
        conn.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION {SIGNATURE} TO {quoted}")
