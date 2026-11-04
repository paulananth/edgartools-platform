"""A link type may state that an entity has one target at a time (ticket 24).

A Security has one issuer. Two source records of one Security that name two issuers over
overlapping periods set both ISSUED_BY links aside and ask for review; an issuer that changed
(the first link ended before the second began) is two periods of history, not a conflict.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from edgar_warehouse.mdm import relationships

ISSUED_BY = "ISSUED_BY"
TYPES = {ISSUED_BY: {"from": ["security"], "to": ["company"], "keeps_start": True, "one_target": True}}
AS_OF = "2026-01-01T00:00:00+00:00"
Y2020, Y2022, Y2024 = ("2020-01-01T00:00:00+00:00", "2022-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00")


def project(links, types=TYPES):
    """Each link is (security, issuer, period); one source record per link."""
    claims = {
        f"r{i}": {"assertion_id": f"a{i}", "source_meta": {"effective_at": Y2024},
                  "relationships": [{"type": ISSUED_BY, "source_subject": security, "target_subject": issuer,
                                     "scope": "", **period}]}
        for i, (security, issuer, period) in enumerate(links)
    }
    names = sorted({n for security, issuer, _ in links for n in (security, issuer)})
    state = SimpleNamespace(bindings={n: n for n in names}, canonical={n: n for n in names})
    entities = {n: {"kind": "security" if n.startswith("S") else "company", "status": "accepted", "profiles": []}
                for n in names}
    return relationships.project(claims, state, entities, AS_OF, types=types)


def test_two_issuers_over_the_same_time_set_both_links_aside_and_ask_for_review():
    edges, reviews = project([("S1", "C1", {"valid_from": Y2020}), ("S1", "C2", {"valid_from": Y2022})])
    assert [e for e in edges if e["type"] == ISSUED_BY] == []  # neither link stands
    assert [r["reason"] for r in reviews] == ["conflicting_targets"]


def test_an_issuer_that_changed_is_history_not_a_conflict():
    edges, reviews = project([("S1", "C1", {"valid_from": Y2020, "valid_to": Y2022}),
                              ("S1", "C2", {"valid_from": Y2022})])
    assert sorted(e["target_id"] for e in edges if e["type"] == ISSUED_BY) == ["C1", "C2"]
    assert "conflicting_targets" not in [r["reason"] for r in reviews]


def test_the_same_issuer_named_twice_is_one_link_and_two_securities_keep_theirs():
    edges, reviews = project([("S1", "C1", {"valid_from": Y2020}), ("S1", "C1", {"valid_from": Y2022}),
                              ("S2", "C2", {"valid_from": Y2020})])
    assert not reviews
    assert len([e for e in edges if e["type"] == ISSUED_BY]) == 2


def test_a_type_that_states_one_target_false_is_refused():
    with pytest.raises(ValueError, match="one_target is true"):
        project([("S1", "C1", {})], types={ISSUED_BY: {**TYPES[ISSUED_BY], "one_target": False}})
