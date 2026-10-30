"""Owner-installed MySQL control capabilities, independent of workload stores."""
import hashlib
import json
import re
from pathlib import Path

from sqlalchemy import inspect, text

from .config import Blocked, canonical
from .storage import tables

PAYLOAD = Path(__file__).parent / "migrations/mysql-v1.sql"
CAPABILITIES = ("start_run", "claim", "heartbeat", "wait_work", "report", "verify_claim", "finish", "finish_resource", "finish_expand", "delivery", "block_run")
NATIVE_CAPABILITIES = ("record_run_checks", "resume_run_prepared")
OWNED_TABLES = {table.name for table in tables("mysql").values()}


def _restricted(conn, principal):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,31}", principal):
        raise Blocked("An existing restricted control login is required")
    params = {"r": principal, "d": conn.engine.url.database}
    if conn.scalar(text("SELECT COUNT(*) FROM mysql.user WHERE User=:r"), params) != 1:
        raise Blocked("One unambiguous existing restricted control account is required")
    host = conn.scalar(text("SELECT Host FROM mysql.user WHERE User=:r"), params)
    params.update(h=host, g="'" + principal + "'@'" + host + "'")
    quote = conn.dialect.identifier_preparer.quote_identifier
    # text() escapes DBAPI percent signs itself; the identifier preparer has
    # already escaped them for raw driver SQL, so remove that layer here.
    account = (quote(principal) + "@" + quote(host)).replace("%%", "%")
    if conn.scalar(text("SELECT SUBSTRING_INDEX(CURRENT_USER(),'@',1)")) == principal:
        raise Blocked("A separate migration owner is required")
    grants = [row[0] for row in conn.execute(text("SHOW GRANTS FOR " + account))]
    if any((" ON *.* " in row and not row.startswith("GRANT USAGE ")) or "WITH GRANT OPTION" in row for row in grants):
        raise Blocked("Control runtime inherits administrative privileges")
    if conn.scalar(text("SELECT @@mandatory_roles")) not in ("", "NONE"):
        raise Blocked("Mandatory roles must be qualified before control installation")
    for membership in conn.execute(text("SELECT FROM_USER,FROM_HOST,WITH_ADMIN_OPTION FROM mysql.role_edges WHERE TO_USER=:r AND TO_HOST=:h"), params):
        if membership.FROM_HOST != "%" or membership.WITH_ADMIN_OPTION != "N" or not re.fullmatch(r"bk_(worker|verifier)_[0-9a-f]{20}", membership.FROM_USER):
            raise Blocked("Control runtime inherits an unqualified role")
        role_account = "'" + membership.FROM_USER + "'@'%'"
        inherited = [row[0] for row in conn.execute(text("SHOW GRANTS FOR " + role_account))]
        if any(not row.startswith("GRANT USAGE ON *.* ") for row in inherited):
            raise Blocked("Control profile role has privileges beyond its duty")
    if conn.scalar(text("SELECT COUNT(*) FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d"), params):
        raise Blocked("Control runtime inherits database-wide privileges")
    if conn.scalar(text("SELECT COUNT(*) FROM information_schema.COLUMN_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d"), params):
        raise Blocked("Control runtime has direct control writes")
    owned = {table.name for table in tables("mysql").values()}
    for row in conn.execute(text("SELECT TABLE_NAME,PRIVILEGE_TYPE FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d"), params):
        if row.TABLE_NAME not in owned or row.PRIVILEGE_TYPE != "SELECT":
            raise Blocked("Control runtime can mutate control storage")
    for row in conn.execute(text("SELECT Routine_name,Proc_priv FROM mysql.procs_priv WHERE Db=:d AND User=:r AND Host=:h"), params):
        if row.Routine_name not in {"bookkeeping_" + name for name in (*CAPABILITIES, *NATIVE_CAPABILITIES)} or str(row.Proc_priv).lower() != "execute":
            raise Blocked("Control runtime can administer capabilities")
    return account


def _revoke(conn, database):
    """Revoke every existing caller before a nontransactional DDL rebuild."""
    quote = conn.dialect.identifier_preparer.quote_identifier
    for row in conn.execute(text("SELECT GRANTEE,TABLE_NAME FROM information_schema.TABLE_PRIVILEGES WHERE TABLE_SCHEMA=:d AND PRIVILEGE_TYPE='SELECT'"), {"d": database}).all():
        conn.execute(text("REVOKE SELECT ON " + quote(database) + "." + quote(row.TABLE_NAME) + " FROM " + row.GRANTEE))
    for row in conn.execute(text("SELECT User,Host,Routine_name FROM mysql.procs_priv WHERE Db=:d AND FIND_IN_SET('Execute',Proc_priv)"), {"d": database}).all():
        account = "'" + row.User.replace("'", "''") + "'@'" + row.Host.replace("'", "''") + "'"
        conn.execute(text("REVOKE EXECUTE ON PROCEDURE " + quote(database) + "." + quote(row.Routine_name) + " FROM " + account))


