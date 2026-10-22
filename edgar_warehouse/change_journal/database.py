"""Checksummed journal storage migrations and restricted runtime grants."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.control_contract import Blocked, canonical


def _execute_sql(conn, sql):
    return conn.execute(text(sql))


def migrate(engine, *, runtime_role: str, existing_only: bool = False, database_name: str = "change_journal") -> dict:
    if engine.dialect.name != "postgresql":
        from .storage_migrations import migrate_storage
        return migrate_storage(engine, runtime_role=runtime_role, existing_only=existing_only, database_name=database_name)
    from .storage_sql import statements
    additions = statements("postgresql")
    addition_checksum = hashlib.sha256("\n".join(additions).encode()).hexdigest()
    paths = sorted((Path(__file__).parent / "migrations").glob("[0-9]*.sql"))
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        if (
            conn.scalar(text("SELECT current_database()")) != database_name
            or int(conn.scalar(text("SHOW server_version_num"))) < 120000
            or conn.scalar(text("SELECT to_regprocedure('pg_catalog.sha256(bytea)')")) is None
        ):
            raise Blocked(
                "Journal migration requires the selected journal database, generated columns and native SHA-256"
            )
        role = conn.execute(
            text(
                "SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=:r"
            ),
            {"r": runtime_role},
        ).first()
        if (
            not role
            or any(role)
            or conn.scalar(text("SELECT current_user")) == runtime_role
            or conn.scalar(
                text("SELECT pg_has_role(:r,current_user,'MEMBER')"),
                {"r": runtime_role},
            )
        ):
            raise Blocked(
                "Separate migration owner and restricted runtime are required"
            )
        conn.execute(text("SELECT pg_advisory_xact_lock(730601)"))
        exists = conn.scalar(
            text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='journal')")
        )
        saved = conn.scalar(
            text(
                "SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname='journal'"
            )
        )
        if existing_only and not exists:
            raise Blocked(
                "Change Journal is not initialized; run change-journal init first"
            )
        if exists and not saved:
            raise Blocked("Refusing to adopt an untracked journal schema")
        if conn.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema','journal'))"
            )
        ):
            raise Blocked("Journal database must not contain legacy or business tables")
        checksums = json.loads(saved) if saved else {}
        if set(checksums) - ({p.name for p in paths} | {"003_native_storage"}):
            raise Blocked("Installed journal migration is absent from this build")
        for path in paths:
            source = path.read_text()
            checksum = hashlib.sha256(source.encode()).hexdigest()
            if path.name in checksums:
                if checksums[path.name] != checksum:
                    raise Blocked("Installed journal migration checksum differs")
            else:
                conn.execute(text(source))
                checksums[path.name] = checksum
        if "003_native_storage" in checksums and checksums["003_native_storage"] != addition_checksum:
            raise Blocked("Installed journal migration checksum differs")
        for statement in additions:
            _execute_sql(conn, statement)
        checksums["003_native_storage"] = addition_checksum
        comment = canonical(checksums).replace("'", "''")
        _execute_sql(conn, f"COMMENT ON SCHEMA journal IS '{comment}'")
        runtime = quote(runtime_role)
        _execute_sql(conn, f"REVOKE ALL ON SCHEMA journal FROM PUBLIC,{runtime}")
        _execute_sql(conn,
            f"REVOKE ALL ON ALL TABLES IN SCHEMA journal FROM PUBLIC,{runtime}"
        )
        _execute_sql(conn,
            f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA journal FROM PUBLIC,{runtime}"
        )
        _execute_sql(conn,
            f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA journal FROM PUBLIC,{runtime}"
        )
        _execute_sql(conn, f"GRANT USAGE ON SCHEMA journal TO {runtime}")
        _execute_sql(conn, f"GRANT SELECT ON journal.event_records TO {runtime}")
        _execute_sql(conn, f"GRANT EXECUTE ON FUNCTION journal.record_event(text,text) TO {runtime}")
        if conn.scalar(
            text(
                "SELECT has_schema_privilege(:r,'journal','CREATE') OR has_table_privilege(:r,'journal.event','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')"
            ),
            {"r": runtime_role},
        ):
            raise Blocked(
                "Runtime inherits journal table privileges or schema ownership"
            )
    return checksums
