"""The cascade: SEC-to-GLEIF matching passes, strict to loose (ticket 21)."""

from __future__ import annotations

from collections import Counter

from edgar_warehouse.mdm.clean.cascade import Entity, Filer, assign, fit_place, place

PASSES = [
    {"pass": "P1", "compare": ["street", "city", "postcode"]},
    {"pass": "P2", "compare": ["street", "postcode"]},
    {"pass": "P4", "compare": ["postcode"]},
    {"pass": "P6", "compare": []},
    {"pass": "P7", "compare": None},
]
HQ = {"street": "1 MAIN ST", "city": "AUSTIN", "postcode": "78701", "country": "US"}


def _place(**changes):
    return place({**HQ, **changes})


def _filer(cik, key="ACME INC", where=None, incorporated="US-DE"):
    return Filer(cik=cik, key=key, place=where or _place(), incorporated=incorporated, business_country="US")


def _entity(lei, keys=("ACME INC",), where=None, eligible=True, jurisdiction="US-DE"):
    return Entity(lei=lei, keys=frozenset(keys), place=where or _place(), jurisdiction=jurisdiction,
                  eligible=eligible, last_update="2026-09-01", legal=keys[0])


def _run(filers, entities, counts=None):
    return assign(filers, entities, PASSES, address_counts=counts or Counter(), over_shared=25)


def test_the_strictest_agreeing_pass_binds_and_records_itself():
    found = _run([_filer("1")], [_entity("L1")])
    assert found == {"1": {"lei": "L1", "last_update": "2026-09-01", "pass": "P1", "flags": [],
                           "key": "ACME INC", "via": "legal name"}}


def test_a_later_pass_takes_what_an_earlier_one_left():
    far = _place(street="9 ELM ST", city="DALLAS")  # only the postcode agrees
    found = _run([_filer("1"), _filer("2", key="BETA LLC")],
                 [_entity("L1"), _entity("L2", keys=("BETA LLC",), where=far)])
    assert found["1"]["pass"] == "P1" and found["2"]["pass"] == "P4"


def test_two_filers_agreeing_with_one_entity_bind_nothing():
    found = _run([_filer("1"), _filer("2")], [_entity("L1")])
    assert found == {}


def test_an_earlier_bind_leaves_the_rest_to_a_later_pass_one_to_one():
    # Two ACME entities: one at the filer's street, one only in its country.
    elsewhere = _place(street="5 OAK AVE", city="RENO", postcode="89501")
    found = _run([_filer("1"), _filer("2", where=elsewhere)], [_entity("L1"), _entity("L2", where=elsewhere)])
    assert found["1"]["lei"] == "L1" and found["2"]["lei"] == "L2"
    assert "name held by another candidate" in found["1"]["flags"]


def test_an_over_shared_address_is_compared_only_by_country():
    counts = Counter({_place().key: 26})
    found = _run([_filer("1")], [_entity("L1")], counts)
    assert found["1"]["pass"] == "P6"


def test_a_withheld_address_is_compared_only_by_country():
    record = {"provenance": {"quality": {"withheld": ["matching.address"]}}}
    agent = fit_place(record, {"address": {**HQ, "street": "1209 ORANGE ST"}})
    assert agent.street == frozenset() and agent.country == "US"
    found = _run([_filer("1", where=agent)], [_entity("L1")])
    assert found["1"]["pass"] == "P6"


def test_the_headquarters_address_comes_before_the_legal_address():
    record = {"provenance": {"quality": {}}}
    chosen = fit_place(record, {"headquarters_address": HQ, "address": {**HQ, "street": "2 OTHER RD"}})
    assert chosen.street == frozenset({"1 MAIN ST"})


def test_a_gleif_other_name_matches():
    found = _run([_filer("1", key="CANON INC")], [_entity("L1", keys=("CANON KABUSHIKI KAISHA", "CANON INC"))])
    assert found["1"]["lei"] == "L1" and found["1"]["via"] == "other name"


def test_an_ineligible_entity_never_binds():
    assert _run([_filer("1")], [_entity("L1", eligible=False)]) == {}


def test_a_conflict_in_place_of_incorporation_binds_and_is_flagged():
    found = _run([_filer("1", incorporated="US-IL")], [_entity("L1", jurisdiction="US-DE")])
    assert found["1"]["flags"] == ["incorporation conflicts"]


def test_name_alone_binds_only_one_to_one():
    abroad = place({"country": "GB"})
    found = _run([_filer("1", where=abroad)], [_entity("L1")])
    assert found["1"]["pass"] == "P7"


def _record(fields, matching, withheld=(), **extra):
    return {"fields": {k: {"op": "value", "value": v} for k, v in fields.items()},
            "provenance": {"matching": matching, "quality": {"withheld": list(withheld)}}, **extra}


def test_a_filer_is_read_from_the_record_the_stage_holds():
    from edgar_warehouse.mdm.clean.cascade import filer_of

    sec = _record({"name": "Acme Inc /DE/", "state_of_incorporation": "DE"},
                  {"address": HQ, "business_country": "US"}, record_key="0000000001")
    f = filer_of(sec)
    assert (f.cik, f.key, f.incorporated, f.business_country) == ("0000000001", "ACME INC", "US-DE", "US")
    assert f.place == _place()


def test_an_entity_is_read_from_the_record_the_stage_holds_headquarters_first():
    from edgar_warehouse.mdm.clean.cascade import entity_of

    gleif = _record({"name": "ACME INC", "jurisdiction": "US-DE", "gleif_last_update": "2026-09-01"},
                    {"headquarters_address": HQ, "address": {**HQ, "street": "1209 ORANGE ST"}},
                    withheld=["matching.address"], identifiers={"lei": "L1"})
    e = entity_of(gleif, frozenset({"ACME INC"}), eligible=True)
    assert (e.lei, e.jurisdiction, e.last_update, e.eligible, e.legal) == ("L1", "US-DE", "2026-09-01", True, "ACME INC")
    assert e.place == _place()


def test_the_passes_come_from_the_company_rules_in_order():
    from edgar_warehouse.mdm.clean.cascade import spec

    def rule(n, compare):
        return {"rule_id": f"p{n}", "when": [
            {"primitive": "cascade_pass@1", "args": {"pass": f"P{n}", "compare": compare, "over_shared": 25}},
            {"primitive": "gleif_entity_eligible@1", "args": {"entity_statuses": ["ACTIVE"],
                                                              "refused_registration_statuses": ["ANNULLED"]}}]}

    policy = {"kinds": {"company": {"rules": [rule(1, ["street"]), {"rule_id": "other", "when": []}, rule(2, None)]}}}
    found = spec(policy)
    assert [p["pass"] for p in found["passes"]] == ["P1", "P2"] and found["over_shared"] == 25
    assert found["entity_statuses"] == ["ACTIVE"]