def _table_fingerprint(conn):
    inspector = inspect(conn)
    if set(inspector.get_table_names()) != OWNED_TABLES | {"bookkeeping_migrations"}:
        return None
    quote = conn.dialect.identifier_preparer.quote_identifier
    definitions = []
    for name in sorted(OWNED_TABLES):
        if inspector.get_table_comment(name)["text"] != "bookkeeping-storage-v1":
            return None
        definitions.append(conn.execute(text("SHOW CREATE TABLE " + quote(name))).first()[1])
    return hashlib.sha256(json.dumps(definitions, ensure_ascii=False).encode()).hexdigest()


def _guard_fingerprint(conn):
    if conn.scalar(text("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=:d"), {"d": conn.engine.url.database}):
        return None
    definitions = [tuple(row) for row in conn.execute(text(
        "SELECT ROUTINE_NAME,ROUTINE_TYPE,ROUTINE_DEFINITION,SECURITY_TYPE,SQL_DATA_ACCESS,SQL_MODE,DEFINER "
        "FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=:d ORDER BY ROUTINE_NAME"), {"d": conn.engine.url.database})]
    expected = {"bookkeeping_" + name for name in (*CAPABILITIES, *NATIVE_CAPABILITIES,
        "require_ready", "require", "lock_work", "live", "authority", "prepare_children", "compare_checkpoint")
        if name not in {"finish_expand", "finish_resource"}}
    if {row[0] for row in definitions} != expected or any(row[2] is None or row[3] != "DEFINER" for row in definitions):
        return None
    return hashlib.sha256(json.dumps(definitions, ensure_ascii=False).encode()).hexdigest()


