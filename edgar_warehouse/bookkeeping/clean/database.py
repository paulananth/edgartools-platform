"""Explicit selected-engine migration and restricted control capabilities."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .config import Blocked, canonical


def get_engine(url: str | None = None):
    target = make_url(url or os.environ["BOOKKEEPING_DATABASE_URL"])
    drivers = {"postgresql": "postgresql+psycopg2", "mysql": "mysql+pymysql", "mssql": "mssql+pymssql"}
    if target.drivername in drivers:
        target = target.set(drivername=drivers[target.drivername])
    return create_engine(target, pool_pre_ping=True, hide_parameters=True)


def migrate(engine, *, runtime_role: str, existing_only: bool = False, database_name: str = "bookkeeping") -> dict:
    if engine.dialect.name == "mysql":
        from .mysql import migrate as migrate_selected
        return migrate_selected(engine, runtime_role=runtime_role, existing_only=existing_only, database_name=database_name)
    if engine.dialect.name != "postgresql":
        raise Blocked("Bookkeeping supports PostgreSQL/MySQL; SQL Server follows last")
    quote = engine.dialect.identifier_preparer.quote
    # The current schema, then any numbered change made after it.
    folder = Path(__file__).parent / "migrations"
    paths = [folder / "schema.sql", *sorted(folder.glob("[0-9]*.sql"))]
    with engine.begin() as conn:
        if conn.scalar(text("SELECT current_database()")) != database_name:
            raise Blocked("Refusing migration outside fresh bookkeeping")
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
        if checksums and "schema.sql" not in checksums:
            raise Blocked("This Bookkeeping store does not hold this build's schema; rebuild the store")
        from .run_storage import execute_ddl
        for path in paths:
            sql = path.read_text()
            sha = hashlib.sha256(sql.encode()).hexdigest()
            if path.name in checksums:
                if checksums[path.name] != sha:
                    raise Blocked("Installed migration checksum differs")
            else:
                execute_ddl(conn, sql)
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
            "wait_work(uuid,text,text,text,uuid,jsonb)", "record_run_checks(text)",
            "resume_run_prepared(text)", "block_run(uuid,text)", "delivery(uuid,text)",
            "finish_resource(uuid,text,text,uuid,jsonb,jsonb,jsonb,uuid,text,bigint,bigint)",
            "finish_expand(uuid,text,text,uuid,jsonb,jsonb,jsonb,uuid,jsonb,text)",
            "pin_runtime(uuid,text,text)",
        ):
            conn.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION bookkeeping.{signature} TO {runtime}")
        if conn.scalar(text("SELECT has_schema_privilege(:r,'bookkeeping','CREATE') OR EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='bookkeeping' AND has_table_privilege(:r,format('%I.%I',schemaname,tablename),'INSERT,UPDATE,DELETE,TRUNCATE'))"), {"r": runtime_role}):
            raise Blocked("Runtime inherits direct control writes or schema ownership")
    return checksums


def grant_profile(engine, *, profile: str, worker: str) -> dict:
    """Let a login work a profile's steps. The profile's group role is created
    on first use; grants are added, never removed."""
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", profile):
        raise Blocked("A profile needs a name")
    if engine.dialect.name == "mysql":
        from .mysql import grant_profile as grant_selected
        return grant_selected(engine, profile=profile, worker=worker)
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        role = conn.scalar(text("SELECT bookkeeping.profile_role(:p,'worker')"), {"p": profile})
        if not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:r)"), {"r": role}):
            conn.exec_driver_sql(f"CREATE ROLE {quote(role)} NOLOGIN")
        if not conn.scalar(text("SELECT pg_has_role(:l,:r,'MEMBER')"), {"l": worker, "r": role}):
            conn.exec_driver_sql(f"GRANT {quote(role)} TO {quote(worker)}")
    return {"worker": {"role": role, "login": worker}}
