"""A large lookup of the links reads a table in one streamed pass; a small one probes by key. Both give the same answer."""
from contextlib import contextmanager

import pytest

from edgar_warehouse.mastering import merge, store as stores
from edgar_warehouse.mastering.store import open_store
from tests.storage_adapters.test_mastering import COMPANY, SEC, record


@contextmanager
def merged_store(database_factory):
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("Mastering runs on PostgreSQL and MySQL")
        stores.install(owner, runtime_role=role)
        db = open_store(runtime)
        try:
            merge.merge_file(db, COMPANY, [record(SEC, f"K{n}", cik=f"{n:010d}") for n in range(1, 41)])
            db.commit()
            yield db
        finally:
            db.rollback()
            db.close()


def test_a_large_lookup_of_bindings_and_masters_reads_one_pass_and_equals_the_probed_answer(database_factory, monkeypatch):
    with merged_store(database_factory) as db:
        subjects = [r[0] for r in db.rows("select subject from mastering_record")] + ["no such subject"]
        entities = sorted({r[0] for r in db.rows("select entity_id from mastering_master")}) + ["no-such-master"]
        monkeypatch.setattr(stores, "SCAN_FROM", 10**9)
        probed = db.bound(subjects), db.master_states(entities)
        monkeypatch.setattr(stores, "SCAN_FROM", 1)
        scanned = db.bound(subjects), db.master_states(entities)
        assert scanned == probed and len(probed[0]) == 40 and len(probed[1]) == 40
        assert "no such subject" not in scanned[0] and "no-such-master" not in scanned[1]


def test_a_large_lookup_is_not_probed_by_key_on_an_engine_that_can_stream(database_factory, monkeypatch):
    with merged_store(database_factory) as db:
        if not db.scans:
            pytest.skip("this engine probes by key")
        subjects = [r[0] for r in db.rows("select subject from mastering_record")]
        monkeypatch.setattr(stores, "SCAN_FROM", 1)
        seen = []
        real = db.rows
        monkeypatch.setattr(db, "rows", lambda sql, values=(): seen.append(sql) or real(sql, values))
        db.bound(subjects)
        assert not [s for s in seen if " in (" in s], "a large lookup was probed by key"
