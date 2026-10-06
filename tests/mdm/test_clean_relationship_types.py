"""Relationship types are data (profiling ticket 04; operator, 2026-10-06: "Types as data").

`rules/merge/relationships.yaml` declares every relationship type MDM masters:
the kinds at each end, the profile roles they need, the capacities of a Person
link, and whether the type is a parent hierarchy, allows one parent, and
derives an ultimate parent. A new type is a rules change, not a code change.

A policy registered before the section existed keeps the table the code held
then (`relationships.TYPES_V0`), so production keeps mastering the same links
until the operator approves the policy that carries the section.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

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


def test_the_rules_file_declares_exactly_the_table_the_code_held():
    assert files.policy()["relationships"]["types"] == BEFORE


def test_a_policy_without_the_section_keeps_that_table():
    assert relationships.TYPES_V0 == BEFORE
    assert relationships.types_of({"kinds": {}}) == BEFORE


@pytest.mark.parametrize("change, words", [
    ({"from": ["planet"]}, "unknown kind"),
    ({"to": []}, "at least one kind"),
    ({"capacities": "director"}, "a list"),
    ({"cycles": "invalid"}, "only on a hierarchy"),
    ({"hierarchy": True}, "cycles"),
    ({"hierarchy": True, "cycles": "invalid", "ultimate_parent": "guess-v9"}, "algorithm"),
    ({"one_parent": True}, "only on a hierarchy"),
    ({"colour": "red"}, "unknown key"),
])
def test_a_type_that_could_not_run_is_refused(change, words):
    body = files.policy()
    body["relationships"]["types"]["NEW_LINK"] = {"from": ["company"], "to": ["company"], **change}
    with pytest.raises(Conflict, match=words):
        check_policy(body)


def test_an_empty_types_section_is_refused_not_read_as_the_old_table():
    body = files.policy()
    body["relationships"]["types"] = {}
    with pytest.raises(Conflict, match="at least one type"):
        check_policy(body)


def test_the_types_round_trip_through_an_export(tmp_path):
    body = files.policy()
    files.write_policy(body, tmp_path)
    assert files.policy(tmp_path)["relationships"] == body["relationships"]
    older = {k: v for k, v in body.items() if k != "relationships"}
    with pytest.raises(files.RulesFileError, match="relationship types absent"):
        files.write_policy(older, tmp_path)


def test_the_rules_file_passes_the_policy_check():
    check_policy(files.policy())


def _state(*pairs):
    bindings = {subject: entity for subject, entity in pairs}
    return SimpleNamespace(bindings=bindings, canonical={e: e for _, e in pairs})


def test_a_new_type_declared_only_in_the_rules_is_mastered():
    entity = {"kind": "company", "status": "accepted", "profiles": []}
    claims = {"s1": {"assertion_id": "a1", "source_meta": {}, "relationships": [
        {"type": "SUPPLIES", "target_subject": "s2", "valid_from": "2024-01-01T00:00:00+00:00", "scope": ""}]}}
    state = _state(("s1", "e1"), ("s2", "e2"))
    entities = {"e1": entity, "e2": entity}
    edges, reviews = relationships.project(claims, state, entities, "2025-01-01T00:00:00+00:00")
    assert edges == [] and [r["reason"] for r in reviews] == ["unsupported_relationship"]
    types = {**BEFORE, "SUPPLIES": {"from": ["company"], "to": ["company"]}}
    edges, reviews = relationships.project(claims, state, entities, "2025-01-01T00:00:00+00:00", types=types)
    assert [(e["type"], e["source_id"], e["target_id"]) for e in edges] == [("SUPPLIES", "e1", "e2")] and not reviews
