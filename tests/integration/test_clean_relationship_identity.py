"""Real PG16: a relationship is one link, whatever restates it (platform
validation 06a; operator, 2026-10-01).

- Design 1: a link is identified by its type, its two ends and its scope.
  Dates and status are periods of that one link, so a restatement keeps its id.
- Design 2: a link ends only on its source's own statement; a later delivery
  that does not mention it leaves it open.
- A link may start at another record than the one stating it
  (`source_subject`), as a GLEIF relationship record starts at its child.
"""

from __future__ import annotations

from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_mdm_postgres import (
    AT,
    apply,
    documents,
    identity_and_binding,
    source,
)

postgres = core.postgres
database = core.database

LATER = "2026-03-01T00:00:00+00:00"


def parent(target, start=AT, end=None, **more):
    return {"type": "ACCOUNTING_PARENT", "target_subject": target["subject"], "valid_from": start,
            "valid_to": end, "scope": "consolidated", **more}


def bound(*records):
    """Each record with a new Company and its binding, from the record as applied."""
    return [identity_and_binding(r) for r in records]


def links(database):
    return [e for e in documents(database, "relationship").values() if not e.get("derived")]


def test_a_restated_link_keeps_its_id_and_takes_the_new_period(database):
    owner = source("owner")
    child = source("child", relationships=[parent(owner, status="ACTIVE")])
    pairs = bound(child, owner)
    apply(database, 1, assertions=[child, owner], identities=[i for i, _ in pairs],
          decisions=[d for _, d in pairs])
    (first,) = links(database)
    ended = source("child", revision=2, relationships=[parent(owner, end=LATER, status="INACTIVE")])
    apply(database, 2, assertions=[ended])
    (second,) = links(database)
    assert second["relationship_id"] == first["relationship_id"]
    assert [(p["valid_to"], p["status"]) for p in second["periods"]] == [(LATER, "INACTIVE")]


def test_a_delivery_that_does_not_mention_a_link_leaves_it_open(database):
    owner, other = source("owner"), source("other")
    child = source("child", relationships=[parent(owner)])
    pairs = bound(child, owner, other)
    apply(database, 1, assertions=[child, owner, other], identities=[i for i, _ in pairs],
          decisions=[d for _, d in pairs])
    (before,) = links(database)
    apply(database, 2, assertions=[source("other", revision=2, fields={"name": "Other, renamed"})])
    (after,) = links(database)
    assert after["relationship_id"] == before["relationship_id"]
    assert after["periods"] == before["periods"]
    assert after["periods"][0]["valid_to"] is None


def test_a_parent_held_left_and_held_again_raises_no_conflict(database):
    a, b = source("a"), source("b")
    child = source("child", relationships=[
        parent(a, "2020-01-01T00:00:00+00:00", "2021-01-01T00:00:00+00:00"),
        parent(b, "2021-01-01T00:00:00+00:00", "2023-01-01T00:00:00+00:00"),
        parent(a, "2023-01-01T00:00:00+00:00"),
    ])
    pairs = bound(child, a, b)
    apply(database, 1, assertions=[child, a, b], identities=[i for i, _ in pairs],
          decisions=[d for _, d in pairs])
    reasons = {r["reason"] for r in documents(database, "review").values() if r["open"]}
    assert "conflicting_accounting_parents" not in reasons
    by_target = {e["target_id"]: e for e in links(database)}
    assert len(by_target[pairs[1][0]["entity_id"]]["periods"]) == 2
    assert len(by_target[pairs[2][0]["entity_id"]]["periods"]) == 1


def test_a_link_record_starts_at_the_record_it_names(database):
    child, owner = source("child"), source("owner")
    pairs = bound(child, owner)
    record = source("child|owner|ACCOUNTING_PARENT", source_code="fixture.secondary", fields={},
                    relationships=[parent(owner, source_subject=child["subject"])])
    apply(database, 1, assertions=[child, owner, record], identities=[i for i, _ in pairs],
          decisions=[d for _, d in pairs])
    (link,) = links(database)
    assert link["source_id"] == pairs[0][0]["entity_id"]
    assert link["target_id"] == pairs[1][0]["entity_id"]
    assert link["evidence"][0]["source_subject"] == child["subject"]
    # A record that only states a link has no identity of its own to bind.
    assert not any(r["reason"] == "binding_required" and r["open"]
                   for r in documents(database, "review").values())


def test_a_match_proposals_snapshot_sees_a_link_that_starts_at_its_key(database):
    """Migration 002: a proposal about a record goes stale when a link starting
    at that record arrives, as when a link ending at it does."""
    import json

    from sqlalchemy import text

    child, owner = source("child"), source("owner")
    pairs = bound(child, owner)
    apply(database, 1, assertions=[child, owner], identities=[i for i, _ in pairs],
          decisions=[d for _, d in pairs])
    scope = json.dumps({"keys": [child["subject"]], "sources": [], "consumer": "load"})

    def snapshot():
        with database.application.connect() as conn:
            return conn.scalar(text("SELECT mdm.match_proposal_snapshot(CAST(:s AS jsonb))"), {"s": scope})

    before = snapshot()
    record = source("child|owner|ACCOUNTING_PARENT", source_code="fixture.secondary", fields={},
                    relationships=[parent(owner, source_subject=child["subject"])])
    apply(database, 2, assertions=[record])
    assert snapshot() != before


def test_a_link_whose_parent_is_not_a_company_yet_waits_quietly(database):
    """Mastering to-do 02, D2 (operator, 2026-10-02: "Wait quietly"): a link
    whose other end is not an entity yet is not an open steward review. It
    waits, is counted, and becomes a link once that end is bound."""
    owner = source("owner")
    child = source("child", relationships=[parent(owner)])
    (child_pair,) = bound(child)
    apply(database, 1, assertions=[child, owner], identities=[child_pair[0]], decisions=[child_pair[1]])
    assert links(database) == []
    (waiting,) = [r for r in documents(database, "review").values() if r["reason"] == "unresolved_endpoint"]
    assert (waiting["open"], waiting["blocking"], waiting["waiting"]) == (False, False, True)
    (owner_pair,) = bound(owner)
    apply(database, 2, identities=[owner_pair[0]], decisions=[owner_pair[1]])
    (link,) = links(database)
    assert link["target_id"] == owner_pair[0]["entity_id"]
    assert not [r for r in documents(database, "review").values()
                if r["reason"] == "unresolved_endpoint" and not r.get("retired")]
