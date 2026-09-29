"""The name-binding tests read what the rule declares (ticket 08).

A rule's arguments are in its approved fingerprint, so each test must act on
them or refuse them; none may be decoration.
"""

import copy

import pytest

from edgar_warehouse.mdm.clean import cascade as _cascade
from edgar_warehouse.mdm.clean.company_source import POLICY as _POLICY
from edgar_warehouse.mdm.clean.matching import HELD_LEI_TEST, PAIR_TESTS, _passes, _refused_by_flag
from edgar_warehouse.mdm.clean.name_census import VERSION
from edgar_warehouse.mdm.clean.primitives import REGISTRY
from edgar_warehouse.mdm.clean.store import Conflict
from tests.mdm.test_clean_activation import NAME_POSTCODE, NAME_STATE


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
                "name_census": {
                    "version": VERSION,
                    "key": "APPLE INC",
                    "ciks": ["0000320193"],
                    "cik_count": 1,
                    "leis": [["HWUPKR0MPOU8FGXBT394", "2026-09-01T00:00:00Z"]],
                    "lei_count": 1,
                    "other_name_holders": 0,
                },
            }
        },
    }


def gleif(jurisdiction="US-CA", postal="95014"):
    return {
        "kind": "company",
        "identifiers": {"lei": "HWUPKR0MPOU8FGXBT394"},
        "fields": {
            "name": value("Apple Inc."),
            "jurisdiction": value(jurisdiction),
            "gleif_last_update": value("2026-09-01T00:00:00Z"),
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


def test_both_measured_rules_pass_a_matching_pair():
    assert _passes(NAME_STATE, sec(), gleif())
    assert _passes(NAME_POSTCODE, sec(), gleif())


def test_a_field_path_is_read_from_the_rule():
    # Point the SEC side at a field that holds no state: the rule no longer holds.
    moved = with_args(NAME_STATE, "jurisdiction_agrees@1", sec_field="sic")
    assert not _passes(moved, sec(), gleif())


def test_a_matching_path_is_read_from_the_rule():
    moved = with_args(NAME_POSTCODE, "postal_agrees@1", gleif_code="matching.nothing")
    assert not _passes(moved, sec(), gleif())


@pytest.mark.parametrize(
    ("primitive", "changes", "reason"),
    [
        ("jurisdiction_agrees@1", {"sec_codes": "edgar-iso-v2"}, "unknown code table"),
        (
            "name_census_match@1",
            {"sec_normalizer": "normalize_text@x"},
            "unknown normalizer",
        ),
        ("gleif_entity_eligible@1", {"categories": ["FUND"]}, "only the GENERAL"),
    ],
)
def test_an_argument_the_test_cannot_honour_is_refused(primitive, changes, reason):
    with pytest.raises(Conflict, match=reason):
        _passes(with_args(NAME_STATE, primitive, **changes), sec(), gleif())


# Ticket 21: a cascade pass re-checks the census's answer on the Stage rows.
HQ = {"street": "1 APPLE PARK WAY", "city": "CUPERTINO", "postcode": "95014", "country": "US"}


def _pass(n):
    return next(r for r in _POLICY["kinds"]["company"]["rules"] if r["rule_id"] == f"sec-gleif-cascade-p{n}")


def cascaded(pass_="P1", flags=(), sec_street="1 APPLE PARK WAY", via="legal name"):
    record = sec()
    record["provenance"]["matching"]["address"] = {**HQ, "street": sec_street}
    record["provenance"]["matching"]["name_census"]["cascade"] = {
        "version": _cascade.VERSION, "lei": "HWUPKR0MPOU8FGXBT394", "last_update": "2026-09-01T00:00:00Z",
        "pass": pass_, "flags": list(flags), "key": "APPLE INC", "via": via}
    other = gleif()
    other["provenance"]["matching"]["headquarters_address"] = HQ
    return record, other


def test_a_cascade_pass_binds_the_pair_the_census_named_in_that_pass():
    assert _passes(_pass(1), *cascaded())
    assert not _passes(_pass(2), *cascaded())  # the census named P1


def test_a_cascade_pass_rechecks_the_address_on_the_stage_rows():
    assert not _passes(_pass(1), *cascaded(sec_street="9 ELSEWHERE RD"))
    assert _passes(_pass(7), *cascaded(pass_="P7", sec_street="9 ELSEWHERE RD"))


def test_a_cascade_pass_refuses_a_flag_its_rule_refuses():
    pair = cascaded(flags=[_cascade.CONFLICT])
    assert _passes(_pass(1), *pair)
    assert not _passes(with_args(_pass(1), "cascade_pass@1", refused_flags=[_cascade.CONFLICT]), *pair)


def test_a_cascade_pass_needs_the_gleif_legal_name_unless_the_census_matched_another():
    record, other = cascaded()
    other["fields"]["name"] = value("APPLE KABUSHIKI KAISHA")
    assert not _passes(_pass(1), record, other)
    record, other = cascaded(via="other name")
    other["fields"]["name"] = value("APPLE KABUSHIKI KAISHA")
    assert _passes(_pass(1), record, other)


def test_a_pair_a_refused_flag_holds_back_goes_to_a_steward():
    rule = with_args(_pass(1), "cascade_pass@1", refused_flags=[_cascade.CONFLICT])
    assert _refused_by_flag(rule, *cascaded(flags=[_cascade.CONFLICT]))
    assert not _refused_by_flag(rule, *cascaded(flags=[_cascade.CONFLICT], sec_street="9 ELSEWHERE RD"))
    assert not _refused_by_flag(_pass(1), *cascaded(sec_street="9 ELSEWHERE RD"))
