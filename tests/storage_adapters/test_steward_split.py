"""A steward's split of a consolidation, on each engine (ticket 142)."""

import pytest

from edgar_warehouse.mastering import merge, reads, steward
from tests.storage_adapters.test_mastering import FIGI, SECURITY, live, opened, record
from tests.support.masters import figi

WORDS = {"actor": "Sam", "reason": "two different issuers", "at": "2026-12-01T00:00:00+00:00"}
SETTINGS = lambda kind: SECURITY  # noqa: E731


def merged_pair(db):
    """Two Securities, each its own master, joined by a record naming both FIGIs."""
    a, b = figi("00TSTX01"), figi("00TSTX02")
    merge.merge_file(db, SECURITY, [record(FIGI, "a", "security", figi=a)])
    merge.merge_file(db, SECURITY, [record(FIGI, "b", "security", figi=b)])
    merge.merge_file(db, SECURITY, [record(FIGI, "c", "security", figi=[a, b])])
    ((merge_id, keep, gone),) = db.merges()
    assert len(live(db)) == 1
    return merge_id, keep, gone, (a, b)


def test_a_preview_writes_nothing_and_a_confirmed_split_returns_both_masters(database_factory):
    with opened(database_factory) as db:
        merge_id, keep, gone, _ = merged_pair(db)
        shown = steward.split(db, SETTINGS, merge_id=merge_id, **WORDS)
        assert shown["written"] is False and (shown["left"], shown["right"]) == (keep, gone)
        assert len(live(db)) == 1  # a preview writes nothing
        done = steward.split(db, SETTINGS, merge_id=merge_id, confirm=True, **WORDS)
        assert done["written"] is True and done["by"] == "Sam" and done["reason"] == "two different issuers"
        assert len(live(db)) == 2  # both masters return
        for master, partner in ((keep, gone), (gone, keep)):
            assert reads.splits_of(db, master) == [{
                "merge": merge_id, "split_from": partner, "by": "Sam", "reason": "two different issuers",
                "at": "2026-12-01T00:00:00+00:00", "excluded": True}], master
        (retained,) = [d for d in db.decisions_about([keep]) if d["operation"] == "reverse"]
        assert (retained["target"], retained["actor"]) == (merge_id, "Sam")  # a retained decision


def test_a_later_record_naming_both_masters_does_not_merge_them_again(database_factory):
    with opened(database_factory) as db:
        merge_id, _, _, (a, b) = merged_pair(db)
        steward.split(db, SETTINGS, merge_id=merge_id, confirm=True, **WORDS)
        merge.merge_file(db, SECURITY, [record(FIGI, "d", "security", figi=[a, b])])
        assert len(live(db)) == 2  # the pair is a Match Exclusion


def test_a_split_merge_or_one_never_held_is_refused(database_factory):
    with opened(database_factory) as db:
        merge_id, _, _, _ = merged_pair(db)
        steward.split(db, SETTINGS, merge_id=merge_id, confirm=True, **WORDS)
        for again in ({}, {"confirm": True}):
            with pytest.raises(ValueError, match="already split"):
                steward.split(db, SETTINGS, merge_id=merge_id, **WORDS, **again)
        with pytest.raises(ValueError, match="holds no merge"):
            steward.split(db, SETTINGS, merge_id="0" * 64, **WORDS)


def test_a_split_needs_who_why_and_a_time_after_the_merge(database_factory):
    with opened(database_factory) as db:
        merge_id, _, _, _ = merged_pair(db)
        with pytest.raises(ValueError, match="who made it"):
            steward.split(db, SETTINGS, merge_id=merge_id, **{**WORDS, "actor": " "})
        with pytest.raises(ValueError, match="who made it"):
            steward.split(db, SETTINGS, merge_id=merge_id, **{**WORDS, "reason": ""})
        with pytest.raises(ValueError, match="later than the merge"):
            steward.split(db, SETTINGS, merge_id=merge_id, **{**WORDS, "at": "2026-11-01T00:00:00+00:00"})
        assert len(live(db)) == 1
