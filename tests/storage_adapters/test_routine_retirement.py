"""Retire calculation routines without rewriting retained storage."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean import catalog, retirement
from edgar_warehouse.mdm.clean.store import Conflict, Store, digest, migrate
from tests.storage_adapters.test_prepared_effects import batch
from tests.mdm.test_configured_pair_comparison import configured_root  # noqa: F401


def routines(conn):
    return set(conn.scalars(text("""SELECT p.proname FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='mdm'""")))


def constraints(conn):
    return conn.execute(text("""SELECT c.conrelid::regclass::text,c.conname,
        pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_namespace n
        ON n.oid=c.connamespace WHERE n.nspname='mdm' ORDER BY 1,2""")).all()


@pytest.mark.parametrize("case", ["populated", "dependency", "checksum"])
def test_owner_routine_retirement(case, database_factory, configured_root, storage_api, monkeypatch):
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            with pytest.raises(ValueError, match="PostgreSQL"):
                migrate(owner, application_role=role, prepared=True)
            return
        # Install the preceding owner revision, then populate governed storage.
        real_retire = retirement.retire
        with monkeypatch.context() as before:
            before.setattr(retirement, "retire", lambda engine: None)
            migrate(owner, application_role=role, prepared=True)
        api = storage_api.Adapter(runtime, prefix="mdm_store", protocol=6)
        pins = {"catalog": digest(catalog.CATALOG)}
        b = batch(storage_api, governed=True, workflow=True, pins=pins, indexes=(),
                  objects=(storage_api.Effect("invented-kind", "one", {"value": 1}),))
        lease = api.claim(b.scope, "invented-worker")
        receipt = api.apply(b, lease, proposal_body={"command": "invented-retained-command"})
        retained = api.read([("invented-kind", "one")])
        if owner.dialect.name == "postgresql":
            with pytest.raises(Conflict, match="owner routine retirement"):
                Store(runtime)
            with owner.connect() as conn:
                assert len(routines(conn)) == 36
                old_constraints = constraints(conn)
                old_tables = conn.scalars(text("""SELECT tablename FROM pg_tables
                    WHERE schemaname='mdm' AND tablename<>'migration' ORDER BY tablename""")).all()
                snapshots = {name: conn.scalar(text(
                    f"SELECT md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text,'null')) FROM mdm.{owner.dialect.identifier_preparer.quote(name)} t")) for name in old_tables}
            if case == "dependency":
                with owner.begin() as conn:
                    conn.execute(text("CREATE VIEW mdm.invented_external_reader AS SELECT mdm.entity_name('{}'::jsonb)"))
                with pytest.raises(DBAPIError):
                    real_retire(owner)
                with pytest.raises(Conflict, match="owner routine retirement"):
                    Store(runtime)
                with owner.begin() as conn:
                    assert len(routines(conn)) == 36
                    assert conn.scalar(text("SELECT count(*) FROM mdm.migration WHERE name=:n"),
                                       {"n": retirement.MIGRATION}) == 0
                    conn.execute(text("DROP VIEW mdm.invented_external_reader"))
        migrate(owner, application_role=role, prepared=True)
        migrate(owner, application_role=role, prepared=True)
        assert Store(runtime).prepared
        assert api.read([("invented-kind", "one")]) == retained
        replay = api.replay(b.batch, lease, observer="invented-recovery")
        assert replay["duplicate"] and replay["generation"] == receipt["generation"] == 1
        if owner.dialect.name == "postgresql":
            with owner.connect() as conn:
                assert routines(conn) == {"immutable_row", "require_configured_kind"}
                assert constraints(conn) == old_constraints
                assert conn.scalar(text("""SELECT count(*) FROM pg_tables WHERE schemaname='mdm'
                    AND has_table_privilege(:role,format('%I.%I',schemaname,tablename),
                        'INSERT,UPDATE,DELETE,TRUNCATE')"""), {"role": role}) == 0
                for name, saved in snapshots.items():
                    assert conn.scalar(text(
                        f"SELECT md5(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text,'null')) FROM mdm.{owner.dialect.identifier_preparer.quote(name)} t")) == saved
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                conn.execute(text("SELECT mdm.save_batch('{}',gen_random_uuid())"))
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                conn.execute(text("DELETE FROM mdm.migration"))
            with pytest.raises(DBAPIError, match="not enabled"), owner.begin() as conn:
                conn.execute(text("""INSERT INTO mdm.master_entity(entity_id,kind,published_at)
                    VALUES(gen_random_uuid(),'invented-disabled-kind',now())"""))
            # The historical ledger still refuses modification at the database.
            with pytest.raises(DBAPIError), owner.begin() as conn:
                conn.execute(text("UPDATE mdm.migration SET checksum='invented' WHERE name=:n"),
                             {"n": retirement.MIGRATION})
            if case == "checksum":
                from pathlib import Path
                read = Path.read_text
                with monkeypatch.context() as changed:
                    changed.setattr(Path, "read_text", lambda path, *a, **kw:
                                    read(path, *a, **kw) + "\n-- invented change" if path.name == retirement.MIGRATION
                                    else read(path, *a, **kw))
                    with pytest.raises(ValueError, match="checksum differs"):
                        real_retire(owner)
