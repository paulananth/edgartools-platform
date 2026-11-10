"""`clear` restarts one source from empty, on each engine under the real rules and the runtime role. Invented records."""

import pytest

from contextlib import contextmanager

from edgar_warehouse.mastering import clear, merge, store as stores
from edgar_warehouse.mastering.store import open_store
from tests.storage_adapters.test_mastering import FIGI, SECURITY, live, record
from tests.support.masters import figi

LISTING, OTHER, THIRD = figi("00CLR001"), figi("00CLR002"), figi("00CLR003")
CUSIP, OTHER_CUSIP = "037833100", "594918104"


@contextmanager
def opened(database_factory):
    """The runtime role loads; the owner clears (the runtime role may not delete decisions)."""
    with database_factory() as (owner, runtime, role):
        if owner.dialect.name == "mssql":
            pytest.skip("Mastering runs on PostgreSQL and MySQL")
        stores.install(owner, runtime_role=role)
        db, admin = open_store(runtime), open_store(owner)
        try:
            yield db, admin
        finally:
            for each in (db, admin):
                each.rollback()
                each.close()


def count(db, table):
    return db.rows(f"select count(*) from {table}")[0][0]


def two_securities_and_a_merge(db):
    one = record(FIGI, "one", "security", cusip=CUSIP, figi=LISTING)
    two = record(FIGI, "two", "security", cusip=OTHER_CUSIP, figi=OTHER)
    merge.merge_file(db, SECURITY, [one, two])
    joined = record(FIGI, "joined", "security", figi=THIRD, isin="US5949181045")
    merge.merge_file(db, SECURITY, [joined])
    both = record(FIGI, "both", "security", figi=LISTING, isin="US5949181045")  # a listing FIGI and an ISIN: merges
    merge.merge_file(db, SECURITY, [both])


def test_a_preview_counts_and_changes_nothing(database_factory):
    with opened(database_factory) as (db, admin):
        two_securities_and_a_merge(db)
        before = {t: count(db, t) for t in ("mastering_record", "mastering_master", "mastering_identifier", "mastering_decision")}
        report = clear.clear(admin, FIGI)
        assert report["written"] is False and report["source_records"] == before["mastering_record"] > 0
        assert {t: count(db, t) for t in before} == before


def test_confirm_clears_the_source_its_golden_records_aliases_and_dependents(database_factory):
    with opened(database_factory) as (db, admin):
        two_securities_and_a_merge(db)
        report = clear.clear(admin, FIGI, confirm=True)
        assert report["written"] is True and report["golden_records"] > 0
        for table in ("mastering_record", "mastering_master", "mastering_identifier", "mastering_decision",
                      "mastering_review", "mastering_delivery", "mastering_file", "mastering_deferred"):
            assert count(db, table) == 0, table
        again = clear.clear(admin, FIGI, confirm=True)  # nothing left: a second clear removes nothing
        assert again["source_records"] == 0 and again["golden_records"] == 0


def test_another_source_is_left_alone_and_a_shared_golden_record_stops_the_clear(database_factory):
    other = "sec.company.v1"
    with opened(database_factory) as (db, admin):
        from tests.storage_adapters.test_mastering import COMPANY
        merge.merge_file(db, COMPANY, [record(other, "kept", "company", cik="0000999301")])
        keep = count(db, "mastering_record")
        two_securities_and_a_merge(db)
        clear.clear(admin, FIGI, confirm=True)
        assert count(db, "mastering_record") == keep and len(live(db)) == 1  # the company is untouched
        # a golden record of the source that another source's record also sits on: nothing is cleared
        merge.merge_file(db, SECURITY, [record(FIGI, "x", "security", cusip=CUSIP, figi=LISTING)])
        merge.merge_file(db, SECURITY, [record("sec.nport.security.v2", "n", "security", cusip=CUSIP)])
        before = count(db, "mastering_record")
        with pytest.raises(ValueError, match="other sources sit on golden records"):
            clear.clear(admin, FIGI, confirm=True)
        assert count(db, "mastering_record") == before
