"""The records that state links are read through a partial index, never by scanning every record body (PostgreSQL).

On the hosted store 13 GB of bodies of one source held 9 records with links: the plain `like` scan read all of it (72 s).
"""
from contextlib import contextmanager

import pytest

from edgar_warehouse.mastering import merge, store as stores
from edgar_warehouse.mastering.store import open_store
from tests.storage_adapters.test_mastering import COMPANY, SEC, record


@contextmanager
def installed(database_factory):
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name != "postgresql":
            pytest.skip("a partial index is PostgreSQL's")
        stores.install(owner, runtime_role=role)
        db = open_store(runtime)
        try:
            merge.merge_file(db, COMPANY, [record(SEC, f"K{n}", cik=f"{n:010d}") for n in range(1, 6)])
            db.commit()
            yield db
        finally:
            db.rollback()
            db.close()


def test_the_query_for_linked_records_uses_the_partial_index(database_factory):
    with installed(database_factory) as db:
        db.cursor.execute("set local enable_seqscan = off")  # a tiny table scans; the question is whether the index can serve the query
        plan = db.cursor
        plan.execute("explain select body from mastering_record where body like %s", ['%"relationships":[{%'])
        text = "\n".join(r[0] for r in plan.fetchall())
        assert "mastering_record_linked" in text, text
        db.rollback()
