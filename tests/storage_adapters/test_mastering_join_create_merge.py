"""Step 4 of mastering, on each engine under the real rules, with invented records: one found joins, none found creates
or waits as the entity type's rule says, and two found are merged with the older kept and nothing lost."""

import pytest

from edgar_warehouse.mastering import merge
from tests.storage_adapters.test_mastering import (AS_OF, COMPANY, FIGI, GLEIF, NPORT, POLICY, SECURITY, SEC, figi, live,
                                                   masters, opened, record)

PERSON = merge.Settings(POLICY, "invented-digest", "person", AS_OF)
FUND = merge.Settings(POLICY, "invented-digest", "fund_structure", AS_OF)
CREATES = [
    ("company", COMPANY, SEC, {"cik": "0000000117"}),
    ("person", PERSON, "sec.submissions.person.v1", {"cik": "0000000118"}),
    ("fund_structure", FUND, "sec.nport.fund.v1", {"sec_series_id": "S000000117"}),
    ("security", SECURITY, NPORT, {"cusip": "INV000017"}),
]


@pytest.mark.parametrize("kind,settings,source,identifiers", CREATES, ids=[c[0] for c in CREATES])
def test_none_found_creates_one_golden_record_of_the_entity_type_and_a_later_record_joins_it(
        database_factory, kind, settings, source, identifiers):
    with opened(database_factory) as db:
        first, again = record(source, "one", kind, **identifiers), record(source, "two", kind, **identifiers)
        merge.merge_file(db, settings, [first])
        (golden,) = live(db).values()
        assert golden["kind"] == kind
        assert db.rows("select count(*) from mastering_review where open_review=1")[0][0] == 0
        merge.merge_file(db, settings, [again])  # one found: it joins, and nothing new is created
        assert len(live(db)) == 1
        assert db.bound([again["subject"]])[again["subject"]] == db.bound([first["subject"]])[first["subject"]]


def test_none_found_waits_where_the_rule_says_wait_and_creates_nothing(database_factory):
    with opened(database_factory) as db:
        merge.merge_file(db, COMPANY, [record(GLEIF, "INVENTEDLEI000000117", lei="INVENTEDLEI000000117")])
        assert masters(db) == {}  # GLEIF attaches to Companies others create, never creates one


def test_two_found_are_merged_the_older_kept_and_nothing_is_lost(database_factory):
    with opened(database_factory) as db:
        a, b = figi("00TSTY01"), figi("00TSTY02")
        first, second = record(FIGI, "a", "security", figi=a), record(FIGI, "b", "security", figi=b)
        merge.merge_file(db, SECURITY, [first])
        merge.merge_file(db, SECURITY, [second])
        older = db.bound([first["subject"]])[first["subject"]]
        both = record(FIGI, "c", "security", figi=[a, b])  # one record whose two identifiers find the two golden records
        merge.merge_file(db, SECURITY, [both])
        (kept_id, kept), = live(db).items()
        assert kept_id == older  # the older golden record survives
        assert kept["identifiers"]["figi"] == sorted([a, b])  # it keeps both golden records' identifiers
        bound = db.bound([first["subject"], second["subject"], both["subject"]])
        assert set(bound.values()) == {older}  # and every source record of both
        assert [m for m in masters(db).values() if m.get("status") == "alias"][0]["canonical_id"] == older  # the younger is an alias