def migrate(engine, *, runtime_role, existing_only, database_name):
    payload = PAYLOAD.read_text()
    checksum = hashlib.sha256(payload.encode()).hexdigest()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if conn.scalar(text("SELECT DATABASE()")) != database_name or not str(conn.scalar(text("SELECT VERSION()"))).startswith("8."):
            raise Blocked("Control migration requires its configured database on MySQL 8")
        account = _restricted(conn, runtime_role)
        key = "bookkeeping-owner:" + hashlib.sha256(database_name.encode()).hexdigest()[:40]
        if conn.scalar(text("SELECT GET_LOCK(:k,30)"), {"k": key}) != 1:
            raise Blocked("Control migration lock unavailable")
        try:
            names = set(inspect(conn).get_table_names())
            if "bookkeeping_migrations" not in names:
                if existing_only:
                    raise Blocked("Bookkeeping is not initialized; run bookkeeping init first")
                if names:
                    raise Blocked("Refusing to adopt untracked control storage")
                conn.execute(text("CREATE TABLE bookkeeping_migrations (id BIGINT PRIMARY KEY,checksum CHAR(64) NOT NULL,complete BIGINT NOT NULL,table_checksum CHAR(64),guard_checksum CHAR(64)) ENGINE=InnoDB COMMENT='bookkeeping-native:" + checksum + "'"))
            held = conn.execute(text("SELECT checksum,complete,table_checksum,guard_checksum FROM bookkeeping_migrations WHERE id=1")).first()
            if held is None:
                inspector = inspect(conn)
                shape = [(column["name"], str(column["type"].compile(dialect=conn.dialect)).upper(), column["nullable"])
                         for column in inspector.get_columns("bookkeeping_migrations")]
                if (set(inspector.get_table_names()) != {"bookkeeping_migrations"}
                    or inspector.get_table_comment("bookkeeping_migrations")["text"] != "bookkeeping-native:" + checksum
                    or shape != [("id", "BIGINT", False), ("checksum", "CHAR(64)", False), ("complete", "BIGINT", False), ("table_checksum", "CHAR(64)", True), ("guard_checksum", "CHAR(64)", True)]
                    or inspector.get_pk_constraint("bookkeeping_migrations")["constrained_columns"] != ["id"]
                    or conn.scalar(text("SELECT COUNT(*) FROM bookkeeping_migrations"))):
                    raise Blocked("Untracked control migration metadata")
                conn.execute(text("INSERT INTO bookkeeping_migrations(id,checksum,complete) VALUES(1,:h,0)"), {"h": checksum})
                held = conn.execute(text("SELECT checksum,complete,table_checksum,guard_checksum FROM bookkeeping_migrations WHERE id=1")).first()
            if held.checksum != checksum or conn.scalar(text("SELECT COUNT(*) FROM bookkeeping_migrations WHERE id<>1 OR complete NOT IN(0,1)")):
                raise Blocked("Control migration history differs from this build")
            if held.complete and (not held.table_checksum or not held.guard_checksum):
                _revoke(conn, database_name)
                raise Blocked("Installed control definitions differ")
            if held.table_checksum and _table_fingerprint(conn) != held.table_checksum:
                _revoke(conn, database_name)
                raise Blocked("Installed control storage differs; restore it before recovery")
            if not held.complete:
                _revoke(conn, database_name)
                if not held.table_checksum:
                    for name in names - {"bookkeeping_migrations"}:
                        if name not in OWNED_TABLES or inspect(conn).get_table_comment(name)["text"] != "bookkeeping-storage-v1" or conn.scalar(text("SELECT COUNT(*) FROM " + conn.dialect.identifier_preparer.quote_identifier(name))):
                            raise Blocked("Refusing untracked or populated initial control storage")
                from .run_storage import execute_ddl
                for statement in payload.strip().split("\n-- statement boundary\n"):
                    execute_ddl(conn, statement)
                table_checksum, guard_checksum = _table_fingerprint(conn), _guard_fingerprint(conn)
                if table_checksum is None or guard_checksum is None:
                    raise Blocked("Installed control definitions differ")
                conn.execute(text("UPDATE bookkeeping_migrations SET complete=1,table_checksum=:t,guard_checksum=:g WHERE id=1"), {"t": table_checksum, "g": guard_checksum})
            elif not held.guard_checksum or _guard_fingerprint(conn) != held.guard_checksum:
                _revoke(conn, database_name)
                raise Blocked("Installed control definitions differ")
            quote = conn.dialect.identifier_preparer.quote_identifier
            for table in tables("mysql").values():
                conn.execute(text("GRANT SELECT ON " + quote(database_name) + "." + quote(table.name) + " TO " + account))
            for operation in sorted({"finish" if name.startswith("finish_") else name for name in (*CAPABILITIES, *NATIVE_CAPABILITIES)}):
                conn.execute(text("GRANT EXECUTE ON PROCEDURE " + quote(database_name) + ".bookkeeping_" + operation + " TO " + account))
        finally:
            conn.execute(text("SELECT RELEASE_LOCK(:k)"), {"k": key})
    return {PAYLOAD.name: checksum}


def call(engine, operation, params):
    if operation not in CAPABILITIES:
        raise Blocked("Unsupported control storage capability")
    if operation == "start_run":
        params = {**params, "i": [{**entry, "resources": canonical(entry["resources"]), "unit": canonical(entry["unit"]), "cursor": canonical(entry["unit"]["cursor"])}
                                  for entry in json.loads(params["i"])]}
    elif operation == "finish_expand":
        params = {**params, "children": [{**entry, "resources": canonical(entry["resources"]),
                  "unit": canonical(entry["unit"]), "cursor": canonical(entry["unit"]["cursor"])}
                  for entry in json.loads(params["children"])]}
    params = {**params, "operation": operation}
    routine = "finish" if operation.startswith("finish_") else operation
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        result = conn.execute(text("CALL bookkeeping_" + routine + "(:w)"), {"w": canonical(params)})
        value = result.scalar() if result.returns_rows else None
        return json.loads(value) if value is not None else None


def grant_profile(engine, *, profile, worker, verifier):
    granted = {}
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for duty, login in (("worker", worker), ("verifier", verifier)):
            account = _restricted(conn, login)
            role = "bk_" + duty + "_" + hashlib.sha256(profile.encode()).hexdigest()[:20]
            group = "'" + role + "'@'%'"
            if not conn.scalar(text("SELECT COUNT(*) FROM mysql.user WHERE User=:r AND Host='%'"), {"r": role}):
                conn.execute(text("CREATE ROLE " + group))
            inherited = [row[0] for row in conn.execute(text("SHOW GRANTS FOR " + group))]
            if any(not row.startswith("GRANT USAGE ON *.* ") for row in inherited):
                raise Blocked("Control profile role has privileges beyond its duty")
            conn.execute(text("GRANT " + group + " TO " + account))
            granted[duty] = {"role": role, "login": login}
    return granted
