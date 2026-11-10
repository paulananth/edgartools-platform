"""Step 5 of mastering, on each engine under the real rules, with invented records: a field's value comes from the
source the policy ranks first, every other source's value is kept beside it, and the ranking never changes which
golden record a source record joins."""

import copy

import pytest

from edgar_warehouse.mastering import merge
from tests.storage_adapters.test_mastering import AS_OF, COMPANY, FIGI, NPORT, POLICY, SECURITY, SEC, live, opened, record

ADV = "iapd.adv.filings.v2"
PERSON = merge.Settings(POLICY, "invented-digest", "person", AS_OF)
SUBMISSIONS, OWNER = "sec.submissions.person.v1", "sec.ownership.reporting_owner.v1"
THIRTEENF = "sec.thirteenf.securities.v2"
# (settings, field, identifiers shared by all, [(source, key, value)] in policy rank order)
KINDS = {
    "company": (COMPANY, "name", {"cik": "0000000317"}, [(SEC, "a", "Sec Name"), (ADV, "b", "Adv Name")]),
    "person": (PERSON, "name", {"cik": "0000000318"}, [(SUBMISSIONS, "a", "Submissions Name"), (OWNER, "b", "Owner Name")]),
    "security": (SECURITY, "name_of_issuer", {"cusip": "INV000017"},
                 [(FIGI, "a", "Openfigi Name"), (THIRTEENF, "b", "Thirteenf Name"), (NPORT, "c", "Nport Name")]),
}


def records(kind, rows, shared):
    return [record(source, key, kind, {field_of[kind]: value}, **shared) for source, key, value in rows]


field_of = {"company": "name", "person": "name", "security": "name_of_issuer"}


@pytest.mark.parametrize("kind", KINDS)
def test_the_first_ranked_source_wins_the_field_and_every_other_value_is_kept(database_factory, kind):
    settings, field, shared, rows = KINDS[kind]
    with opened(database_factory) as db:
        merge.merge_file(db, settings, records(kind, rows, shared))
        (golden,) = live(db).values()
        value = golden["fields"][field]
        assert value["value"] == rows[0][2] and value["winner"]["source_code"] == rows[0][0]
        kept = {(c["source_code"], c["value"]) for c in value["conflicts"]}
        assert kept == {(source, text) for source, _, text in rows[1:]}  # each losing value, with its source


@pytest.mark.parametrize("kind", ["company", "person", "security"])
def test_the_ranking_never_changes_which_golden_record_a_record_joins(database_factory, kind):
    settings, field, shared, rows = KINDS[kind]
    reversed_policy = copy.deepcopy(POLICY)
    reversed_policy["kinds"][kind]["defaults"]["sources"].reverse()
    outcomes = []
    for policy in (POLICY, reversed_policy):
        with opened(database_factory) as db:
            batch = records(kind, rows, shared)
            merge.merge_file(db, merge.Settings(policy, "invented-digest", kind, AS_OF), batch)
            (golden,) = live(db).values()
            outcomes.append((sorted(golden["subjects"]), golden["fields"][field]["value"]))
    (same_a, winner_a), (same_b, winner_b) = outcomes
    assert same_a == same_b  # the same records in the same golden record
    assert winner_a == rows[0][2] and winner_b == rows[-1][2]  # only the winner moved
