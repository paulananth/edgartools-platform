"""Parent links follow corporate actions (profiling ticket 04b, part B;
operator, 2026-10-07: "It should also consider corporate actions").

- A parent period's dates carry their basis: `stated` when the source gives
  the date, else `observed` from when the link was first seen.
- The calculated ultimate parent keeps its history (`accounting-chain-v2`): a
  new period each time a link in its chain changes, so any date has an answer.
- `SUCCESSOR_ENTITY` ends the ceased entity's parent links on its date, and its
  children's links unless a source states them again after that date.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from edgar_warehouse.mdm.clean import relationships
from edgar_warehouse.mdm.clean.store import Conflict

LEGAL = ["company"]
PARENT = "IS_DIRECTLY_CONSOLIDATED_BY"
ULTIMATE = "IS_ULTIMATELY_CONSOLIDATED_BY"
TYPES = {
    PARENT: {"from": LEGAL, "to": LEGAL, "hierarchy": True, "cycles": "invalid", "one_parent": True,
             "ultimate_parent": "accounting-chain-v2", "ultimate_type": ULTIMATE},
    ULTIMATE: {"from": LEGAL, "to": LEGAL, "hierarchy": True, "cycles": "invalid", "one_parent": True},
    "SUCCESSOR_ENTITY": {"from": LEGAL, "to": LEGAL, "ends_parent_links": True},
}
AS_OF = "2026-01-01T00:00:00+00:00"
Y2020, Y2022, Y2024 = ("2020-01-01T00:00:00+00:00", "2022-01-01T00:00:00+00:00",
                       "2024-01-01T00:00:00+00:00")
SEEN = "2025-06-01T00:00:00+00:00"


def _project(links, types=TYPES, seen=SEEN, as_of=AS_OF):
    """Each link is (child, parent, type, period); one reading per link."""
    names = sorted({n for child, parent, _, _ in links for n in (child, parent)})
    claims = {
        f"r{i}": {"assertion_id": f"a{i}", "source_meta": {"effective_at": seen},
                  "relationships": [{"type": kind, "source_subject": child, "target_subject": parent,
                                     "scope": "", **period}]}
        for i, (child, parent, kind, period) in enumerate(links)
    }
    state = SimpleNamespace(bindings={n: n for n in names}, canonical={n: n for n in names})
    entities = {n: {"kind": "company", "status": "accepted", "profiles": []} for n in names}
    return relationships.project(claims, state, entities, as_of, types=types)


def _of(edges, kind, derived=False):
    return {(e["source_id"], e["target_id"]): e for e in edges if e["type"] == kind and e["derived"] is derived}


def test_a_stated_date_is_stated_and_a_missing_start_is_first_seen():
    edges, reviews = _project([
        ("A", "B", PARENT, {"valid_from": Y2020, "valid_to": Y2024}),
        ("C", "B", PARENT, {}),
    ])
    stated, seen = _of(edges, PARENT)[("A", "B")], _of(edges, PARENT)[("C", "B")]
    assert stated["periods"] == [{"valid_from": Y2020, "valid_from_basis": "stated",
                                  "valid_to": Y2024, "valid_to_basis": "stated"}]
    assert seen["periods"] == [{"valid_from": SEEN, "valid_from_basis": "observed"}]
    assert not reviews


def test_the_calculated_ultimate_parent_keeps_its_history():
    # A's parent is B until 2022, then C; B and C have no parent.
    edges, reviews = _project([
        ("A", "B", PARENT, {"valid_from": Y2020, "valid_to": Y2022}),
        ("A", "C", PARENT, {"valid_from": Y2022}),
    ])
    calculated = _of(edges, ULTIMATE, derived=True)
    assert set(calculated) == {("A", "B"), ("A", "C")} and not reviews
    to_b, to_c = calculated[("A", "B")], calculated[("A", "C")]
    assert [(p["valid_from"], p["valid_to"]) for p in to_b["periods"]] == [(Y2020, Y2022)]
    assert [(p["valid_from"], p["valid_to"]) for p in to_c["periods"]] == [(Y2022, None)]
    assert to_c["periods"][0]["path"] == [_of(edges, PARENT)[("A", "C")]["relationship_id"]]
    assert to_c["algorithm"] == "accounting-chain-v2" and "as_of" not in to_c


def test_a_change_higher_in_the_chain_opens_a_new_period():
    # A -> B always; B -> C from 2022. A's ultimate parent is B, then C.
    edges, _ = _project([
        ("A", "B", PARENT, {"valid_from": Y2020}),
        ("B", "C", PARENT, {"valid_from": Y2022}),
    ])
    calculated = _of(edges, ULTIMATE, derived=True)
    assert [(p["valid_from"], p["valid_to"]) for p in calculated[("A", "B")]["periods"]] == [(Y2020, Y2022)]
    assert [(p["valid_from"], p["valid_to"]) for p in calculated[("A", "C")]["periods"]] == [(Y2022, None)]
    assert len(calculated[("A", "C")]["periods"][0]["path"]) == 2


def test_the_calculated_id_does_not_change_with_the_run_date():
    links = [("A", "B", PARENT, {"valid_from": Y2020})]
    edges, _ = _project(links)
    later, _ = _project(links, as_of="2026-02-01T00:00:00+00:00")
    assert (_of(edges, ULTIMATE, True)[("A", "B")]["relationship_id"]
            == _of(later, ULTIMATE, True)[("A", "B")]["relationship_id"])


def test_a_stated_date_to_come_is_calculated_too():
    # A's parent is B until a stated end in 2027, then C: an --as-of after it answers C.
    later = "2027-01-01T00:00:00+00:00"
    edges, _ = _project([
        ("A", "B", PARENT, {"valid_from": Y2020, "valid_to": later}),
        ("A", "C", PARENT, {"valid_from": later}),
    ])
    calculated = _of(edges, ULTIMATE, derived=True)
    assert [(p["valid_from"], p["valid_to"]) for p in calculated[("A", "C")]["periods"]] == [(later, None)]


def test_a_link_seen_in_many_publications_starts_when_first_seen():
    names = ["A", "B"]
    claims = {f"r{i}": {"assertion_id": f"a{i}", "source_meta": {"effective_at": seen}, "relationships": [
        {"type": PARENT, "source_subject": "A", "target_subject": "B", "scope": ""}]}
        for i, seen in enumerate([Y2024, Y2020, Y2022])}
    state = SimpleNamespace(bindings={n: n for n in names}, canonical={n: n for n in names})
    entities = {n: {"kind": "company", "status": "accepted", "profiles": []} for n in names}
    edges, _ = relationships.project(claims, state, entities, AS_OF, types=TYPES)
    assert _of(edges, PARENT)[("A", "B")]["periods"] == [{"valid_from": Y2020, "valid_from_basis": "observed"}]


def test_a_disputed_link_higher_up_cuts_the_period():
    # A -> B always; B has two parents from 2022 (disputed): A's ultimate parent
    # is B until 2022, then unknown.
    edges, reviews = _project([
        ("A", "B", PARENT, {"valid_from": Y2020}),
        ("B", "C", PARENT, {"valid_from": Y2022}),
        ("B", "D", PARENT, {"valid_from": Y2022}),
    ])
    calculated = _of(edges, ULTIMATE, derived=True)
    assert [(p["valid_from"], p["valid_to"]) for p in calculated[("A", "B")]["periods"]] == [(Y2020, Y2022)]
    assert ("A", "C") not in calculated and ("A", "D") not in calculated
    assert "conflicting_accounting_parents" in [r["reason"] for r in reviews]


def test_a_date_basis_the_rules_do_not_know_goes_to_a_steward():
    edges, reviews = _project([("A", "B", PARENT, {"valid_from": Y2020, "valid_from_basis": "guessed"})])
    assert edges == [] and [r["reason"] for r in reviews] == ["unknown_date_basis"]


def test_the_v1_algorithm_is_unchanged():
    v1 = {**TYPES, PARENT: {**TYPES[PARENT], "ultimate_parent": "accounting-chain-v1"}}
    edges, _ = _project([("A", "B", PARENT, {"valid_from": Y2020})], types=v1)
    (calculated,) = _of(edges, ULTIMATE, derived=True).values()
    assert calculated["as_of"] == AS_OF and "periods" not in calculated


def test_a_successor_ends_the_ceased_entitys_parent_links_and_its_childrens():
    # B ceased in 2022, succeeded by S. A is B's child, B's parent was P.
    edges, reviews = _project([
        ("B", "P", PARENT, {"valid_from": Y2020}),
        ("A", "B", PARENT, {"valid_from": Y2020}),
        ("B", "S", "SUCCESSOR_ENTITY", {"valid_from": Y2022}),
    ], seen=Y2020)
    parents = _of(edges, PARENT)
    successor = _of(edges, "SUCCESSOR_ENTITY")[("B", "S")]
    for link in (parents[("B", "P")], parents[("A", "B")]):
        assert link["periods"] == [{"valid_from": Y2020, "valid_from_basis": "stated", "valid_to": Y2022,
                                    "valid_to_basis": "stated", "ended_by": successor["relationship_id"]}]
    # A's ultimate parent was P (through B) until 2022, and none after.
    calculated = _of(edges, ULTIMATE, derived=True)
    assert [(p["valid_from"], p["valid_to"]) for p in calculated[("A", "P")]["periods"]] == [(Y2020, Y2022)]
    assert not reviews


def test_a_child_link_stated_again_after_the_succession_stays_open():
    edges, _ = _project([
        ("A", "B", PARENT, {"valid_from": Y2020}),
        ("B", "S", "SUCCESSOR_ENTITY", {"valid_from": Y2022}),
    ], seen=Y2024)
    assert _of(edges, PARENT)[("A", "B")]["periods"] == [{"valid_from": Y2020, "valid_from_basis": "stated"}]


def test_a_parent_period_after_the_succession_goes_to_a_steward():
    edges, reviews = _project([
        ("B", "P", PARENT, {"valid_from": Y2024}),
        ("B", "S", "SUCCESSOR_ENTITY", {"valid_from": Y2022}),
    ], seen=Y2024)
    assert ("B", "P") not in _of(edges, PARENT)
    assert [r["reason"] for r in reviews] == ["parent_link_after_succession"]


@pytest.mark.parametrize("spec", [
    {"from": LEGAL, "to": LEGAL, "ends_parent_links": False},
    {"from": LEGAL, "to": LEGAL, "hierarchy": True, "cycles": "review", "ends_parent_links": True},
])
def test_ends_parent_links_is_true_on_a_link_that_is_no_parent(spec):
    with pytest.raises(Conflict, match="ends_parent_links"):
        relationships.check_types({"version": "t", "types": {"SUCCESSOR_ENTITY": spec}})
