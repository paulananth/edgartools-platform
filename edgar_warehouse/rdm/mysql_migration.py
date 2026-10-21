"""Owner-only installation of frozen reference storage on a configured MySQL DB."""
import hashlib
import re
from pathlib import Path

from sqlalchemy import inspect, text

from edgar_warehouse.control_contract import Blocked
from .storage import KEYS

BOUNDARY = "\n-- statement boundary\n"
MIGRATION = Path(__file__).parent / "migrations" / "mysql-v1.sql"


def migrate(engine, *, runtime_role, existing_only=False, database_name=None):
    database_name = database_name or engine.url.database
    if not database_name or engine.url.database != database_name:
        raise Blocked("Reference migration requires the configured isolated database")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,31}", runtime_role):
        raise Blocked("An existing restricted runtime account is required")
    payload = MIGRATION.read_text()
    checksum = hashlib.sha256(payload.encode()).hexdigest()
    statements = payload.strip().split(BOUNDARY)
    quote = engine.dialect.identifier_preparer.quote_identifier
    role = "'" + runtime_role + "'@'%'"
    grantee = role
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if not str(conn.scalar(text("SELECT VERSION()"))).startswith("8."):
            raise Blocked("Reference storage requires MySQL 8")
        if conn.scalar(text("SELECT DATABASE()")) != database_name:
            raise Blocked("Reference migration requires the configured isolated database")
        if (conn.scalar(text("SELECT SUBSTRING_INDEX(CURRENT_USER(),'@',1)=:r"), {"r": runtime_role})
                or conn.scalar(text("SELECT COUNT(*) FROM mysql.user WHERE User=:r AND Host='%'"), {"r": runtime_role}) != 1):
            raise Blocked("Separate migration owner and restricted runtime are required")
        grants = [row[0] for row in conn.execute(text("SHOW GRANTS FOR " + role))]
        if any((" ON *.* " in row and not row.startswith("GRANT USAGE ")) or "WITH GRANT OPTION" in row
               or " ON " not in row for row in grants):
            raise Blocked("Runtime inherits administrative or role privileges")
        if (conn.scalar(text("SELECT @@mandatory_roles")) not in ("", "NONE")
                or conn.scalar(text("SELECT COUNT(*) FROM mysql.role_edges WHERE TO_USER=:r AND TO_HOST='%'"), {"r": runtime_role})
                or conn.scalar(text("SELECT COUNT(*) FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d"),
                               {"g": grantee, "d": database_name})
                or conn.scalar(text("SELECT COUNT(*) FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d "
                                    "AND PRIVILEGE_TYPE NOT IN ('SELECT','INSERT','UPDATE','DELETE')"),
                               {"g": grantee, "d": database_name})):
            raise Blocked("Runtime inherits broad or administrative storage privileges")
        if conn.scalar(text("SELECT COUNT(*) FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d "
                            "AND TABLE_NAME IN ('rdm_migrations','rdm_readiness') AND PRIVILEGE_TYPE<>'SELECT'"),
                       {"g": grantee, "d": database_name}) or conn.scalar(text(
                            "SELECT COUNT(*) FROM information_schema.COLUMN_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d "
                            "AND TABLE_NAME IN ('rdm_migrations','rdm_readiness') AND PRIVILEGE_TYPE<>'SELECT'"),
                       {"g": grantee, "d": database_name}):
            raise Blocked("Runtime can mutate migration metadata")
        lock = "rdm_" + hashlib.sha256(database_name.encode()).hexdigest()[:40]
        if conn.scalar(text("SELECT GET_LOCK(:n,30)"), {"n": lock}) != 1:
            raise Blocked("Reference migration lock unavailable")
        try:
            held_tables = set(inspect(conn).get_table_names())
            if "rdm_migrations" not in held_tables:
                if existing_only:
                    raise Blocked("RDM is not initialized; run rdm init first")
                if held_tables:
                    raise Blocked("Refusing to adopt untracked reference storage")
                conn.execute(text("CREATE TABLE rdm_migrations (id SMALLINT PRIMARY KEY, checksum CHAR(64) NOT NULL, "
                                  "complete SMALLINT NOT NULL) ENGINE=InnoDB COMMENT='rdm-native:" + checksum + "'"))
                conn.execute(text("INSERT INTO rdm_migrations VALUES (1,:h,0)"), {"h": checksum})
            if held_tables - (set(KEYS) | {"rdm_migrations"}):
                raise Blocked("Reference database must contain only its own store")
            held = conn.execute(text("SELECT checksum,complete FROM rdm_migrations WHERE id=1")).first()
            if (held is None and held_tables == {"rdm_migrations"}
                    and inspect(conn).get_table_comment("rdm_migrations")["text"] == "rdm-native:" + checksum
                    and {row["name"] for row in inspect(conn).get_columns("rdm_migrations")} == {"id", "checksum", "complete"}
                    and conn.scalar(text("SELECT COUNT(*) FROM rdm_migrations")) == 0):
                conn.execute(text("INSERT INTO rdm_migrations VALUES (1,:h,0)"), {"h": checksum})
                held = conn.execute(text("SELECT checksum,complete FROM rdm_migrations WHERE id=1")).first()
            if not held or held.checksum != checksum:
                raise Blocked("Installed RDM migration checksum differs")
            conn.execute(text("UPDATE rdm_migrations SET complete=0 WHERE id=1"))
            # DDL commits implicitly. Revoke writes before removing any guard;
            # interruption must leave neither an admitted caller nor direct SQL
            # able to alter immutable content through an unguarded table.
            for name in KEYS:
                _revoke(conn, database_name, name, runtime_role)
            for statement in statements:
                # MySQL DDL commits implicitly; resume an interrupted migration
                # using only its same frozen, checksummed statements.
                index = re.match(r"CREATE (?:UNIQUE |FULLTEXT )?INDEX (\w+) ON (\w+)", statement)
                if index and index[1] in {row["name"] for row in inspect(conn).get_indexes(index[2])}:
                    continue
                conn.execute(text(statement))
            conn.execute(text("CREATE OR REPLACE SQL SECURITY DEFINER VIEW rdm_readiness AS "
                              "SELECT complete FROM rdm_migrations WHERE id=1"))
            for name in KEYS:
                target = quote(database_name) + "." + quote(name)
                conn.execute(text("GRANT SELECT ON " + target + " TO " + role))
                rights = ("INSERT(code_set,name,definition,authority,steward)" if name == "code_set" else
                    "INSERT(code_set,version,supersedes,created_by,evidence),UPDATE(status,approved_by,approved_words,valid_from,valid_to,sha256)"
                    if name == "code_set_version" else "INSERT" if name == "code_path" else "INSERT,UPDATE,DELETE")
                conn.execute(text("GRANT " + rights + " ON " + target + " TO " + role))
            conn.execute(text("GRANT SELECT ON " + quote(database_name) + ".rdm_readiness TO " + role))
            conn.execute(text("GRANT SELECT ON " + quote(database_name) + ".code_context TO " + role))
            conn.execute(text("GRANT EXECUTE ON PROCEDURE " + quote(database_name) + ".lock_code_set TO " + role))
            conn.execute(text("UPDATE rdm_migrations SET complete=1 WHERE id=1"))
        finally:
            conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": lock})
    return {"mysql-v1.sql": checksum}


def _revoke(conn, database_name, name, runtime_role):
    quote = conn.dialect.identifier_preparer.quote_identifier
    role = "'" + runtime_role + "'@'%'"
    parameters = {"g": role, "d": database_name, "t": name}
    held = conn.scalar(text("SELECT COUNT(*) FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=:g "
                            "AND TABLE_SCHEMA=:d AND TABLE_NAME=:t"), parameters)
    held += conn.scalar(text("SELECT COUNT(*) FROM information_schema.COLUMN_PRIVILEGES WHERE GRANTEE=:g "
                             "AND TABLE_SCHEMA=:d AND TABLE_NAME=:t"), parameters)
    if held:
        conn.execute(text("REVOKE ALL PRIVILEGES ON " + quote(database_name) + "." + quote(name) + " FROM " + role))
