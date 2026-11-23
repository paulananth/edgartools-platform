"""A silver row finds its master by a join on a view of the mastering tables, never by a written id."""

from edgar_warehouse.mastering import merge

from tests.storage_adapters.test_mastering import COMPANY, SEC, live, opened, record


def test_the_record_view_gives_each_source_key_its_master(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [record(SEC, "KEY-1", cik="0000000017"), record(SEC, "KEY-2", cik="0000000018")])
        db.commit()
        masters = set(live(db))
        found = dict(db.rows("select source_key, master_id from company_record where source_code=%s", [SEC]))
        assert sorted(found) == ["KEY-1", "KEY-2"]
        assert set(found.values()) == masters and len(masters) == 2


def test_the_identifier_view_leaves_out_a_value_two_masters_hold(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [record(SEC, "KEY-1", cik="0000000017"), record(SEC, "KEY-2", cik="0000000018")])
        db.commit()
        holder = db.rows("select entity_id from mastering_identifier where namespace=%s and value=%s", ["cik", "0000000018"])[0][0]
        other = next(entity for entity in live(db) if entity != holder)
        db.insert("mastering_identifier", ("namespace", "value", "entity_id"), [("cik", "0000000018", other)])
        db.commit()
        held = db.rows("select value, master_id from company_identifier_holder where namespace=%s", ["cik"])
        assert [value for value, _ in held] == ["0000000017"]
