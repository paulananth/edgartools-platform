"""The records that state links are read through a partial index, never by scanning every record body (PostgreSQL).

On the hosted store 13 GB of bodies of one source held 9 records with links: the plain `like` scan read all of it (72 s).
"""
import json
from contextlib import contextmanager

import pytest

from edgar_warehouse.mastering import links, merge, store as stores
from edgar_warehouse.mdm.evidence import assertion, subject_key
from edgar_warehouse.mastering.store import open_store
from tests.storage_adapters.test_mastering import AS_OF, COMPANY, NPORT, POLICY, SECURITY, SEC, record


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


def test_the_links_build_reads_the_same_links_from_the_cut_records_as_from_whole_ones(database_factory, monkeypatch):
    """The database sends a record's identity and its links only; the links it yields equal those of the whole bodies."""
    custodian = "iapd.adv.custodians.v1"
    link = {"type": "ISSUED_BY", "target_subject": subject_key(custodian, "issuer"), "scope": "invented",
            "valid_from": "2026-03-01T00:00:00+00:00", "valid_to": None, "valid_from_basis": "observed", "properties": {}}
    share = assertion(source_code=NPORT, record_key="share", publication_key="invented", revision=1, effective_at=None,
                      kind="security", fields={"name": "INVENTED SHARE", "note": "x" * 5000},
                      identifiers={"cusip": "037833100"}, relationships=[link])
    with installed(database_factory) as db:
        merge.merge_file(db, SECURITY, [share])
        merge.merge_file(db, COMPANY, [record(custodian, "issuer", lei="529900T8BM49AURSDO55")])
        db.commit()
        (cut,) = [body for _, body in db.linked_records()]
        monkeypatch.setattr(type(db), "linked_select", stores.Store.linked_select)
        (whole,) = [body for _, body in db.linked_records()]
        assert len(cut) < len(whole) / 2 and json.loads(cut)["relationships"] == [link]
        edges, waiting = links.calculate(db, POLICY, AS_OF, [])
        monkeypatch.undo()
        again, again_waiting = links.calculate(db, POLICY, AS_OF, [])
        assert edges == again and waiting == again_waiting and len(edges) == 1
