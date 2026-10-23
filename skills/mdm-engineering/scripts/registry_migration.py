"""Owner installation of a governed registry; values and vocabulary are data."""

import re
from hashlib import sha256
from types import SimpleNamespace

from sqlalchemy import (
    CheckConstraint,
    Column,
    Integer,
    String,
    Table,
    UnicodeText,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.schema import CreateTable

if __package__:
    from . import database_adapter as api
    from .adapter_model import ExactJSON, native_registry_model
else:
    import database_adapter as api
    from adapter_model import ExactJSON, native_registry_model

PREFIX = "mdm_store"
VERSION = 1


def verify_postgres_registry(conn):
    """Read back the established registry contract without replacing its DDL."""
    expected = {
        "policy": {"digest": "TEXT", "body": "JSONB"},
        "dataset": {"source_code": "TEXT", "registry_version": "UUID", "body": "JSONB"},
        "dataset_mapping": {
            "source_code": "TEXT",
            "mapping_version": "BIGINT",
            "body": "JSONB",
            "registry_version": "UUID",
            "registered_at": "TIMESTAMP WITH TIME ZONE",
        },
        "master_kind": {"kind": "TEXT", "enabled": "BOOLEAN"},
    }
    keys = {
        "policy": ["digest"],
        "dataset": ["source_code"],
        "dataset_mapping": ["source_code", "mapping_version"],
        "master_kind": ["kind"],
    }
    inspector = inspect(conn)
    for name, fields in expected.items():
        columns = inspector.get_columns(name, schema="mdm")
        if {c["name"] for c in columns} != set(fields):
            raise api.AdapterError("Installed registry columns differ from this build")
        if any(
            c["nullable"]
            or str(c["type"].compile(dialect=conn.dialect)) != fields[c["name"]]
            for c in columns
        ):
            raise api.AdapterError(
                "Installed registry column contract differs from this build"
            )
        if (
            inspector.get_pk_constraint(name, schema="mdm")["constrained_columns"]
            != keys[name]
        ):
            raise api.AdapterError("Installed registry key differs from this build")


def contract():
    """Versioned logical objects, compiled once for the selected engine."""
    metadata, tables = native_registry_model("mysql")
    tables["registry_migration"] = Table(
        "registry_migration",
        metadata,
        Column("version", Integer, primary_key=True, autoincrement=False),
        Column("checksum", String(64), nullable=False),
        Column("complete", Integer, nullable=False),
        CheckConstraint("complete IN (0,1)"),
        Column("initialized", Integer, nullable=False),
        CheckConstraint("initialized IN (0,1)"),
    )
    tables["registry_catalog"] = Table(
        "registry_catalog",
        metadata,
        Column("digest", String(64), primary_key=True),
        Column("body", ExactJSON(), nullable=False),
    )
    tables["registry_state"] = Table(
        "registry_state",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("configuration", String(64), nullable=False),
        Column("complete", Integer, nullable=False),
        CheckConstraint("id=1"),
        CheckConstraint("complete IN (0,1)"),
    )
    tables["master_kind"] = Table(
        "master_kind",
        metadata,
        Column("kind_key", String(64), primary_key=True),
        Column(
            "kind",
            UnicodeText().with_variant(
                LONGTEXT(charset="utf8mb4", collation="utf8mb4_0900_bin"), "mysql"
            ),
            nullable=False,
        ),
        Column("enabled", Integer, nullable=False),
        CheckConstraint("enabled IN (0,1)"),
    )
    for table in tables.values():
        table.dialect_options["mysql"].update(
            engine="InnoDB", charset="utf8mb4", collate="utf8mb4_0900_bin"
        )
        if "body" in table.c:
            table.append_constraint(CheckConstraint("JSON_VALID(body)"))
    tables["dataset_mapping"].append_constraint(CheckConstraint("mapping_version>0"))
    dialect = mysql.dialect()

    def ddl(table):
        result = str(CreateTable(table).compile(dialect=dialect))
        # These independent table options are emitted in hash-seed order.
        result = re.sub(
            r"\)(?:ENGINE=InnoDB|CHARSET=utf8mb4|COLLATE utf8mb4_0900_bin|\s)+$",
            ") ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_0900_bin\n",
            result,
        )
        return result

    statements = {name: ddl(table) for name, table in tables.items()}
    guards = {}
    for table in ("policy", "dataset", "dataset_mapping", "registry_catalog"):
        for event in ("UPDATE", "DELETE"):
            name = table + "_immutable_" + event.lower()
            body = "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='immutable_registry_input'"
            sql = f"CREATE TRIGGER `{name}` BEFORE {event} ON `{table}` FOR EACH ROW {body}"
            guards[name] = (table, event, body, sql)
    checksum = sha256(
        "\n".join([*statements.values(), *(v[3] for v in guards.values())]).encode()
    ).hexdigest()
    return metadata, tables, statements, guards, checksum


def _verify_table(conn, table):
    found = inspect(conn)
    columns = found.get_columns(table.name)
    if {c["name"] for c in columns} != set(table.c.keys()):
        raise api.AdapterError("Installed registry columns differ from this build")
    normalize = lambda value: re.sub(
        r"\s+(CHARACTER SET|COLLATE)\s+\w+", "", str(value), flags=re.I
    ).lower()
    for column in columns:
        expected = table.c[column["name"]]
        actual_type = normalize(column["type"].compile(dialect=conn.dialect))
        expected_type = normalize(expected.type.compile(dialect=conn.dialect))
        if (
            column["nullable"] != expected.nullable
            or actual_type != expected_type
            or column.get("default") is not None
            or column.get("autoincrement")
        ):
            raise api.AdapterError(
                "Installed registry column contract differs from this build"
            )
    for row in conn.execute(
        text(
            "SELECT CHARACTER_SET_NAME,COLLATION_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t"
        ),
        {"t": table.name},
    ):
        if row[0] is not None and tuple(row) != ("utf8mb4", "utf8mb4_0900_bin"):
            raise api.AdapterError(
                "Installed registry column collation differs from this build"
            )
    if found.get_pk_constraint(table.name)["constrained_columns"] != [
        c.name for c in table.primary_key
    ]:
        raise api.AdapterError("Installed registry key differs from this build")
    options = found.get_table_options(table.name)
    if (
        options.get("mysql_engine") != "InnoDB"
        or options.get("mysql_collate") != "utf8mb4_0900_bin"
    ):
        raise api.AdapterError(
            "Installed registry table options differ from this build"
        )
    normalize_check = lambda sql: re.sub(r"[\s`()]+", "", sql).lower()
    expected_checks = {
        normalize_check(str(c.sqltext))
        for c in table.constraints
        if isinstance(c, CheckConstraint)
    }
    actual_checks = {
        normalize_check(c["sqltext"]) for c in found.get_check_constraints(table.name)
    }
    if expected_checks != actual_checks:
        raise api.AdapterError("Installed registry constraints differ from this build")


def require_ready(conn, configuration=None):
    """A shared row lock pins readiness through the caller's transaction."""
    _, tables, _, _, checksum = contract()
    try:
        state = (
            conn.execute(
                select(tables["registry_state"])
                .where(tables["registry_state"].c.id == 1)
                .with_for_update(read=True)
            )
            .mappings()
            .first()
        )
        migration = (
            conn.execute(
                select(tables["registry_migration"])
                .where(tables["registry_migration"].c.version == VERSION)
                .with_for_update(read=True)
            )
            .mappings()
            .first()
        )
    except api.DBAPIError as exc:
        if getattr(exc.orig, "args", ())[0:1] == (1146,):
            raise api.AdapterError("Governed registry is not initialized") from None
        raise api.AdapterError("Governed registry read failed") from None
    if not state or not migration or not state["complete"] or not migration["complete"]:
        raise api.AdapterError("Governed registry migration is pending")
    if migration["checksum"] != checksum:
        raise api.AdapterError("Governed registry build differs")
    if configuration is not None and state["configuration"] != configuration:
        raise api.AdapterError("Configured vocabulary differs from installed registry")
    catalog = conn.scalar(
        select(tables["registry_catalog"].c.body).where(
            tables["registry_catalog"].c.digest == state["configuration"]
        )
    )
    if (
        catalog is None
        or sha256(api.canonical(catalog)).hexdigest() != state["configuration"]
    ):
        raise api.AdapterError("Installed configuration differs from its fingerprint")
    return state["configuration"]


def migrate(engine, *, runtime_role, configuration, kinds, runtime_host="%"):
    """Install MySQL governance and a read-only future prepared-effect store."""
    if engine.dialect.name != "mysql":
        raise api.AdapterError(
            "Native registry installation is qualified for MySQL only"
        )
    if (
        not isinstance(configuration, dict)
        or not isinstance(kinds, list)
        or not kinds
        or configuration.get("kinds") != kinds
        or any(not isinstance(k, str) or not k or k.strip() != k for k in kinds)
        or len(set(kinds)) != len(kinds)
    ):
        raise api.AdapterError(
            "A pinned configuration and distinct vocabulary are required"
        )
    metadata, tables, statements, guards, checksum = contract()
    configuration_key = sha256(api.canonical(configuration)).hexdigest()
    database = engine.url.database
    if not database or database.lower() in {
        "mysql",
        "sys",
        "information_schema",
        "performance_schema",
    }:
        raise api.AdapterError("Configure an isolated native store database")
    ledger = tables["registry_migration"]
    with (
        engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn,
        api._migration_lock(conn, "native_registry"),
    ):
        if conn.scalar(text("SELECT DATABASE()")) != database:
            raise api.AdapterError("Native registry requires its configured database")
        version = str(conn.scalar(text("SELECT VERSION()")))
        found = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
        if (
            not found
            or "mariadb" in version.lower()
            or not (8, 0, 21) <= tuple(map(int, found.groups())) < (9, 0, 0)
        ):
            raise api.AdapterError("Native registry requires supported MySQL 8")
        principal = SimpleNamespace(schema=database, tables={}, routines={})
        api._grants(conn, principal, runtime_role, runtime_host, runtime_execute=False)
        held_tables = set(inspect(conn).get_table_names())
        _, prepared = api.model(PREFIX, database, protocol=4)
        if held_tables - set(tables) - {t.name for t in prepared.values()}:
            raise api.AdapterError("Native database contains unrelated storage")
        if ledger.name not in held_tables:
            if held_tables:
                raise api.AdapterError("Refusing untracked native registry objects")
            conn.exec_driver_sql(
                statements[ledger.name].rstrip()
                + " COMMENT='native-registry:"
                + checksum
                + "'"
            )
        _verify_table(conn, ledger)
        saved = conn.execute(select(ledger)).mappings().all()
        if not saved:
            if (
                set(inspect(conn).get_table_names()) != {ledger.name}
                or inspect(conn).get_table_comment(ledger.name)["text"]
                != "native-registry:" + checksum
            ):
                raise api.AdapterError("Refusing an untracked empty registry marker")
            conn.execute(
                ledger.insert().values(
                    version=VERSION, checksum=checksum, complete=0, initialized=0
                )
            )
            saved = [
                {
                    "version": VERSION,
                    "checksum": checksum,
                    "complete": 0,
                    "initialized": 0,
                }
            ]
        if (
            len(saved) != 1
            or saved[0]["version"] != VERSION
            or saved[0]["checksum"] != checksum
        ):
            raise api.AdapterError("Installed registry migration checksum differs")
        fresh = not saved[0]["complete"]
        # The same transaction lock held by registry callers drains existing
        # transactions before this persistent DDL barrier is published.
        with engine.begin() as barrier:
            if "registry_state" in set(inspect(barrier).get_table_names()):
                barrier.execute(tables["registry_state"].update().values(complete=0))
            barrier.execute(ledger.update().values(complete=0))
        if saved[0]["initialized"] and set(tables) - held_tables:
            raise api.AdapterError(
                "Installed registry table is missing; restore retained storage"
            )
        for name, table in tables.items():
            if name not in set(inspect(conn).get_table_names()):
                conn.exec_driver_sql(statements[name])
            _verify_table(conn, table)
        for name, (table, event, body, sql) in guards.items():
            held = conn.execute(
                text(
                    "SELECT EVENT_OBJECT_TABLE,ACTION_TIMING,EVENT_MANIPULATION,ACTION_STATEMENT "
                    "FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=:d AND TRIGGER_NAME=:n"
                ),
                {"d": database, "n": name},
            ).first()
            if held is None:
                if saved[0]["initialized"]:
                    raise api.AdapterError("Installed registry guard is missing")
                conn.exec_driver_sql(sql)
            elif tuple(held) != (table, "BEFORE", event, body):
                raise api.AdapterError(
                    "Installed registry guard differs from this build"
                )
        principal.tables = tables
        api._grants(conn, principal, runtime_role, runtime_host, runtime_execute=False)
        # These capabilities are installed for the later normal Merge Stage
        # integration. Runtime execution is withheld until that path qualifies.
        result = api.migrate(
            engine,
            runtime_role=runtime_role,
            runtime_host=runtime_host,
            prefix=PREFIX,
            protocol=4,
            runtime_execute=False,
        )
        with engine.begin() as final:
            existing = final.scalar(
                select(tables["registry_catalog"].c.body).where(
                    tables["registry_catalog"].c.digest == configuration_key
                )
            )
            if existing is None:
                final.execute(
                    tables["registry_catalog"]
                    .insert()
                    .values(digest=configuration_key, body=configuration)
                )
            elif api.canonical(existing) != api.canonical(configuration):
                raise api.AdapterError("Installed configuration fingerprint collision")
            vocabulary = tables["master_kind"]
            final.execute(vocabulary.update().values(enabled=0))
            for kind in sorted(kinds):
                key = sha256(kind.encode()).hexdigest()
                old = final.scalar(
                    select(vocabulary.c.kind).where(vocabulary.c.kind_key == key)
                )
                if old is None:
                    final.execute(
                        vocabulary.insert().values(kind_key=key, kind=kind, enabled=1)
                    )
                elif old != kind:
                    raise api.AdapterError(
                        "Configured vocabulary fingerprint collision"
                    )
                else:
                    final.execute(
                        vocabulary.update()
                        .where(vocabulary.c.kind_key == key)
                        .values(enabled=1)
                    )
            state = tables["registry_state"]
            if final.scalar(select(state.c.id).where(state.c.id == 1)) is None:
                final.execute(
                    state.insert().values(
                        id=1, configuration=configuration_key, complete=1
                    )
                )
            else:
                final.execute(
                    state.update()
                    .where(state.c.id == 1)
                    .values(configuration=configuration_key, complete=1)
                )
            final.execute(ledger.update().values(complete=1, initialized=1))
    return {
        "migration": "native-registry-v1",
        "checksum": checksum,
        "installed": fresh,
        "engine": "mysql",
        "configuration": configuration_key,
        "kinds": len(kinds),
        "prepared_storage": result["migration"],
        "merge_supported": False,
    }
