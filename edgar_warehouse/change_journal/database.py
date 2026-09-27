"""Checksummed migrations of the empty, isolated PostgreSQL 16 journal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical


def migrate(engine, *, runtime_role: str) -> dict:
    if engine.dialect.name != "postgresql":
        raise Blocked("Change Journal requires PostgreSQL 16")
    paths = sorted((Path(__file__).parent / "migrations").glob("[0-9]*.sql"))
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        if (
            conn.scalar(text("SELECT current_database()")) != "change_journal_clean"
            or int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16
        ):
            raise Blocked(
                "Journal migration requires change_journal_clean on PostgreSQL 16"
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
        if exists and not saved:
            raise Blocked("Refusing to adopt an untracked journal schema")
        if conn.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema','journal'))"
            )
        ):
            raise Blocked("Journal database must not contain legacy or business tables")
        checksums = json.loads(saved) if saved else {}
        if set(checksums) - {p.name for p in paths}:
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
        comment = canonical(checksums).replace("'", "''")
        conn.exec_driver_sql(f"COMMENT ON SCHEMA journal IS '{comment}'")
        runtime = quote(runtime_role)
        conn.exec_driver_sql(f"REVOKE ALL ON SCHEMA journal FROM PUBLIC,{runtime}")
        conn.exec_driver_sql(
            f"REVOKE ALL ON ALL TABLES IN SCHEMA journal FROM PUBLIC,{runtime}"
        )
        conn.exec_driver_sql(
            f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA journal FROM PUBLIC,{runtime}"
        )
        conn.exec_driver_sql(
            f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA journal FROM PUBLIC,{runtime}"
        )
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA journal TO {runtime}")
        for signature in (
            "append(text,text)",
            "get(text,text)",
            "list_events(text,text,uuid,integer,bigint)",
            "status(text,text)",
        ):
            conn.exec_driver_sql(
                f"GRANT EXECUTE ON FUNCTION journal.{signature} TO {runtime}"
            )
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
