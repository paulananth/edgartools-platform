"""A silver row finds its master by a join on the binding of its source key, never by a written id."""

from edgar_warehouse.mastering import merge

from tests.storage_adapters.test_mastering import COMPANY, SEC, live, opened, record


def test_bindings_give_each_source_key_its_current_master(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [record(SEC, "KEY-1", cik="0000000017"), record(SEC, "KEY-1b", cik="0000000017"),
                                       record(SEC, "KEY-2", cik="0000000018")])
        db.commit()
        masters = set(live(db))
        found = {(code, key): (kind, entity) for code, key, kind, entity in db.bindings()}
        assert sorted(key for _, key in found) == ["KEY-1", "KEY-1b", "KEY-2"]
        assert {kind for kind, _ in found.values()} == {"company"}
        assert {entity for _, entity in found.values()} == masters and len(masters) == 2
        assert found[(SEC, "KEY-1")] == found[(SEC, "KEY-1b")] != found[(SEC, "KEY-2")]
