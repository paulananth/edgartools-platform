"""Destination-local authority for configured work."""
from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import text

from .config import Blocked, canonical


def migrate_guard(engine, *, runtime_role: str):
    schema = "bookkeeping_guard"
    sql = (Path(__file__).parent / "migrations" / "destination_guard.sql").read_text()
    checksum = hashlib.sha256(sql.encode()).hexdigest()
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        if int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
            raise Blocked("Destination requires PostgreSQL 16")
        role = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=:r"), {"r": runtime_role}).first()
        if not role or any(role) or conn.scalar(text("SELECT current_user")) == runtime_role:
            raise Blocked("Restricted runtime and separate migration owner required")
        conn.execute(text("SELECT pg_advisory_xact_lock(730502)"))
        saved = conn.scalar(text("SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname=:s"), {"s": schema})
        exists = conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:s)"), {"s": schema})
        if exists and saved != checksum:
            raise Blocked("Destination migration checksum differs")
        if not exists:
            conn.execute(text(sql))
            conn.exec_driver_sql(f"COMMENT ON SCHEMA {schema} IS '{checksum}'")
        runtime = quote(runtime_role)
        conn.exec_driver_sql(f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM PUBLIC, {runtime}")
        conn.exec_driver_sql(f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {schema} FROM PUBLIC, {runtime}")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA {schema} TO {runtime}")
        conn.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {runtime}")
        conn.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION {schema}.authorize(jsonb) TO {runtime}")
        conn.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION bookkeeping_guard.claim_publication(text,text,integer,text) TO {runtime}")
        if conn.scalar(text("SELECT has_schema_privilege(:r,:s,'CREATE') OR EXISTS(SELECT 1 FROM pg_tables WHERE schemaname=:s AND has_table_privilege(:r,format('%I.%I',schemaname,tablename),'INSERT,UPDATE,DELETE,TRUNCATE'))"), {"r": runtime_role, "s": schema}):
            raise Blocked("Runtime inherits destination guard or journal mutation privileges")
    return checksum


def guard(conn, claim):
    """Call in the SAME transaction as the destination mutation.

    Proof never enters the business payload or idempotency key. Each retry
    keeps its original effects identity while obtaining fresh authority.
    """
    conn.execute(text("SELECT bookkeeping_guard.authorize(CAST(:p AS jsonb))"), {"p": canonical(claim.proof)})
