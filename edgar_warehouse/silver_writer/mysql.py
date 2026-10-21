"""Owner installation and recoverable spec registration on dedicated MySQL storage."""
from contextlib import contextmanager
import hashlib
import re
from pathlib import Path

from sqlalchemy import UniqueConstraint, inspect, insert, select, text

from edgar_warehouse.control_contract import Blocked, digest
from . import spec as specs
from .storage import registry
from .tables import data_table, staging_name

PAYLOAD = Path(__file__).parent / "migrations/mysql-v1.sql"


def separate(conn, role):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,31}", role):
        raise Blocked("An existing restricted runtime account is required")
    if (conn.scalar(text("SELECT SUBSTRING_INDEX(CURRENT_USER(),'@',1)=:r"), {"r": role})
            or conn.scalar(text("SELECT COUNT(*) FROM mysql.user WHERE User=:r AND Host='%'"), {"r": role}) != 1):
        raise Blocked("Separate schema owner and restricted runtime are required")
    grantee = "'" + role + "'@'%'"
    grants = [row[0] for row in conn.execute(text("SHOW GRANTS FOR " + grantee))]
    if any((" ON *.* " in row and not row.startswith("GRANT USAGE ")) or "WITH GRANT OPTION" in row
           or " ON " not in row for row in grants):
        raise Blocked("Runtime inherits administrative or role privileges")
    params = {"g": grantee, "r": role, "d": conn.engine.url.database}
    if (conn.scalar(text("SELECT @@mandatory_roles")) not in ("", "NONE")
        or conn.scalar(text("SELECT COUNT(*) FROM mysql.role_edges WHERE TO_USER=:r AND TO_HOST='%'"), params)
        or conn.scalar(text("SELECT COUNT(*) FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d "
                            ""), params)
        or conn.scalar(text("SELECT COUNT(*) FROM information_schema.TABLE_PRIVILEGES WHERE GRANTEE=:g AND TABLE_SCHEMA=:d "
                            "AND PRIVILEGE_TYPE NOT IN ('SELECT','INSERT','UPDATE','DELETE')"), params)):
        raise Blocked("Runtime inherits broad or administrative storage privileges")
    for source in ("TABLE_PRIVILEGES", "COLUMN_PRIVILEGES"):
        if conn.scalar(text("SELECT COUNT(*) FROM information_schema." + source + " WHERE GRANTEE=:g AND TABLE_SCHEMA=:d "
                            "AND TABLE_NAME IN ('silver_migrations','table_spec') AND PRIVILEGE_TYPE<>'SELECT'"), params):
            raise Blocked("Runtime can mutate registration or migration metadata")
    return grantee


@contextmanager
def owner(engine, role):
    if not engine.url.database:
        raise Blocked("Silver requires its configured isolated database")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if not str(conn.scalar(text("SELECT VERSION()"))).startswith("8."):
            raise Blocked("Silver requires MySQL 8")
        account = separate(conn, role)
        lock = "silver_" + hashlib.sha256(engine.url.database.encode()).hexdigest()[:40]
        if conn.scalar(text("SELECT GET_LOCK(:n,30)"), {"n": lock}) != 1:
            raise Blocked("Silver owner lock unavailable")
        try: yield conn, account
        finally: conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": lock})


def migrate(engine, *, runtime_role, existing_only=False):
    payload = PAYLOAD.read_text()
    checksum = hashlib.sha256(payload.encode()).hexdigest()
    with owner(engine, runtime_role) as (conn, account):
        names = set(inspect(conn).get_table_names())
        if "silver_migrations" not in names:
            if existing_only: raise Blocked("Silver is not initialized; run silver init first")
            if names: raise Blocked("Refusing to adopt untracked Silver storage")
            conn.execute(text("CREATE TABLE silver_migrations (id SMALLINT PRIMARY KEY, checksum CHAR(64) NOT NULL, "
                              "complete SMALLINT NOT NULL) ENGINE=InnoDB COMMENT='silver-native:" + checksum + "'"))
        held = conn.execute(text("SELECT checksum,complete FROM silver_migrations WHERE id=1")).first()
        if held is None:
            if (set(inspect(conn).get_table_names()) != {"silver_migrations"}
                or inspect(conn).get_table_comment("silver_migrations")["text"] != "silver-native:" + checksum
                or {c["name"] for c in inspect(conn).get_columns("silver_migrations")} != {"id", "checksum", "complete"}
                or conn.scalar(text("SELECT COUNT(*) FROM silver_migrations"))):
                raise Blocked("Untracked Silver migration metadata")
            conn.execute(text("INSERT INTO silver_migrations VALUES (1,:h,0)"), {"h": checksum})
        elif held.checksum != checksum:
            raise Blocked("Installed Silver migration checksum differs")
        # A completed frozen installation is never dismantled on a rerun.
        if held is None or not held.complete:
            for statement in payload.strip().split("\n-- statement boundary\n"):
                conn.execute(text(statement))
            conn.execute(text("UPDATE silver_migrations SET complete=1 WHERE id=1"))
        quote = conn.dialect.identifier_preparer.quote_identifier
        database = quote(engine.url.database)
        conn.execute(text("GRANT SELECT ON " + database + ".table_spec TO " + account))
        conn.execute(text("GRANT EXECUTE ON PROCEDURE " + database + ".lock_silver_table TO " + account))
    return {PAYLOAD.name: checksum}


