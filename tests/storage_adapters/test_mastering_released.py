"""Nothing waits forever for what has arrived (operator, 2026-11-10): a record that waits for a golden record to hold an
identifier moves to it when a later file gives one, on each engine under the real rules. Invented records."""

from edgar_warehouse.mastering import merge
from tests.storage_adapters.test_mastering import FIGI, NPORT, SECURITY, live, opened, record
from tests.support.masters import figi

CUSIP, ISIN = "037833100", "US0378331005"  # invented pairing; both pass their check digit


def waiting(db):
    return sorted(r[0] for r in db.rows("select subject from mastering_review where reason='binding_required' and open_review=1"))


def not_found(key, **identifiers):
    """An OpenFIGI answer that found nothing: no `matching.found` evidence, so it may only join a Security that holds it."""
    return record(FIGI, key, "security", **identifiers)


def test_a_not_found_answer_joins_the_security_a_later_file_creates(database_factory):
    with opened(database_factory) as db:
        asked = not_found("asked", cusip=CUSIP)
        merge.merge_file(db, SECURITY, [asked])
        assert waiting(db) == [asked["subject"]] and live(db) == {}  # no Security holds the CUSIP: it waits
        counts = merge.merge_file(db, SECURITY, [record(NPORT, CUSIP, "security", cusip=CUSIP, isin=ISIN)])
        (golden_id, _), = live(db).items()
        assert counts["released"] == 1 and waiting(db) == []
        assert db.bound([asked["subject"]])[asked["subject"]] == golden_id


def test_a_waiting_record_is_released_by_a_later_file_of_any_source_and_a_second_pass_changes_nothing(database_factory):
    with opened(database_factory) as db:
        asked, other = not_found("asked", cusip=CUSIP), not_found("other", cusip="594918104")
        merge.merge_file(db, SECURITY, [asked, other])
        assert len(waiting(db)) == 2
        arrival = record(NPORT, CUSIP, "security", cusip=CUSIP)
        merge.merge_file(db, SECURITY, [arrival])
        assert waiting(db) == [other["subject"]]  # only the one whose CUSIP arrived moved
        before = db.rows("select count(*) from mastering_record where entity_id is not null")[0][0]
        merge.merge_file(db, SECURITY, [arrival], again=True)
        assert db.rows("select count(*) from mastering_record where entity_id is not null")[0][0] == before
        assert waiting(db) == [other["subject"]] and len(live(db)) == 1
