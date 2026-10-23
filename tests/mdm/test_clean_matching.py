"""The name-binding tests read what the rule declares (ticket 08).

A rule's arguments are in its approved fingerprint, so each test must act on
them or refuse them; none may be decoration.
"""

import copy

import pytest

from edgar_warehouse.mdm.clean import cascade as _cascade
from edgar_warehouse.mdm.clean.sec_company import POLICY as _POLICY
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


def gleif(jurisdiction="US-CA", postal="95014", effective_at="2026-09-01T00:00:00+00:00"):
    # The Stage keeps GLEIF's LastUpdateDate as the record's effective time, in
    # UTC; the census keeps GLEIF's own spelling (ticket 129, fix 2).
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


def test_both_measured_rules_pass_a_matching_pair():
    assert _passes(NAME_STATE, sec(), gleif())
    assert _passes(NAME_POSTCODE, sec(), gleif())


def test_the_census_names_the_gleif_version_the_stage_holds_by_its_effective_time():
    # GLEIF's spelling and the Stage's UTC form are one instant.
    assert _passes(NAME_STATE, sec(), gleif(effective_at="2026-09-01T02:00:00+02:00"))
    # A later GLEIF version than the one the census saw is not the census's answer.
    assert not _passes(NAME_STATE, sec(), gleif(effective_at="2026-09-02T00:00:00+00:00"))
    # A record with no stated time matches only a census that saw none.
    assert not _passes(NAME_STATE, sec(), gleif(effective_at=None))
    record = sec()
    record["provenance"]["matching"]["name_census"]["leis"] = [["HWUPKR0MPOU8FGXBT394", ""]]
    assert _passes(NAME_STATE, record, gleif(effective_at=None))
    assert not _passes(NAME_STATE, record, gleif())


@pytest.mark.parametrize(
    "case,expected",
    [
        ("ambiguous_candidates", (False, False)),
        ("ambiguous_holders", (False, False)),
        ("stale_census", (False, False)),
        ("different_legal_form", (False, False)),
        ("inactive_candidate", (False, False)),
        ("different_places", (False, False)),
        ("conflicting_jurisdictions", (False, False)),
        ("foreign_business_country", (False, True)),
    ],
)
def test_pair_policy_without_storage(case, expected):
    """Calculation matrix retired from PostgreSQL integration; fixtures are invented."""
    record, other = sec(), gleif()
    record["record_key"] = "9999999999"
    record["fields"]["name"] = value("INVENTED GROUP INC")
    other["fields"]["name"] = value("Invented Group Inc.")
    other["identifiers"] = {"lei": "9999000000EXAMPLE113"}
    entry = record["provenance"]["matching"]["name_census"]
    entry.update(key="INVENTED GROUP INC", ciks=[record["record_key"]],
                 leis=[[other["identifiers"]["lei"], "2026-09-01T00:00:00Z"]])
    assert all(_passes(rule, record, other) for rule in (NAME_STATE, NAME_POSTCODE))
    if case == "ambiguous_candidates":
        entry["leis"].append(["9999000000EXAMPLE114", "2026-09-01T00:00:00Z"])
        entry["lei_count"] = 2
    elif case == "ambiguous_holders":
        entry["ciks"].append("9999999998")
        entry["cik_count"] = 2
    elif case == "stale_census":
        other["effective_at"] = "2026-09-20T00:00:00Z"
    elif case == "different_legal_form":
        other["fields"]["name"] = value("Invented Group LLC")
    elif case == "inactive_candidate":
        other["fields"]["gleif_entity_status"] = value("INACTIVE")
    elif case == "different_places":
        other["fields"]["jurisdiction"] = value("US-NV")
        other["provenance"]["matching"]["headquarters_postal_code"] = "89501"
    elif case == "conflicting_jurisdictions":
        other["fields"]["jurisdiction"] = value("US-NV")
    elif case == "foreign_business_country":
        record["provenance"]["matching"]["business_country"] = "GB"
        other["fields"]["jurisdiction"] = value("GB")
        other["provenance"]["matching"]["headquarters_country"] = "GB"
    assert tuple(_passes(rule, record, other) for rule in (NAME_STATE, NAME_POSTCODE)) == expected


def test_a_cascade_pass_checks_the_gleif_version_by_its_effective_time():
    for effective_at, passes in [("2026-08-31T20:00:00-04:00", True), ("2026-09-03T00:00:00+00:00", False)]:
        record, other = cascaded()
        other["effective_at"] = effective_at
        assert _passes(_pass(1), record, other) is passes, effective_at


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
    assert not _passes(_pass(4), *cascaded())  # the census named P1


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
