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


@pytest.mark.parametrize("interrupt_before", ["ALTER TABLE code_label ADD COLUMN", "UPDATE code SET _search_tokens="])
def test_populated_word_index_upgrade_recovers_without_changing_published_pin(store, monkeypatch, tmp_path, interrupt_before):
    from argparse import Namespace
    from edgar_warehouse.rdm import storage
    from edgar_warehouse.rdm.context import CodeContext

    owner, runtime, arguments = store
    # Install the frozen v1 schema and populate it through its normal caller.
    with monkeypatch.context() as patch:
        patch.setattr(mysql_migration, "_search_migration", lambda *args: None)
        patch.setattr(storage, "refresh_search_tokens", lambda *args, **kwargs: None)
        migrate(owner, **arguments)
        reference = RDM(runtime, reserved_subjects=())
        reference.draft({"code_set": "invented", "name": "Invented"}, "1",
                        [{"code": "a", "label": "AI the reference"}], created_by="drafter",
                        labels=[{"code": "a", "label": "An alternate", "kind": "synonym"}])
        reference.approve("invented", "1", by="operator", words="Approve this invented version")
        reference.publish("invented", "1", out=tmp_path)
    before = reference.verify("invented", "1")
    version = reference.version("invented", "1")
    artifact = (tmp_path / "invented" / "1" / "canonical.jsonl").read_bytes()
    execute = Connection.execute
    def interrupted(self, statement, *args, **kwargs):
        if str(statement).startswith(interrupt_before):
            raise RuntimeError("Invented search backfill interruption")
        return execute(self, statement, *args, **kwargs)
    with runtime.begin() as admitted:
        admitted.execute(text("SELECT 1"))
        with monkeypatch.context() as patch:
            patch.setattr(Connection, "execute", interrupted)
            with pytest.raises(RuntimeError, match="backfill interruption"):
                migrate(owner, **arguments)
        with pytest.raises(DBAPIError):
            admitted.execute(text("UPDATE code SET label='Changed'"))
    with pytest.raises(Blocked, match="incomplete"):
        reference.code_sets()
    installed = migrate(owner, existing_only=True, **arguments)
    assert migrate(owner, existing_only=True, **arguments) == installed
    assert reference.verify("invented", "1") == before
    assert reference.version("invented", "1") == version
    assert (tmp_path / "invented" / "1" / "canonical.jsonl").read_bytes() == artifact
    for words, method in [("AI", "label"), ("the", "label"), ("an", "synonym"), ("-absent", "label")]:
        args = Namespace(subject="invented", key=None, as_of=None, as_at=None, hops=1,
                         relationship_type=None, search=words, detail="brief", page=None, limit=5)
        assert CodeContext(runtime).answer(args)["matches"][0]["matched_by"] == method
    with pytest.raises(DBAPIError, match="Only a draft"):
        with runtime.begin() as conn:
            conn.execute(text("UPDATE code SET _search_tokens=''"))


def test_search_migration_drift_does_not_disable_installed_store(store, monkeypatch, tmp_path):
    owner, runtime, arguments = store
    migrate(owner, **arguments)
    changed = tmp_path / "search.sql"
    changed.write_text(mysql_migration.SEARCH_MIGRATION.read_text() + "\n-- invented drift\n")
    monkeypatch.setattr(mysql_migration, "SEARCH_MIGRATION", changed)
    with pytest.raises(Blocked, match="checksum differs"):
        migrate(owner, **arguments)
    assert RDM(runtime).code_sets() == []
