"""The name-binding tests read what the rule declares (ticket 08).

A rule's arguments are in its approved fingerprint, so each test must act on
them or refuse them; none may be decoration.
"""

import copy

import pytest

from edgar_warehouse.mdm import cascade as _cascade
from edgar_warehouse.mdm.sec_company import POLICY as _POLICY
from edgar_warehouse.mdm.matching import HELD_LEI_TEST, PAIR_TESTS, _passes, _refused_by_flag
from edgar_warehouse.mdm.primitives import REGISTRY
from edgar_warehouse.mdm.store import Conflict


def value(v):
    return {"op": "value", "value": v}


def sec(state="CA", postal="95014", country="US"):
    return {
        "record_key": "0000320193",
        "fields": {"name": value("APPLE INC"), "state_of_incorporation": value(state)},
        "provenance": {
            "matching": {
                "business_postal_code": postal,
                "business_country": country,
                "name_count": {},
            }
        },
    }


def gleif(jurisdiction="US-CA", postal="95014", effective_at="2026-09-01T00:00:00+00:00"):
    # The Stage keeps GLEIF's LastUpdateDate as the record's effective time, in
    # UTC; the name count keeps GLEIF's own spelling (ticket 129, fix 2).
    return {
        "kind": "company",
        "identifiers": {"lei": "HWUPKR0MPOU8FGXBT394"},
        "effective_at": effective_at,
        "fields": {
            "name": value("Apple Inc."),
            "jurisdiction": value(jurisdiction),
            "gleif_entity_status": value("ACTIVE"),
            "gleif_registration_status": value("ISSUED"),
        },
        "provenance": {
            "matching": {
                "headquarters_postal_code": postal,
                "headquarters_country": "US",
            }
        },
    }


def with_args(rule, primitive, **changes):
    rule = copy.deepcopy(rule)
    for test in rule["when"]:
        if test["primitive"] == primitive:
            test["args"] = {**test["args"], **changes}
    return rule


def test_every_registered_name_binding_test_is_implemented():
    registered = {n for n, p in REGISTRY.items() if p.family == "name_binding"}
    assert registered == set(PAIR_TESTS) | {HELD_LEI_TEST}








def test_a_cascade_pass_checks_the_gleif_version_by_its_effective_time():
    for effective_at, passes in [("2026-08-31T20:00:00-04:00", True), ("2026-09-03T00:00:00+00:00", False)]:
        record, other = cascaded()
        other["effective_at"] = effective_at
        assert _passes(_pass(CITY_OR_POSTCODE), record, other) is passes, effective_at








# Ticket 21: a cascade pass re-checks the name count's answer on the Stage rows.
HQ = {"street": "1 APPLE PARK WAY", "city": "CUPERTINO", "postcode": "95014", "country": "US"}


def _pass(rule_id):
    return next(r for r in _POLICY["kinds"]["company"]["rules"] if r["rule_id"] == rule_id)


CITY_OR_POSTCODE = "sec-gleif-name-city-or-postcode"


ELSEWHERE = {"street": "9 ELSEWHERE RD", "city": "SAN JOSE", "postcode": "95110"}


def cascaded(pass_="name and city or postcode", flags=(), via="legal name", **address):
    record = sec()
    record["provenance"]["matching"]["address"] = {**HQ, **address}
    record["provenance"]["matching"]["name_count"]["cascade"] = {
        "version": _cascade.VERSION, "lei": "HWUPKR0MPOU8FGXBT394", "last_update": "2026-09-01T00:00:00Z",
        "pass": pass_, "flags": list(flags), "key": "APPLE INC", "via": via}
    other = gleif()
    other["provenance"]["matching"]["headquarters_address"] = HQ
    return record, other


def test_a_cascade_pass_binds_the_pair_the_name_count_named_in_that_pass():
    assert _passes(_pass(CITY_OR_POSTCODE), *cascaded())
    assert not _passes(_pass(CITY_OR_POSTCODE), *cascaded(pass_="name alone"))  # the name count named another pass


def test_a_cascade_pass_rechecks_the_address_on_the_stage_rows():
    assert not _passes(_pass(CITY_OR_POSTCODE), *cascaded(**ELSEWHERE))


def test_p5_agrees_on_the_city_or_the_postcode():
    assert _passes(_pass(CITY_OR_POSTCODE), *cascaded(street="9 ELSEWHERE RD", postcode="95110"))  # the city agrees
    assert _passes(_pass(CITY_OR_POSTCODE), *cascaded(street="9 ELSEWHERE RD", city="SAN JOSE"))  # the postcode agrees


def test_a_cascade_pass_refuses_a_flag_its_rule_refuses():
    pair = cascaded(flags=[_cascade.CONFLICT])
    assert _passes(_pass(CITY_OR_POSTCODE), *pair)
    assert not _passes(with_args(_pass(CITY_OR_POSTCODE), "cascade_pass@1", refused_flags=[_cascade.CONFLICT]), *pair)


def test_a_cascade_pass_needs_the_gleif_legal_name_unless_the_name_census_matched_another():
    record, other = cascaded()
    other["fields"]["name"] = value("APPLE KABUSHIKI KAISHA")
    assert not _passes(_pass(CITY_OR_POSTCODE), record, other)
    record, other = cascaded(via="other name")
    other["fields"]["name"] = value("APPLE KABUSHIKI KAISHA")
    assert _passes(_pass(CITY_OR_POSTCODE), record, other)


def test_a_pair_a_refused_flag_holds_back_goes_to_a_steward():
    rule = with_args(_pass(CITY_OR_POSTCODE), "cascade_pass@1", refused_flags=[_cascade.CONFLICT])
    assert _refused_by_flag(rule, *cascaded(flags=[_cascade.CONFLICT]))
    assert not _refused_by_flag(rule, *cascaded(flags=[_cascade.CONFLICT], **ELSEWHERE))
    assert not _refused_by_flag(_pass(CITY_OR_POSTCODE), *cascaded(**ELSEWHERE))
