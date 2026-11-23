"""`silver.master_binding` is built by statements inside the data database and only what changed is written (ticket 21).

PostgreSQL only: MySQL keeps the writer path, since its two schemas are two databases. Invented records, the runtime role.
"""
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import text

from edgar_warehouse.mastering import links, merge, store as stores
from edgar_warehouse.mastering.store import open_store
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.control_contract import Blocked
from tests.storage_adapters.test_mastering import COMPANY, SEC, record

SPEC = Path(__file__).resolve().parents[2] / "rules" / "silver" / "silver-master-binding.yaml"
BINDINGS = "select source_code, source_key, kind, master_id from silver.master_binding order by 1, 2"


@contextmanager
def opened(database_factory):
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name != "postgresql":
            pytest.skip("the in-database build is the PostgreSQL path; MySQL keeps the writer")
        stores.install(owner, runtime_role=role)
        silver.migrate(owner, runtime_role=role)
        silver.register(owner, spec_file(SPEC, None), runtime_role=role)
        db = open_store(runtime)
        try:
            yield owner, runtime, role, db
        finally:
            db.rollback()
            db.close()


def held(engine):
    with engine.connect() as conn:
        return [tuple(row) for row in conn.execute(text(BINDINGS))]


def merged(db, *keys_and_ciks):
    merge.merge_file(db, COMPANY, [record(SEC, key, cik=cik) for key, cik in keys_and_ciks])
    db.commit()


def test_the_build_gives_exactly_the_rows_the_client_path_gave_and_the_client_reads_none(database_factory, monkeypatch):
    with opened(database_factory) as (owner, runtime, role, db):
        merged(db, ("K1", "0000000017"), ("K1b", "0000000017"), ("K2", "0000000018"))
        expected = sorted(db.bindings())
        monkeypatch.setattr(stores.Store, "bindings", lambda self: pytest.fail("the client read the bindings"))
        monkeypatch.setattr(links, "land", lambda *a, **k: pytest.fail("the writer received binding rows"))
        counts = links.bind(runtime)
        assert held(owner) == expected and len(expected) == 3
        assert counts == {"inserted": 3, "changed": 0, "deleted": 0, "bindings": 3}


def test_an_unchanged_rerun_writes_no_row(database_factory):
    with opened(database_factory) as (owner, runtime, role, db):
        merged(db, ("K1", "0000000017"), ("K2", "0000000018"))
        links.bind(runtime)
        with owner.connect() as conn:
            before = conn.execute(text("select source_key, loaded_at, xmin::text from silver.master_binding order by 1")).all()
        assert links.bind(runtime) == {"inserted": 0, "changed": 0, "deleted": 0, "bindings": 2}
        with owner.connect() as conn:
            assert conn.execute(text("select source_key, loaded_at, xmin::text from silver.master_binding order by 1")).all() == before


def test_a_new_record_is_bound_to_the_master_it_joined_and_a_record_gone_from_mdm_loses_its_binding(database_factory):
    with opened(database_factory) as (owner, runtime, role, db):
        merged(db, ("K1", "0000000017"), ("K2", "0000000018"), ("K3", "0000000019"))
        links.bind(runtime)
        first = {key: master for _, key, _, master in held(owner)}
        assert len(set(first.values())) == 3
        merged(db, ("K4", "0000000017"))  # a new record that states the first company's CIK joins that master
        with owner.begin() as conn:
            conn.execute(text("delete from mdm.mastering_record where source_key = 'K3'"))
        counts = links.bind(runtime)
        after = {key: master for _, key, _, master in held(owner)}
        assert "K3" not in after and counts["deleted"] == 1 and counts["inserted"] == 1 and counts["changed"] == 0
        assert after["K4"] == after["K1"] == first["K1"] and after["K2"] == first["K2"]


def test_two_records_with_one_source_key_leave_one_row(database_factory):
    with opened(database_factory) as (owner, runtime, role, db):
        merged(db, ("K1", "0000000017"), ("K2", "0000000018"))
        with owner.begin() as conn:
            columns = [r[0] for r in conn.execute(text(
                "select column_name from information_schema.columns where table_schema='mdm' and table_name='mastering_record' "
                "and column_name not in ('assertion_id', 'entity_id')"))]
            listed = ", ".join(f'"{c}"' for c in columns)
            conn.execute(text(f"insert into mdm.mastering_record (assertion_id, entity_id, {listed}) select 'duplicate', "
                              f"(select entity_id from mdm.mastering_record where source_key = 'K2' limit 1), {listed} "
                              "from mdm.mastering_record where source_key = 'K1' limit 1"))
        links.bind(runtime)
        keys = [key for _, key, _, _ in held(owner)]
        assert keys.count("K1") == 1 and sorted(set(keys)) == ["K1", "K2"]


def test_a_login_that_cannot_read_mdm_is_refused_naming_the_grants(database_factory):
    with opened(database_factory) as (owner, runtime, role, db):
        merged(db, ("K1", "0000000017"))
        with owner.begin() as conn:
            conn.execute(text(f'revoke select on mdm.mastering_record from "{role}"'))
        with pytest.raises(Blocked, match="select on mdm.mastering_record"):
            links.bind(runtime)


def test_an_empty_store_refuses_to_empty_the_snapshot(database_factory):
    with opened(database_factory) as (owner, runtime, role, db):
        merged(db, ("K1", "0000000017"))
        links.bind(runtime)
        with owner.begin() as conn:
            conn.execute(text("delete from mdm.mastering_record"))
        with pytest.raises(Blocked, match="snapshot"):
            links.bind(runtime)
        assert len(held(owner)) == 1  # nothing was removed
