"""The name-binding tests read what the rule declares (ticket 08).

A rule's arguments are in its approved fingerprint, so each test must act on
them or refuse them; none may be decoration.
"""

import copy

import pytest

from edgar_warehouse.mdm.clean.matching import HELD_LEI_TEST, PAIR_TESTS, _passes
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
