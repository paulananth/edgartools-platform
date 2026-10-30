"""Implicit DDL and runtime conversion failures must preserve Silver authority."""
import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Connection

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.silver_writer import mysql
from edgar_warehouse.silver_writer.database import migrate, register
from edgar_warehouse.silver_writer.relational import DatabaseSink
from edgar_warehouse.silver_writer.writer import land
from tests.unit.test_silver_writer import a_spec


@pytest.fixture
def store(database_factory):
    with database_factory() as values:
        assert values[0].dialect.name == "mysql"
        yield values


def test_empty_marker_interruption_recovers(store, monkeypatch):
    owner, runtime, role = store
    execute = Connection.execute
    def interrupted(conn, statement, *args, **kwargs):
        if str(statement).startswith("INSERT INTO silver_migrations"):
            raise RuntimeError("Invented interruption")
        return execute(conn, statement, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", interrupted)
        with pytest.raises(RuntimeError, match="interruption"): migrate(owner, runtime_role=role)
    assert migrate(owner, runtime_role=role)
    assert migrate(owner, runtime_role=role, existing_only=True)


def test_register_after_create_interruption_resumes_without_adopting_data(store, monkeypatch):
    owner, runtime, role = store
    migrate(owner, runtime_role=role)
    config = a_spec(links=[])
    execute = Connection.execute
    def interrupted(conn, statement, *args, **kwargs):
        if getattr(statement, "is_insert", False) and statement.table.name == "table_spec":
            raise RuntimeError("Invented interruption")
        return execute(conn, statement, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", interrupted)
        with pytest.raises(RuntimeError, match="interruption"): register(owner, config, runtime_role=role)
    assert register(owner, config, runtime_role=role)["created"]
    assert land(DatabaseSink(runtime), "visit", [{"visit_id": 1}])["inserted"] == 1
    assert not register(owner, config, runtime_role=role)["created"]


def test_permissive_session_is_refused_before_delivery(store):
    owner, runtime, role = store
    migrate(owner, runtime_role=role)
    register(owner, a_spec(links=[]), runtime_role=role)
    @event.listens_for(runtime, "checkout")
    def permissive(dbapi, record, proxy):
        with dbapi.cursor() as cursor: cursor.execute("SET SESSION sql_mode=''")
    with pytest.raises(Blocked, match="strict MySQL"):
        land(DatabaseSink(runtime), "visit", [{"visit_id": 2**63}])
    with runtime.connect() as conn: assert conn.scalar(text("SELECT COUNT(*) FROM visit")) == 0


def test_runtime_cannot_shadow_registry_with_a_temporary_table(store):
    from sqlalchemy.exc import DBAPIError
    owner, runtime, role = store
    migrate(owner, runtime_role=role)
    config = a_spec(links=[])
    register(owner, config, runtime_role=role)
    with pytest.raises(DBAPIError):
        with runtime.begin() as conn:
            conn.execute(text("CREATE TEMPORARY TABLE table_spec (table_name TEXT,spec LONGTEXT,sha256 TEXT)"))
    assert land(DatabaseSink(runtime), "visit", [{"visit_id": 1}])["inserted"] == 1


@pytest.mark.parametrize("table,column", [("table_spec", False), ("table_spec", True),
                                          ("silver_migrations", False), ("silver_migrations", True)])
def test_metadata_write_grants_are_refused(store, table, column):
    owner, runtime, role = store
    migrate(owner, runtime_role=role)
    quote = owner.dialect.identifier_preparer.quote_identifier
    field = "spec" if table == "table_spec" else "complete"
    with owner.begin() as conn:
        conn.execute(text("GRANT " + ("UPDATE(" + field + ")" if column else "UPDATE") + " ON "
                          + quote(owner.url.database) + "." + quote(table) + " TO '" + role + "'@'%'"))
    with pytest.raises(Blocked, match="metadata"): migrate(owner, runtime_role=role)


def test_partition_index_recovers_after_interrupted_create_and_populated_upgrade(store, monkeypatch):
    from sqlalchemy import inspect, select
    from edgar_warehouse.silver_writer.tables import data_table
    owner, runtime, role = store
    migrate(owner, runtime_role=role)
    config = a_spec(links=[])
    execute = Connection.execute
    def interrupted(conn, statement, *args, **kwargs):
        if statement.__class__.__name__ == "CreateIndex" and statement.element.name == "silver_partition":
            raise RuntimeError("Invented partition-index interruption")
        return execute(conn, statement, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", interrupted)
        with pytest.raises(RuntimeError, match="partition-index interruption"):
            register(owner, config, runtime_role=role)
    assert register(owner, config, runtime_role=role)["created"]
    sink = DatabaseSink(runtime)
    land(sink, config["table"], [{"visit_id": 1, "visited_on": "2026-10-01"}])
    table = data_table(config, "mysql")
    with runtime.connect() as conn:
        before = conn.execute(select(table)).mappings().all()
    # A pre-index installation has the same approved spec and populated rows.
    with owner.begin() as conn:
        conn.execute(text("DROP INDEX silver_partition ON visit"))
    assert not register(owner, config, runtime_role=role)["created"]
    with runtime.connect() as conn:
        assert conn.execute(select(table)).mappings().all() == before
    with owner.connect() as conn:
        assert any(i["name"] == "silver_partition" and i["column_names"] == config["partition"]
                   for i in inspect(conn).get_indexes("visit"))
    assert land(sink, config["table"], [{"visit_id": 1, "visited_on": "2026-10-01"}])["inserted"] == 0


def test_runtime_cannot_change_partition_index(store):
    from sqlalchemy.exc import DBAPIError
    owner, runtime, role = store
    migrate(owner, runtime_role=role)
    register(owner, a_spec(links=[]), runtime_role=role)
    with pytest.raises(DBAPIError):
        with runtime.begin() as conn:
            conn.execute(text("DROP INDEX silver_partition ON visit"))


def test_calendar_interval_refusal_preserves_existing_rows(store):
    owner, runtime, role = store
    migrate(owner, runtime_role=role)
    config = a_spec(links=[], columns=[{"name": "visit_id", "type": "BIGINT", "nullable": False},
                                     {"name": "duration", "type": "INTERVAL", "nullable": True}],
                    partition=[], time={"as_of": None, "as_at": "loaded_at", "event_time": None})
    register(owner, config, runtime_role=role)
    sink = DatabaseSink(runtime)
    from datetime import timedelta
    assert land(sink, "visit", [{"visit_id": 1, "duration": timedelta(days=2)}])["inserted"] == 1
    with pytest.raises(Blocked):
        land(sink, "visit", [{"visit_id": 2, "duration": timedelta(days=1)},
                            {"visit_id": 3, "duration": "1 month"}])
    with runtime.connect() as conn:
        assert conn.scalar(text("SELECT COUNT(*) FROM visit")) == 1
