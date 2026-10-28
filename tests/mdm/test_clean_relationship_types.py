"""Relationship types are reference data (ticket 132; operator, 2026-10-27: "Use RDM
for keeping types and other information", "Types in YAML + Rust only").

RDM code set `mdm-relationship-types` holds every relationship type MDM
masters: each type a code whose properties are its rules (the kinds at each
end, the profile roles they need, whether it is a parent hierarchy, allows one
parent and derives an ultimate parent, written as its `ultimate_type`); each
capacity a child code `TYPE:capacity`. The policy pins it; the Rust engine reads
and checks it. A new type is a new code set version, not a code change; a
policy that pins none masters no link, each reported one going to review.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.support.relationship_types import read_types

from edgar_warehouse.mdm.clean import relationships
from edgar_warehouse.mdm.clean.activation import check_policy
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.rules import files

LEGAL = ["company", "fund_structure", "government", "international_organization"]
# The table as the code held it before this ticket (CONTRACTS, CAPACITIES,
# HIERARCHIES and the type lists inside `project`), frozen here as the golden copy.
BEFORE = {
    "AUDITED_BY": {"from": ["company"], "to": ["company"], "to_profile": "audit_firm"},
    "ISSUED_BY": {"from": ["security"], "to": LEGAL},
    "EMPLOYED_BY": {"from": ["person"], "to": ["company"], "capacities": ["director", "employee", "officer"]},
    "CONTROLS": {"from": ["person"], "to": ["company"], "capacities": ["control_person", "owner", "ten_percent_owner"]},
    "HOLDS": {"from": ["company", "fund_structure", "person"], "to": ["security"]},
    "MANAGES_FUND": {"from": ["company", "person"], "to": ["company", "fund_structure"],
                     "from_profile": "adviser", "to_profile": "fund"},
    "OWNERSHIP_PARENT": {"from": LEGAL, "to": LEGAL, "hierarchy": True, "cycles": "review"},
    "ACCOUNTING_PARENT": {"from": LEGAL, "to": LEGAL, "hierarchy": True, "cycles": "invalid", "one_parent": True,
                          "ultimate_parent": "accounting-chain-v1"},
    "IS_DIRECTLY_CONSOLIDATED_BY": {"from": ["company"], "to": ["company"], "hierarchy": True, "cycles": "invalid",
                                    "one_parent": True, "ultimate_parent": "accounting-chain-v1"},
    "IS_ULTIMATELY_CONSOLIDATED_BY": {"from": ["company"], "to": ["company"], "hierarchy": True,
                                      "cycles": "invalid", "one_parent": True},
    "REPORTED_ULTIMATE_PARENT": {"from": LEGAL, "to": LEGAL},
    "IS_INTERNATIONAL_BRANCH_OF": {"from": ["branch"], "to": LEGAL, "hierarchy": True, "cycles": "invalid"},
    "VENUE_OPERATOR": {"from": ["venue"], "to": LEGAL},
    "VENUE_SEGMENT_OF": {"from": ["venue"], "to": ["venue"], "hierarchy": True, "cycles": "invalid"},
    "IS_SUBFUND_OF": {"from": ["company", "fund_structure"], "to": ["company", "fund_structure"],
                      "from_profile": "fund", "to_profile": "fund", "hierarchy": True, "cycles": "invalid"},
    "IS_FEEDER_TO": {"from": ["company", "fund_structure"], "to": ["company", "fund_structure"],
                     "from_profile": "fund", "to_profile": "fund", "hierarchy": True, "cycles": "invalid"},
    "IS_FUND-MANAGED_BY": {"from": ["company", "fund_structure"], "to": ["company", "person"],
                           "from_profile": "fund"},
}


# The types under their sources' own names (profiling ticket 04b; each name
# approved by the operator one by one, 2026-10-07).
REAL_NAMES = {
    "IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY", "SUCCESSOR_ENTITY", "IS_SUBSIDIARY_OF",
    "BENEFICIAL_OWNER_OF", "EMPLOYED_BY", "ISSUED_BY", "INVESTMENT_ADVISER_TO", "IS_FUND-MANAGED_BY",
    "IS_SUBFUND_OF", "IS_FEEDER_TO", "IS_INTERNATIONAL_BRANCH_OF", "AUDITED_BY", "HAS_MARKET_OPERATOR",
    "IS_SEGMENT_OF_EXCHANGE", "CUSTODIAN",
}


def test_the_code_set_names_every_type_as_its_source_does():
    types = relationships.types_of(files.policy())
    assert set(types) == REAL_NAMES
    # Every type the old table had either keeps its name and rules, or is gone.
    for name, spec in BEFORE.items():
        if name in types and name not in ("IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY"):
            # ISSUED_BY keeps its start since ticket 113 (2026-10-19); its rules are otherwise the same.
            found = {k: v for k, v in types[name].items() if not (name == "ISSUED_BY" and k == "keeps_start")}
            assert found == spec, name
    # The direct parent derives its ultimate parent as the stated type's name.
    assert types["IS_DIRECTLY_CONSOLIDATED_BY"]["ultimate_type"] == "IS_ULTIMATELY_CONSOLIDATED_BY"
    # A capacity is a child code of its type.
    codes = {row["code"]: row for row in files.pinned_reference("mdm-relationship-types")}
    assert codes["EMPLOYED_BY:director"]["parent_code"] == "EMPLOYED_BY"
    assert "capacities" not in codes["EMPLOYED_BY"]["properties"]


def test_a_policy_that_pins_no_types_masters_no_link():
    assert relationships.types_of({"kinds": {}}) == {}
    entity = {"kind": "company", "status": "accepted", "profiles": []}
    claims = {"s1": {"assertion_id": "a1", "source_meta": {}, "relationships": [
        {"type": "SUPPLIES", "target_subject": "s2", "valid_from": "2024-01-01T00:00:00+00:00", "scope": ""}]}}
    edges, reviews = relationships.project(claims, _state(("s1", "e1"), ("s2", "e2")), {"e1": entity, "e2": entity},
                                           "2025-01-01T00:00:00+00:00", types={})
    assert edges == [] and [r["reason"] for r in reviews] == ["unsupported_relationship"]


def test_a_policy_that_pins_types_badly_is_refused():
    with pytest.raises(Conflict, match="pins no relationship types"):
        relationships.types_of({"relationships": {"types": {}}})
    body = files.policy()
    body["reference_pins"].pop("mdm-relationship-types")
    with pytest.raises(Conflict, match="no reference data named mdm-relationship-types"):
        relationships.types_of(body)
    body = files.policy()
    body["reference_pins"]["mdm-relationship-types"] = {**body["reference_pins"]["mdm-relationship-types"],
                                                        "sha256": "0" * 64}
    with pytest.raises(Conflict, match="differs from its pinned sha256"):
        check_policy(body)


@pytest.mark.parametrize("change, words", [
    ({"from": ["planet"]}, "unknown kind"),
    ({"to": []}, "at least one kind"),
    ({"cycles": "invalid"}, "only on a hierarchy"),
    ({"hierarchy": True}, "cycles"),
    ({"hierarchy": True, "cycles": "invalid", "ultimate_parent": "guess-v9"}, "algorithm"),
    ({"one_parent": True}, "only on a hierarchy"),
    ({"colour": "red"}, "rules it cannot run"),
    ({"hierarchy": True, "cycles": "invalid", "ultimate_parent": "accounting-chain-v1", "ultimate_type": "NOT_A_TYPE"},
     "ultimate_type"),
    ({"hierarchy": True, "cycles": "invalid", "ultimate_type": "IS_ULTIMATELY_CONSOLIDATED_BY"}, "ultimate_type"),
    # An ultimate parent is written only as the type its hierarchy names (ticket 132: no default type).
    ({"hierarchy": True, "cycles": "invalid", "ultimate_parent": "accounting-chain-v2"}, "names its ultimate_type"),
])
def test_a_type_that_could_not_run_is_refused(change, words):
    types = {**relationships.types_of(files.policy()), "NEW_LINK": {"from": ["company"], "to": ["company"], **change}}
    with pytest.raises(ValueError, match=words):
        read_types(types)


def test_no_types_is_refused():
    with pytest.raises(ValueError, match="at least one type"):
        read_types({})


def test_the_pin_round_trips_through_an_export(tmp_path):
    body = files.policy()
    files.write_policy(body, tmp_path)
    exported = files.policy(tmp_path)
    assert exported["relationships"] == body["relationships"] == {"pin": "mdm-relationship-types"}
    assert exported["reference_pins"]["mdm-relationship-types"] == body["reference_pins"]["mdm-relationship-types"]


def test_the_policy_passes_the_policy_check():
    check_policy(files.policy())


def _state(*pairs):
    bindings = {subject: entity for subject, entity in pairs}
    return SimpleNamespace(bindings=bindings, canonical={e: e for _, e in pairs})


def test_a_new_type_declared_only_as_a_code_is_mastered():
    from edgar_warehouse.mdm.clean.evidence import KINDS
    from edgar_warehouse.rules.source_engine import prepare_relationship_types

    entity = {"kind": "company", "status": "accepted", "profiles": []}
    claims = {"s1": {"assertion_id": "a1", "source_meta": {}, "relationships": [
        {"type": "SUPPLIES", "target_subject": "s2", "valid_from": "2024-01-01T00:00:00+00:00", "scope": ""}]}}
    state = _state(("s1", "e1"), ("s2", "e2"))
    entities = {"e1": entity, "e2": entity}
    codes = files.pinned_reference("mdm-relationship-types")
    edges, reviews = relationships.project(claims, state, entities, "2025-01-01T00:00:00+00:00",
                                           prepare_relationship_types(codes, sorted(KINDS)))
    assert edges == [] and [r["reason"] for r in reviews] == ["unsupported_relationship"]
    supplies = {"code": "SUPPLIES", "label": "Supplies", "parent_code": None, "status": "valid",
                "properties": {"from": ["company"], "to": ["company"]}}
    types = prepare_relationship_types([*codes, supplies], sorted(KINDS))
    edges, reviews = relationships.project(claims, state, entities, "2025-01-01T00:00:00+00:00", types=types)
    assert [(e["type"], e["source_id"], e["target_id"]) for e in edges] == [("SUPPLIES", "e1", "e2")] and not reviews


def test_every_capacity_a_contract_states_is_one_its_type_has():
    """A link's capacity is fixed text in its contract, so the allowed set is
    held here, not per record (rebuild ticket 10; operator, 2026-10-02)."""
    types = relationships.types_of(files.policy())
    stated = [
        (link["type"], link["capacity"])
        for folder in sorted((files.ROOT / "sources").iterdir()) if (folder / "source.yaml").exists()
        for entry in (files.source(folder.name).get("mdm") or {}).values()
        for link in entry["contract"]["adapter"].get("relationships") or []
        if "capacity" in link
    ]
    assert stated, "the ownership feed states capacities"
    for type_name, capacity in stated:
        assert capacity in types[type_name].get("capacities", []), (type_name, capacity)
