"""Checksummed migrations of the RDM database: its own `rdm` database on PostgreSQL 16."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.control_contract import Blocked, canonical

MIGRATIONS = Path(__file__).parent / "migrations"
CONTENT = ("code", "code_label", "level", "crosswalk_row", "code_set_usage", "code_set_hint")


def migrate(engine, *, runtime_role: str, existing_only: bool = False) -> dict:
    """Apply the numbered migrations not yet installed, then grant the runtime
    role what drafting, recording an approval and publishing need, and no more."""
    if engine.dialect.name != "postgresql":
        raise Blocked("RDM requires PostgreSQL 16")
    paths = sorted(MIGRATIONS.glob("[0-9]*.sql"))
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        if (conn.scalar(text("SELECT current_database()")) != "rdm"
                or int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16):
            raise Blocked("RDM migration requires its own rdm database on PostgreSQL 16")
        role = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=:r"),
                            {"r": runtime_role}).first()
        if (not role or any(role) or conn.scalar(text("SELECT current_user")) == runtime_role
                or conn.scalar(text("SELECT pg_has_role(:r,current_user,'MEMBER')"), {"r": runtime_role})):
            raise Blocked("Separate migration owner and restricted runtime are required")
        conn.execute(text("SELECT pg_advisory_xact_lock(730701)"))
        exists = conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='rdm')"))
        saved = conn.scalar(text("SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname='rdm'"))
        if existing_only and not exists:
            raise Blocked("RDM is not initialized; run rdm init first")
        if exists and not saved:
            raise Blocked("Refusing to adopt an untracked rdm schema")
        checksums = json.loads(saved) if saved else {}
        if set(checksums) - {p.name for p in paths}:
            raise Blocked("Installed RDM migration is absent from this build")
        for path in paths:
            source = path.read_text()
            checksum = hashlib.sha256(source.encode()).hexdigest()
            if path.name in checksums:
                if checksums[path.name] != checksum:
                    raise Blocked("Installed RDM migration checksum differs")
            else:
                conn.execute(text(source))
                checksums[path.name] = checksum
        comment = canonical(checksums).replace("'", "''")
        conn.exec_driver_sql(f"COMMENT ON SCHEMA rdm IS '{comment}'")
        runtime = quote(runtime_role)
        conn.exec_driver_sql(f"REVOKE ALL ON SCHEMA rdm FROM PUBLIC,{runtime}")
        conn.exec_driver_sql(f"REVOKE ALL ON ALL TABLES IN SCHEMA rdm FROM PUBLIC,{runtime}")
        conn.exec_driver_sql(f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA rdm FROM PUBLIC,{runtime}")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA rdm TO {runtime}")
        conn.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA rdm TO {runtime}")
        conn.exec_driver_sql(f"GRANT INSERT(code_set,name,definition,authority,steward) ON rdm.code_set TO {runtime}")
        # The runtime records the operator's approval in their name and exact
        # words, as the Rules agent does (operator, 2026-09-29, rules skill
        # ticket 14); the trigger refuses it without both, or from the drafter.
        conn.exec_driver_sql(
            f"GRANT INSERT(code_set,version,supersedes,created_by,evidence), "
            f"UPDATE(status,approved_by,approved_words,valid_from,valid_to,sha256) "
            f"ON rdm.code_set_version TO {runtime}")
        for table in CONTENT:  # a draft's content; the triggers refuse it after approval
            conn.exec_driver_sql(f"GRANT INSERT, UPDATE, DELETE ON rdm.{table} TO {runtime}")
        conn.exec_driver_sql(f"GRANT INSERT ON rdm.code_path TO {runtime}")
        if conn.scalar(text("SELECT to_regprocedure('rdm.code_search(text,text,text,integer)') IS NOT NULL")):
            conn.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION rdm.code_search(text,text,text,integer) TO {runtime}")
        tables = ["code_set", "code_set_version", "code_path", *CONTENT]
        if conn.scalar(text(
                "SELECT has_schema_privilege(:r,'rdm','CREATE') "
                "OR has_table_privilege(:r,'rdm.code_set','UPDATE,DELETE') "
                "OR has_table_privilege(:r,'rdm.code_set_version','DELETE') "
                "OR has_table_privilege(:r,'rdm.code_path','UPDATE,DELETE') "
                "OR EXISTS(SELECT 1 FROM unnest(CAST(:t AS text[])) t "
                "WHERE has_table_privilege(:r,'rdm.'||t,'TRUNCATE,TRIGGER,REFERENCES'))"),
                {"r": runtime_role, "t": tables}):
            raise Blocked("Runtime inherits RDM schema ownership or rights beyond drafting and publishing")
    return checksums
