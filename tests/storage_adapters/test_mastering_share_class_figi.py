"""A share class FIGI finds its Security unless the Security holds another CUSIP or ISIN (step 3), on each engine under the
real rules. Invented records."""

from edgar_warehouse.mastering import merge
from tests.storage_adapters.test_mastering import FIGI, SECURITY, live, opened, record
from tests.support.masters import figi

CLASS = figi("00SCLS01")
LISTING, OTHER_LISTING = figi("00SCLS02"), figi("00SCLS03")
CUSIP, NEW_CUSIP = "037833100", "594918104"  # invented pairing; both pass the check digit


def answer(key, **identifiers):
    return record(FIGI, key, "security", **identifiers)


def seed(db):
    merge.merge_file(db, SECURITY, [answer("held", cusip=CUSIP, figi=LISTING, share_class_figi=CLASS)])
    (golden_id, _), = live(db).items()
    return golden_id


def test_a_record_with_no_cusip_or_isin_joins_the_security_that_holds_its_share_class(database_factory):
    with opened(database_factory) as db:
        golden_id = seed(db)
        ticker_only = answer("ticker", figi=OTHER_LISTING, share_class_figi=CLASS)
        merge.merge_file(db, SECURITY, [ticker_only])
        assert list(live(db)) == [golden_id]
        assert db.bound([ticker_only["subject"]])[ticker_only["subject"]] == golden_id


def test_a_record_with_another_cusip_goes_to_review_and_joins_nothing(database_factory):
    with opened(database_factory) as db:
        golden_id = seed(db)
        split = answer("split", cusip=NEW_CUSIP, figi=OTHER_LISTING, share_class_figi=CLASS)
        counts = merge.merge_file(db, SECURITY, [split])
        assert counts["conflicting_identifiers"] == 1
        assert list(live(db)) == [golden_id]  # no second Security either: it waits for a data steward
        assert split["subject"] not in db.bound([split["subject"]])


def test_a_record_with_the_same_cusip_joins_it(database_factory):
    with opened(database_factory) as db:
        golden_id = seed(db)
        again = answer("again", cusip=CUSIP, figi=OTHER_LISTING, share_class_figi=CLASS)
        merge.merge_file(db, SECURITY, [again])
        assert list(live(db)) == [golden_id]
