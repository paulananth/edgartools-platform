"""Explicit PostgreSQL 16 migration, isolated DB, restricted runtime functions."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text

from .config import Blocked, canonical


def get_engine(url: str | None = None):
    # No fallback to BOOKKEEPING_DATABASE_URL: that is the legacy store.
    return create_engine(url or os.environ["BOOKKEEPING_CLEAN_DATABASE_URL"], pool_pre_ping=True)


def migrate(engine, *, runtime_role: str, existing_only: bool = False) -> dict:
    if engine.dialect.name != "postgresql":
        raise Blocked("Bookkeeping requires PostgreSQL 16")
    quote = engine.dialect.identifier_preparer.quote
    paths = sorted((Path(__file__).parent / "migrations").glob("[0-9]*.sql"))
    with engine.begin() as conn:
        if conn.scalar(text("SELECT current_database()")) != "bookkeeping_clean":
            raise Blocked("Refusing migration outside fresh bookkeeping_clean")
        if int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
            raise Blocked("Bookkeeping requires PostgreSQL 16")
        role = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=:r"), {"r": runtime_role}).first()
        if not role or any(role) or conn.scalar(text("SELECT current_user")) == runtime_role:
            raise Blocked("An existing restricted runtime and separate migration owner are required")
        conn.execute(text("SELECT pg_advisory_xact_lock(730501)"))
        exists = conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='bookkeeping')"))
        saved = conn.scalar(text("SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname='bookkeeping'"))
        if existing_only and not exists:
            raise Blocked(
                "Bookkeeping is not initialized; run bookkeeping init first"
            )
        if exists and not saved:
            raise Blocked("Existing untracked schema; refusing to adopt it")
        checksums = json.loads(saved) if saved else {}
        for path in paths:
            sql = path.read_text()
            sha = hashlib.sha256(sql.encode()).hexdigest()
            if path.name in checksums:
                if checksums[path.name] != sha:
                    raise Blocked("Installed migration checksum differs")
            else:
                conn.execute(text(sql))
                checksums[path.name] = sha
        comment = canonical(checksums).replace("'", "''")
        conn.exec_driver_sql(f"COMMENT ON SCHEMA bookkeeping IS '{comment}'")
        runtime = quote(runtime_role)
        conn.exec_driver_sql(f"REVOKE ALL ON SCHEMA bookkeeping FROM PUBLIC, {runtime}")
        conn.exec_driver_sql(f"REVOKE ALL ON ALL TABLES IN SCHEMA bookkeeping FROM PUBLIC, {runtime}")
        conn.exec_driver_sql(f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA bookkeeping FROM PUBLIC, {runtime}")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA bookkeeping TO {runtime}")
        conn.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA bookkeeping TO {runtime}")
        for signature in (
            "start_run(uuid,jsonb,text,jsonb)", "claim(uuid,text,text,uuid,integer,jsonb)",
            "heartbeat(uuid,text,text,uuid,jsonb,integer)", "finish(uuid,text,text,uuid,jsonb,jsonb,jsonb,uuid)",
            "wait_work(uuid,text,text,text,uuid,jsonb)", "record_checks(uuid,jsonb)",
            "resume_run(uuid)", "block_run(uuid,text)", "delivery(uuid,text)",
            "finish_resource(uuid,text,text,uuid,jsonb,jsonb,jsonb,uuid,text,bigint,bigint)",
            "finish_expand(uuid,text,text,uuid,jsonb,jsonb,jsonb,uuid,jsonb,text)",
            "report(uuid,text,text,uuid,jsonb,jsonb,text,text)", "verify_claim(uuid,text,text,uuid,integer)",
            "pin_verifier(uuid,text,text)",
        ):
            conn.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION bookkeeping.{signature} TO {runtime}")
        if conn.scalar(text("SELECT has_schema_privilege(:r,'bookkeeping','CREATE') OR EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='bookkeeping' AND has_table_privilege(:r,format('%I.%I',schemaname,tablename),'INSERT,UPDATE,DELETE,TRUNCATE'))"), {"r": runtime_role}):
            raise Blocked("Runtime inherits direct control writes or schema ownership")
    return checksums


def grant_profile(engine, *, profile: str, worker: str, verifier: str) -> dict:
    """Let one login report a profile's work and another verify it. The
    profile's two group roles are created on first use; grants are added,
    never removed, and the two logins must differ."""
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", profile) or worker == verifier:
        raise Blocked("A profile needs a name and two different logins")
    quote = engine.dialect.identifier_preparer.quote
    granted = {}
    with engine.begin() as conn:
        for duty, login in (("worker", worker), ("verifier", verifier)):
            role = conn.scalar(text("SELECT bookkeeping.profile_role(:p,:d)"), {"p": profile, "d": duty})
            if not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:r)"), {"r": role}):
                conn.exec_driver_sql(f"CREATE ROLE {quote(role)} NOLOGIN")
            if not conn.scalar(text("SELECT pg_has_role(:l,:r,'MEMBER')"), {"l": login, "r": role}):
                conn.exec_driver_sql(f"GRANT {quote(role)} TO {quote(login)}")
            granted[duty] = {"role": role, "login": login}
    return granted
