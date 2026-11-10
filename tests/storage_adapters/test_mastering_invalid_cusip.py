"""A record whose CUSIP fails its check digit joins the Security its ISIN names, on each engine under the real rules."""

from edgar_warehouse.mastering import merge
from tests.storage_adapters.test_mastering import NPORT, SECURITY, live, opened, record
from tests.unit.test_invalid_cusip import BAD, GOOD, read

ISIN = "US0378331005"


def test_a_bad_cusip_record_joins_the_security_its_isin_names(database_factory):
    with opened(database_factory) as db:
        held = record(NPORT, GOOD, "security", cusip=GOOD, isin=ISIN)
        merge.merge_file(db, SECURITY, [held])
        (golden_id, _), = live(db).items()
        bad = read(cusip=BAD, isin=ISIN)  # through the real Dataset Contract: the CUSIP is set aside, the ISIN kept
        merge.merge_file(db, SECURITY, [bad])
        assert list(live(db)) == [golden_id]  # no second Security
        assert db.bound([bad["subject"]])[bad["subject"]] == golden_id


def test_a_bad_cusip_alone_creates_a_flagged_security_and_never_joins_one_by_that_value(database_factory):
    with opened(database_factory) as db:
        held = record(NPORT, GOOD, "security", cusip=GOOD, isin=ISIN)
        merge.merge_file(db, SECURITY, [held])
        (golden_id, _), = live(db).items()
        alone = read(cusip=BAD)  # no other identifier: keyed by the CUSIP as filed
        merge.merge_file(db, SECURITY, [alone])
        assert len(live(db)) == 2  # a Security of its own: the filed value is not the good CUSIP, so it joins nothing
        own = db.bound([alone["subject"]])[alone["subject"]]
        assert own != golden_id and set(live(db)[own]["identifiers"]["filed_cusip"]) == {BAD}
        again = read(cusip=BAD)  # the same filed value from a later file is the same Security
        again["subject"], again["assertion_id"] = alone["subject"] + "-2", alone["assertion_id"] + "-2"
        merge.merge_file(db, SECURITY, [again])
        assert len(live(db)) == 2 and db.bound([again["subject"]])[again["subject"]] == own
