"""Recoverable owner installation for the normal MySQL Rules caller."""
import hashlib
import re
from pathlib import Path

from sqlalchemy import inspect, text

from edgar_warehouse.control_contract import Blocked
from .storage import APPROVAL, IDENTITY, PROOF

PAYLOAD = Path(__file__).parent / "migrations/mysql-v1.sql"


def _ddl(conn, sql):
    return conn.execute(text(sql))


def _principal(conn, name, *, agent):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,31}", name):
        raise Blocked("An existing restricted Rules principal is required")
    if conn.scalar(text("SELECT COUNT(*) FROM mysql.user WHERE User=:r AND Host='%'"), {"r": name}) != 1:
        raise Blocked("Create the configured Rules principal explicitly")
    grantee = "'" + name + "'@'%'"
    grants = [row[0] for row in conn.execute(text("SHOW GRANTS FOR " + grantee))]
    if any((" ON *.* " in row and not row.startswith("GRANT USAGE ")) or "WITH GRANT OPTION" in row or " ON " not in row for row in grants):
        raise Blocked("Rules runtime inherits administrative or role privileges")
    params = {"g": grantee, "r": name, "d": conn.engine.url.database}
    if conn.scalar(text("SELECT @@mandatory_roles")) not in ("", "NONE") or conn.scalar(text(
        "SELECT COUNT(*) FROM mysql.role_edges WHERE TO_USER=:r AND TO_HOST='%'"), params):
        raise Blocked("Rules runtime inherits role privileges")
    if conn.scalar(text("SELECT COUNT(*) FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d"), params):
        raise Blocked("Rules runtime inherits broad database privileges")
    for row in conn.execute(text("SELECT TABLE_NAME,PRIVILEGE_TYPE FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d"), params):
        if row.TABLE_NAME != "rule_version" or row.PRIVILEGE_TYPE != "SELECT":
            raise Blocked("Rules runtime has broad table or migration privileges")
    for row in conn.execute(text("SELECT TABLE_NAME,COLUMN_NAME,PRIVILEGE_TYPE FROM information_schema.COLUMN_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d"), params):
        allowed = set(IDENTITY) if agent and row.PRIVILEGE_TYPE == "INSERT" else set(APPROVAL) | (set(PROOF) if agent else set()) if row.PRIVILEGE_TYPE == "UPDATE" else set()
        if row.TABLE_NAME != "rule_version" or row.COLUMN_NAME not in allowed:
            raise Blocked("Rules runtime can mutate protected content or migration metadata")
    return grantee


def _revoke(conn, account, target):
    params = {"g": account, "d": conn.engine.url.database}
    groups = {}
    for row in conn.execute(text("SELECT COLUMN_NAME,PRIVILEGE_TYPE FROM information_schema.COLUMN_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d AND TABLE_NAME='rule_version'"), params):
        groups.setdefault(row.PRIVILEGE_TYPE, []).append(row.COLUMN_NAME)
    quote = conn.dialect.identifier_preparer.quote_identifier
    for privilege, columns in groups.items():
        _ddl(conn, "REVOKE " + privilege + "(" + ",".join(quote(c) for c in columns) + ") ON " + target + " FROM " + account)
    if conn.scalar(text("SELECT COUNT(*) FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d AND TABLE_NAME='rule_version'"), params):
        _ddl(conn, "REVOKE SELECT ON " + target + " FROM " + account)


def migrate(engine, *, agent_role, approver_role, database_name):
    payload = PAYLOAD.read_text()
    checksum = hashlib.sha256(payload.encode()).hexdigest()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if conn.scalar(text("SELECT DATABASE()")) != database_name or not str(conn.scalar(text("SELECT VERSION()"))).startswith("8."):
            raise Blocked("Rules migration requires its configured database on MySQL 8")
        current = conn.scalar(text("SELECT SUBSTRING_INDEX(CURRENT_USER(),'@',1)"))
        if current in {agent_role, approver_role}:
            raise Blocked("Rules requires a separate migration owner")
        agent = _principal(conn, agent_role, agent=True)
        approver = _principal(conn, approver_role, agent=False)
        quote = conn.dialect.identifier_preparer.quote_identifier
        target = quote(database_name) + ".rule_version"
        key = "rules-owner:" + hashlib.sha256(database_name.encode()).hexdigest()[:48]
        if conn.scalar(text("SELECT GET_LOCK(:k,30)"), {"k": key}) != 1:
            raise Blocked("Rules owner lock unavailable")
        try:
            names = set(inspect(conn).get_table_names())
            if "rules_migrations" not in names:
                if names:
                    raise Blocked("Refusing to adopt untracked Rules storage")
                _ddl(conn, "CREATE TABLE rules_migrations (id BIGINT PRIMARY KEY,checksum CHAR(64) NOT NULL,complete BIGINT NOT NULL) ENGINE=InnoDB COMMENT='rules-native:" + checksum + "'")
            held = conn.execute(text("SELECT checksum,complete FROM rules_migrations WHERE id=1")).first()
            if conn.scalar(text("SELECT COUNT(*) FROM rules_migrations WHERE id<>1 OR complete NOT IN (0,1)")):
                raise Blocked("Rules migration history differs from this build")
            if held is None:
                inspector = inspect(conn)
                shape = [(column["name"], str(column["type"].compile(dialect=conn.dialect)).upper(), column["nullable"])
                         for column in inspector.get_columns("rules_migrations")]
                if (set(inspector.get_table_names()) != {"rules_migrations"}
                    or inspector.get_table_comment("rules_migrations")["text"] != "rules-native:" + checksum
                    or shape != [("id", "BIGINT", False), ("checksum", "CHAR(64)", False), ("complete", "BIGINT", False)]
                    or inspector.get_pk_constraint("rules_migrations")["constrained_columns"] != ["id"]
                    or conn.scalar(text("SELECT COUNT(*) FROM rules_migrations"))):
                    raise Blocked("Untracked Rules migration metadata")
                conn.execute(text("INSERT INTO rules_migrations VALUES (1,:h,0)"), {"h": checksum})
            elif held.checksum != checksum:
                raise Blocked("Rules migration checksum differs")
            if held is None or not held.complete:
                if "rule_version" in names:
                    if inspect(conn).get_table_comment("rule_version")["text"] != "rules-storage-v1":
                        raise Blocked("Refusing to adopt untracked Rules history")
                    _revoke(conn, agent, target)
                    _revoke(conn, approver, target)
                for statement in payload.strip().split("\n-- statement boundary\n"):
                    conn.execute(text(statement))
                conn.execute(text("UPDATE rules_migrations SET complete=1 WHERE id=1"))
            for account in {agent, approver}:
                _ddl(conn, "GRANT SELECT ON " + target + " TO " + account)
                _ddl(conn, "GRANT UPDATE(" + ",".join(APPROVAL) + ") ON " + target + " TO " + account)
            _ddl(conn, "GRANT INSERT(" + ",".join(IDENTITY) + "),UPDATE(" + ",".join(PROOF) + ") ON " + target + " TO " + agent)
        finally:
            conn.execute(text("SELECT RELEASE_LOCK(:k)"), {"k": key})
    return {PAYLOAD.name: checksum}