def register(engine, spec, *, runtime_role):
    spec = specs.check(spec)
    checksum = digest(spec)
    name = spec["table"]
    # MySQL names cannot differ only by case on all supported installations.
    columns = specs.columns(spec)
    if len({c.casefold() for c in columns}) != len(columns) or "_silver_key" in {c.casefold() for c in columns}:
        raise Blocked("MySQL cannot preserve these distinct configured column names")
    with owner(engine, runtime_role) as (conn, account):
        held_migration = conn.execute(text("SELECT checksum,complete FROM silver_migrations WHERE id=1")).first()
        if not held_migration or not held_migration.complete or held_migration.checksum != hashlib.sha256(PAYLOAD.read_bytes()).hexdigest():
            raise Blocked("Silver migration incomplete or differs from this build")
        catalog = registry("mysql")
        held = conn.scalar(select(catalog.c.sha256).where(catalog.c.table_name == name))
        if held and held != checksum:
            raise Blocked(f"silver.{name} holds another spec; a changed spec is registered as a new table")
        table = data_table(spec, "mysql")
        q = conn.dialect.identifier_preparer.quote_identifier
        table.append_constraint(UniqueConstraint(table.c._silver_key, name="silver_key"))
        table.comment = "silver-spec:" + checksum
        for column in table.c:
            source = next((c for c in spec["columns"] if c["name"] == column.name), None)
            column.comment = ((source.get("definition") or source.get("source") or "Configured source field")
                              if source else "Configured derived Silver field")
        if conn.scalar(text("SELECT @@lower_case_table_names")) and name != name.lower():
            raise Blocked("MySQL configuration cannot preserve the configured table name's case")
        stage = data_table(spec, "mysql", temporary=staging_name(spec))
        stage.comment = "silver-stage:" + checksum
        for physical in (table, stage):
            names = inspect(conn).get_table_names()
            if physical.name not in names:
                if held: raise Blocked("Registered Silver physical table is absent")
                physical.create(conn)
            elif not held:
                # Implicit DDL can leave an empty table before registration.
                # Recover only the same spec, shape, uniqueness and empty data.
                def type_name(value):
                    return re.sub(r" character set \w+", "", str(value.compile(dialect=conn.dialect)).lower()).replace("numeric(", "decimal(")
                if (inspect(conn).get_table_comment(physical.name)["text"] != physical.comment
                    or [(c["name"], type_name(c["type"]), c["nullable"]) for c in inspect(conn).get_columns(physical.name)] !=
                       [(c.name, type_name(c.type), c.nullable) for c in physical.c]
                    or (physical is table and not any(i["unique"] and i["column_names"] == ["_silver_key"]
                        for i in inspect(conn).get_indexes(physical.name)))
                    or conn.scalar(select(1).select_from(physical).limit(1)) is not None):
                    raise Blocked("Silver table exists without a registered spec; refusing to adopt it")
        if not held:
            # Table DDL commits implicitly. The registration becomes visible only
            # after physical storage exists; retries restore grants after a crash.
            conn.execute(insert(catalog).values(table_name=name, spec=spec, sha256=checksum))
        for physical in (table, stage):
            target = q(engine.url.database) + "." + q(physical.name)
            conn.execute(text("GRANT SELECT,INSERT,UPDATE,DELETE ON " + target + " TO " + account))
    return {"table": name, "sha256": checksum, "created": not bool(held)}
