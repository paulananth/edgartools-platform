"""The waterfall pass: SEC filers read from the stored company records, GLEIF entities from the whole
publication, paired one to one pass by pass. The pairs replace the answer a separate file put on each
SEC record (ticket 202, step A). Invented names only."""
from collections import Counter

from edgar_warehouse.mdm import cascade, waterfall

ADDRESS = {"street": "1 Example Way", "city": "Exampleton", "postcode": "12345", "country": "US"}
PASSES = [{"pass": "name and street", "compare": ["street", "city", "postcode"], "rule_id": "r1"},
          {"pass": "name only", "compare": None, "rule_id": "r2"}]


def sec_record(cik, name, address=ADDRESS):
    return cascade.record(cik, {"name": name, "state_of_incorporation": "DE"},
                          {"address": address, "business_country": "US"}, None, {"cik": cik})


def entity(lei, *names, address=ADDRESS, eligible=True):
    keys = frozenset(cascade.legal_form_key(n) for n in names)
    return cascade.Entity(lei, keys, cascade.place(address), "US-DE", eligible, "2026-01-01",
                          legal=cascade.legal_form_key(names[0]))


def test_filers_come_from_the_stored_company_records():
    [filer] = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc")])

    assert filer.cik == "0000000001"
    assert filer.key == cascade.sec_legal_form_key("Alpha Widgets Inc")
    assert filer.place.key == ("1 Example Way", "12345", "US")


def test_a_name_held_by_one_filer_and_one_entity_binds_in_the_first_pass_that_agrees():
    filers = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc")])

    pairs = waterfall.assignments(filers, [entity("LEI-A", "Alpha Widgets Inc")], PASSES, gleif_addresses=Counter(),
                                  over_shared=10)

    assert pairs["0000000001"]["lei"] == "LEI-A" and pairs["0000000001"]["pass"] == "name and street"


def test_a_name_two_filers_share_binds_neither():
    filers = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc"),
                                            sec_record("0000000002", "Alpha Widgets Inc")])

    pairs = waterfall.assignments(filers, [entity("LEI-A", "Alpha Widgets Inc")], PASSES, gleif_addresses=Counter(),
                                  over_shared=10)

    assert pairs == {}


def test_the_gleif_address_counts_join_the_filers_when_an_address_is_over_shared():
    # An address more than `over_shared` entities use is compared by its country only, so the street pass
    # no longer tells two places apart: the shared GLEIF count is part of the answer.
    other = {**ADDRESS, "street": "9 Elsewhere Road"}
    filers = waterfall.filers_from_records([sec_record("0000000001", "Alpha Widgets Inc", other)])
    gleif = Counter({("1 Example Way", "12345", "US"): 50})

    pairs = waterfall.assignments(filers, [entity("LEI-A", "Alpha Widgets Inc")], PASSES, gleif_addresses=gleif,
                                  over_shared=3)

    assert pairs["0000000001"]["pass"] == "name only"


def test_differences_count_each_kind_of_disagreement_with_the_stored_answer():
    new = {"1": {"lei": "A"}, "2": {"lei": "B"}, "3": {"lei": "C"}}
    stored = {"1": {"lei": "A"}, "2": {"lei": "X"}, "4": {"lei": "D"}}

    assert waterfall.differences(new, stored) == {"same": 1, "other_lei": 1, "only_new": 1, "only_stored": 1}


def test_it_gives_the_pairs_the_existing_name_count_document_gives_on_the_same_inputs():
    # While both exist, they must agree: the document's address counts are the filers' places plus the
    # GLEIF addresses, and `assignments` forms the same counts.
    from edgar_warehouse.mdm import name_count

    filers = waterfall.filers_from_records([
        sec_record("0000000001", "Alpha Widgets Inc"),
        sec_record("0000000002", "Beta Gadgets Inc", {**ADDRESS, "street": "2 Other Street"}),
        sec_record("0000000003", "Gamma Tools Inc"),
        sec_record("0000000004", "Gamma Tools Inc")])
    entities = [entity("LEI-A", "Alpha Widgets Inc"), entity("LEI-B", "Beta Gadgets Inc"),
                entity("LEI-G", "Gamma Tools Inc")]
    gleif = Counter({("1 Example Way", "12345", "US"): 4})
    counts = cascade.count_addresses(f.place for f in filers) + gleif

    document = name_count.counted_document(
        sec_population={}, gleif={}, wanted=set(), held={}, legal={}, other={},
        cascade={"spec": {"version": "v", "passes": PASSES, "over_shared": 10}, "filers": filers},
        entities=entities, address_counts=counts)

    new = waterfall.assignments(filers, entities, PASSES, gleif_addresses=gleif, over_shared=10)

    assert new == document["cascade"]["assignments"]
    assert set(new) == {"0000000001", "0000000002"}  # the shared name binds neither of its filers
