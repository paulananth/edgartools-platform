"""Destination-local authority; legacy mirror helpers are archive interfaces."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from .config import Blocked, canonical


def _migrate(engine, filename: str, schema: str, runtime_role: str):
    sql = (Path(__file__).parent / "migrations" / filename).read_text()
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
        signature = "authorize(jsonb)" if schema == "bookkeeping_guard" else "deliver(uuid,jsonb,text)"
        conn.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION {schema}.{signature} TO {runtime}")
        if schema == "bookkeeping_guard":
            conn.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION bookkeeping_guard.claim_publication(text,text,integer,text) TO {runtime}")
        if conn.scalar(text("SELECT has_schema_privilege(:r,:s,'CREATE') OR EXISTS(SELECT 1 FROM pg_tables WHERE schemaname=:s AND has_table_privilege(:r,format('%I.%I',schemaname,tablename),'INSERT,UPDATE,DELETE,TRUNCATE'))"), {"r": runtime_role, "s": schema}):
            raise Blocked("Runtime inherits destination guard or journal mutation privileges")
    return checksum


def migrate_guard(engine, *, runtime_role: str):
    return _migrate(engine, "destination_guard.sql", "bookkeeping_guard", runtime_role)


def migrate_ledger(engine, *, runtime_role: str):
    """Legacy provisioning only; fresh CLI uses change-journal init."""
    with engine.connect() as conn:
        if conn.scalar(text("SELECT current_database()")) in {"change_journal_clean", "bookkeeping_clean", "rules"}:
            raise Blocked("Legacy mirror provisioning is forbidden in fresh owner databases")
    return _migrate(engine, "ledger.sql", "bookkeeping_mirror", runtime_role)


def guard(conn, claim):
    """Call in the SAME transaction as the destination mutation.

    Proof never enters the business payload or idempotency key. Each retry
    keeps its original effects identity while obtaining fresh authority.
    """
    conn.execute(text("SELECT bookkeeping_guard.authorize(CAST(:p AS jsonb))"), {"p": canonical(claim.proof)})


class ChangeLedger:
    """Legacy sink for original-stack drains; never a fresh runtime fallback."""
    def __init__(self, engine):
        self.engine = engine

    def deliver(self, event_id: str, payload: dict):
        with self.engine.begin() as conn:
            body = canonical(payload)
            # PostgreSQL's jsonb text representation is the sink's checksum
            # contract, matching the existing mdm_mirror deliver mechanism.
            sha = conn.scalar(text("SELECT encode(sha256(convert_to(CAST(CAST(:p AS jsonb) AS text),'UTF8')),'hex')"), {"p": body})
            conn.execute(text("SELECT bookkeeping_mirror.deliver(CAST(:e AS uuid),CAST(:p AS jsonb),:h)"), {"e": event_id, "p": body, "h": sha})
