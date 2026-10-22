"""DDL interruption cannot expose approved content or migration authority."""
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rdm import mysql_migration
from edgar_warehouse.rdm.database import migrate
from edgar_warehouse.rdm.store import RDM


@pytest.fixture
def store(database_factory):
    with database_factory() as (owner, runtime, role):
        assert owner.dialect.name == "mysql"
        yield owner, runtime, {"runtime_role": role, "database_name": owner.url.database}


def test_interrupt_after_marker_creation_resumes(store, monkeypatch):
    owner, runtime, arguments = store
    execute = Connection.execute
    def interrupted(self, statement, *args, **kwargs):
        if str(statement).startswith("INSERT INTO rdm_migrations"):
            raise RuntimeError("Invented interruption")
        return execute(self, statement, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Connection, "execute", interrupted)
        with pytest.raises(RuntimeError, match="interruption"):
            migrate(owner, **arguments)
    installed = migrate(owner, **arguments)
    assert migrate(owner, existing_only=True, **arguments) == installed
    assert RDM(runtime).code_sets() == []


def test_interrupted_guard_replacement_keeps_published_rows_protected(store, monkeypatch, tmp_path):
    owner, runtime, arguments = store
    migrate(owner, **arguments)
    reference = RDM(runtime, reserved_subjects=())
    reference.draft({"code_set": "invented", "name": "Invented"}, "1", [{"code": "a", "label": "First"}], created_by="drafter")
    reference.approve("invented", "1", by="operator", words="Approve this invented version")
    reference.publish("invented", "1", out=tmp_path)
    before = reference.verify("invented", "1")
    execute = Connection.execute
    def interrupted(self, statement, *args, **kwargs):
        if str(statement).startswith("CREATE TRIGGER `code_update_guard`"):
            raise RuntimeError("Invented interruption")
        return execute(self, statement, *args, **kwargs)
    with runtime.begin() as already_connected:
        already_connected.execute(text("SELECT 1"))
        with monkeypatch.context() as patch:
            patch.setattr(Connection, "execute", interrupted)
            with pytest.raises(RuntimeError, match="interruption"):
                migrate(owner, **arguments)
        with pytest.raises(DBAPIError):
            already_connected.execute(text("UPDATE code SET label='Changed'"))
    with pytest.raises(Blocked, match="incomplete"):
        reference.code_sets()
    migrate(owner, existing_only=True, **arguments)
    assert reference.verify("invented", "1") == before
    with pytest.raises(DBAPIError, match="Only a draft"):
        with runtime.begin() as conn:
            conn.execute(text("UPDATE code SET label='Changed'"))


@pytest.mark.parametrize("target,column", [("rdm_migrations", False), ("rdm_readiness", False),
                                           ("rdm_migrations", True), ("rdm_readiness", True)])
def test_metadata_write_grants_are_refused_before_changing_store(store, target, column):
    owner, runtime, arguments = store
    migrate(owner, **arguments)
    role = "'" + arguments["runtime_role"] + "'@'%'"
    quote = owner.dialect.identifier_preparer.quote_identifier
    with owner.begin() as conn:
        conn.execute(text("GRANT " + ("UPDATE(complete)" if column else "UPDATE") + " ON "
                          + quote(owner.url.database) + "." + quote(target) + " TO " + role))
    with pytest.raises(Blocked, match="migration metadata"):
        migrate(owner, **arguments)
    with runtime.connect() as conn:
        assert conn.scalar(text("SELECT complete FROM rdm_readiness")) == 1


def test_checksum_change_is_refused_without_disabling_installed_store(store, tmp_path, monkeypatch):
    owner, runtime, arguments = store
    migrate(owner, **arguments)
    changed = tmp_path / "changed.sql"
    changed.write_text(mysql_migration.MIGRATION.read_text() + "\n-- invented drift\n")
    monkeypatch.setattr(mysql_migration, "MIGRATION", changed)
    with pytest.raises(Blocked, match="checksum differs"):
        migrate(owner, **arguments)
    assert RDM(runtime).code_sets() == []
