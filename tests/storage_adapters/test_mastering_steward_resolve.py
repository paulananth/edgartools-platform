"""A data steward closes a `conflicting_identifiers` review (step 4), on each engine under the real rules. Invented records."""

import json

import pytest

from edgar_warehouse.mastering import merge, steward
from tests.storage_adapters.test_mastering import FIGI, SECURITY, live, opened, record
from tests.support.masters import figi

CLASS, LISTING, OTHER = figi("00RSLV01"), figi("00RSLV02"), figi("00RSLV03")
CUSIP, ISIN = "037833100", "US5949181045"  # invented pairing; both pass their check digit
NEW_CUSIP = "594918104"
BY, WHY, AT = "Steward", "checked against the filings", "2999-01-01T00:00:00+00:00"


def answer(key, **identifiers):
    return record(FIGI, key, "security", **identifiers)


def settings_of(kind):
    assert kind == "security"
    return SECURITY


def reviews(db):
    return [r[0] for r in db.rows("select subject from mastering_review where reason='conflicting_identifiers' and open_review=1")]


def conflict_on_share_class(db):
    """One Security holds a share class and a CUSIP; a record states the share class and another CUSIP: it waits."""
    merge.merge_file(db, SECURITY, [answer("held", cusip=CUSIP, figi=LISTING, share_class_figi=CLASS)])
    (held, _), = live(db).items()
    waiting = answer("split", cusip=NEW_CUSIP, figi=OTHER, share_class_figi=CLASS)
    merge.merge_file(db, SECURITY, [waiting])
    assert reviews(db) == [waiting["subject"]] and list(live(db)) == [held]
    return held, waiting


def test_a_preview_writes_nothing(database_factory):
    with opened(database_factory) as db:
        held, waiting = conflict_on_share_class(db)
        report = steward.resolve(db, settings_of, subject=waiting["subject"], result="merge", actor=BY, reason=WHY, at=AT)
        assert report["written"] is False and report["reached"] == [held]
        assert reviews(db) == [waiting["subject"]] and list(live(db)) == [held]


def test_merge_joins_the_record_to_the_golden_record_it_reached(database_factory):
    with opened(database_factory) as db:
        held, waiting = conflict_on_share_class(db)
        steward.resolve(db, settings_of, subject=waiting["subject"], result="merge", actor=BY, reason=WHY, at=AT,
                        confirm=True)
        assert list(live(db)) == [held] and reviews(db) == []
        assert db.bound([waiting["subject"]])[waiting["subject"]] == held
        assert set(live(db)[held]["identifiers"]["cusip"]) == {CUSIP, NEW_CUSIP}
        (said,) = [json.loads(b) for (b,) in db.rows("select body from mastering_decision where operation='bind' and left_id=%s",
                                                     [waiting["subject"]])]
        assert (said["actor"], said["reason"]) == (BY, WHY)


def test_merge_makes_the_golden_records_a_record_reached_one(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, SECURITY, [answer("by-cusip", cusip=CUSIP, figi=LISTING),
                                        answer("by-isin", isin=ISIN, figi=OTHER)])
        assert len(live(db)) == 2
        both = answer("both", cusip=CUSIP, isin=ISIN, figi=figi("00RSLV04"))
        merge.merge_file(db, SECURITY, [both])
        assert reviews(db) == [both["subject"]]
        steward.resolve(db, settings_of, subject=both["subject"], result="merge", actor=BY, reason=WHY, at=AT, confirm=True)
        (survivor, body), = live(db).items()
        assert reviews(db) == [] and set(body["identifiers"]["cusip"]) == {CUSIP} and set(body["identifiers"]["isin"]) == {ISIN}
        assert db.bound([both["subject"]])[both["subject"]] == survivor
        assert len(db.rows("select 1 from mastering_decision where operation='merge'")) == 1


def test_exclude_gives_the_record_a_golden_record_of_its_own(database_factory):
    with opened(database_factory) as db:
        held, waiting = conflict_on_share_class(db)
        steward.resolve(db, settings_of, subject=waiting["subject"], result="exclude", actor=BY, reason=WHY, at=AT,
                        confirm=True)
        own = db.bound([waiting["subject"]])[waiting["subject"]]
        assert own != held and set(live(db)) == {held, own} and reviews(db) == []
        assert set(live(db)[held]["identifiers"].get("share_class_figi", [])) == {CLASS}
        assert "share_class_figi" not in live(db)[own]["identifiers"]  # the value the other Security holds stays with it
        (excluded,) = [json.loads(b) for (b,) in db.rows("select body from mastering_decision where operation='exclude'")]
        assert {excluded["left"], excluded["right"]} == {held, own}


def test_a_review_that_is_not_open_or_a_missing_reason_is_refused(database_factory):
    with opened(database_factory) as db:
        held, waiting = conflict_on_share_class(db)
        with pytest.raises(ValueError, match="no open conflicting_identifiers review"):
            steward.resolve(db, settings_of, subject="nobody", result="merge", actor=BY, reason=WHY, at=AT)
        with pytest.raises(ValueError, match="says who made it"):
            steward.resolve(db, settings_of, subject=waiting["subject"], result="merge", actor=BY, reason=" ", at=AT)
        with pytest.raises(ValueError, match="one of merge, exclude"):
            steward.resolve(db, settings_of, subject=waiting["subject"], result="drop", actor=BY, reason=WHY, at=AT)
