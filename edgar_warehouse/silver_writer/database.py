"""The silver schema on PostgreSQL 16: checksummed migrations, then one table per
registered spec. The schema owner migrates and registers; the restricted runtime
only reads specs and writes rows into registered tables."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.control_contract import Blocked, canonical, digest as spec_digest

from . import spec as specs

MIGRATIONS = Path(__file__).parent / "migrations"
LOCK = 730706  # the advisory lock that serialises migrating and registering


def migrate(engine, *, runtime_role: str, existing_only: bool = False) -> dict:
    """Apply the numbered migrations not yet installed, then let the runtime role
    read the registry and nothing else; each registered table grants its own rows."""
    if engine.dialect.name != "postgresql":
        raise Blocked("Silver requires PostgreSQL 16")
    paths = sorted(MIGRATIONS.glob("[0-9]*.sql"))
    with engine.begin() as conn:
        if int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
            raise Blocked("Silver migration requires PostgreSQL 16")
        _separate(conn, runtime_role)
        conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK})
        exists = conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='silver')"))
        saved = conn.scalar(text("SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname='silver'"))
        if existing_only and not exists:
            raise Blocked("Silver is not initialized; run silver init first")
        if exists and not saved:
            raise Blocked("Refusing to adopt an untracked silver schema")
        checksums = json.loads(saved) if saved else {}
        if set(checksums) - {p.name for p in paths}:
            raise Blocked("Installed silver migration is absent from this build")
        for path in paths:
            source = path.read_text()
            checksum = hashlib.sha256(source.encode()).hexdigest()
            if path.name in checksums:
                if checksums[path.name] != checksum:
                    raise Blocked("Installed silver migration checksum differs")
            else:
                conn.execute(text(source))
                checksums[path.name] = checksum
        comment = canonical(checksums).replace("'", "''")
        conn.exec_driver_sql(f"COMMENT ON SCHEMA silver IS '{comment}'")
        runtime = _quote(conn, runtime_role)
        conn.exec_driver_sql(f"REVOKE ALL ON SCHEMA silver FROM PUBLIC,{runtime}")
        conn.exec_driver_sql(f"REVOKE ALL ON silver.table_spec, silver.table_context FROM PUBLIC,{runtime}")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA silver TO {runtime}")
        conn.exec_driver_sql(f"GRANT SELECT ON silver.table_spec, silver.table_context TO {runtime}")
        if conn.scalar(text("SELECT has_schema_privilege(:r,'silver','CREATE') "
                            "OR has_table_privilege(:r,'silver.table_spec','INSERT,UPDATE,DELETE,TRUNCATE')"),
                       {"r": runtime_role}):
            raise Blocked("Runtime inherits silver schema ownership or registry rights")
    return checksums


def register(engine, spec: dict, *, runtime_role: str) -> dict:
    """Create the table a spec describes, with a comment on it and every column,
    and record the spec. The same spec again changes nothing; a changed spec for
    a registered table is refused: register it as a new table."""
    spec = specs.check(spec)
    digest = spec_digest(spec)
    name = spec["table"]
    with engine.begin() as conn:
        _separate(conn, runtime_role)
        conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK})
        held = conn.execute(text("SELECT sha256 FROM silver.table_spec WHERE table_name=:t"), {"t": name}).scalar()
        if held == digest:
            return {"table": name, "sha256": digest, "created": False}
        if held:
            raise Blocked(f"silver.{name} holds another spec ({held[:12]}); a changed spec is registered as a new table")
        q = specs.quote
        table = f"silver.{q(name)}"
        if conn.scalar(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table}):
            raise Blocked(f"silver.{name} exists without a registered spec; refusing to adopt it")
        lines = [f"{q(c['name'])} {specs.postgres_type(c['type'])}{'' if c['nullable'] else ' NOT NULL'}"
                 for c in spec["columns"]]
        lines += [f"{q(c)} text" for c in specs.mdm_id_columns(spec)]
        lines += [f"{q(c)} timestamp with time zone NOT NULL" for c in specs.added_time(spec)]
        lines.append(f"PRIMARY KEY ({', '.join(q(k) for k in spec['key'])})")
        _ddl(conn, f"CREATE TABLE {table} ({', '.join(lines)})")
        if spec["partition"]:
            # Rows are read by partition; the warehouse sink partitions physically, here an index serves.
            _ddl(conn, f"CREATE INDEX ON {table} ({', '.join(q(p) for p in spec['partition'])})")
        _comment(conn, f"TABLE {table}", f"One row per {spec['grain'].removeprefix('one row per ')}. "
                 f"{spec.get('definition') or spec['why']} Load mode: {spec['load_mode']}. Spec sha256 {digest}.")
        for c in spec["columns"]:
            words = c.get("definition") or f"From {c.get('source') or 'the source'}; not yet defined by a steward."
            if c.get("sensitivity") not in (None, "none"):
                words += f" Sensitivity: {c['sensitivity']}."
            _comment(conn, f"COLUMN {table}.{q(c['name'])}", words)
        for link in spec["links"] or []:
            share = link.get("inclusion")
            _comment(conn, f"COLUMN {table}.{q(link['mdm_id_column'])}",
                     f"The MDM id of the {link['kind']} whose {link['source_code']} record key is "
                     f"{link['source_key']}; empty while that record is not mastered."
                     + (f" Profiling found {share:.1%} of the source keys among the master's keys." if share is not None else ""))
        for c in specs.added_time(spec):
            _comment(conn, f"COLUMN {table}.{q(c)}", "When the row's delivered values were last written (the as-at "
                     "time); filling an MDM id later does not change it.")
        runtime = q(runtime_role)
        _ddl(conn, f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {runtime}")
        conn.execute(text("INSERT INTO silver.table_spec(table_name, spec, sha256) VALUES (:t, CAST(:s AS jsonb), :h)"),
                     {"t": name, "s": canonical(spec), "h": digest})
    return {"table": name, "sha256": digest, "created": True}


def _separate(conn, runtime_role: str) -> None:
    role = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=:r"),
                        {"r": runtime_role}).first()
    if (not role or any(role) or conn.scalar(text("SELECT current_user")) == runtime_role
            or conn.scalar(text("SELECT pg_has_role(:r,current_user,'MEMBER')"), {"r": runtime_role})):
        raise Blocked("Separate schema owner and restricted runtime are required")


def _quote(conn, name: str) -> str:
    return conn.dialect.identifier_preparer.quote_identifier(name)


def _ddl(conn, sql: str) -> None:
    """A statement built from spec names, sent as written: names may hold `%` or `:`,
    which a parameter-formatting call would read as placeholders."""
    with conn.connection.driver_connection.cursor() as cursor:
        cursor.execute(sql)


def _comment(conn, target: str, words: str) -> None:
    _ddl(conn, f"COMMENT ON {target} IS '" + words.replace("'", "''") + "'")
