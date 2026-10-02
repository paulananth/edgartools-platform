"""Real PG16: a review names only the records it is about (platform
validation 05b, part 1; operator, 2026-10-01: "Fix reviews first").

Every review used to copy every record and Company of its save's closure, so
a save's size grew with reviews times records: 200 GLEIF links came to 24 MB,
over the 16 MiB cap. A closure is a connected component, so a later save that
touches any of its records loads all of them, and finds a review by its own
records alone.
"""

from __future__ import annotations

from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_mdm_postgres import (
    AT,
    apply,
    decision,
    documents,
    identity_and_binding,
    source,
)

postgres = core.postgres
database = core.database


def parent(target, start=AT, end=None):
    return {"type": "ACCOUNTING_PARENT", "target_subject": target["subject"], "valid_from": start,
            "valid_to": end, "scope": "consolidated"}


def open_reviews(database, reason):
    return [r for r in documents(database, "review").values() if r["reason"] == reason and r["open"]]


def test_a_review_names_only_its_own_record_not_the_whole_family(database):
    owner = source("owner")
    children = [source(f"child-{n}", relationships=[parent(owner)]) for n in range(20)]
    stray = source("stray", relationships=[parent(owner)])
    pairs = [identity_and_binding(r) for r in [owner, *children]]
    apply(database, 1, assertions=[owner, *children, stray], identities=[i for i, _ in pairs],
          decisions=[d for _, d in pairs])
    (review,) = open_reviews(database, "binding_required")
    assert review["affected_subjects"] == [stray["subject"]]
    assert review["affected_entities"] == []


def test_a_parent_conflict_names_the_three_companies_and_is_retired_when_fixed(database):
    a, b, hub = source("a"), source("b"), source("hub")
    others = [source(f"sibling-{n}", relationships=[parent(hub)]) for n in range(10)]
    child = source("child", relationships=[parent(a), parent(b), parent(hub)])
    records = [child, a, b, hub, *others]
    pairs = [identity_and_binding(r) for r in records]
    apply(database, 1, assertions=records, identities=[i for i, _ in pairs], decisions=[d for _, d in pairs])
    entity = {r["subject"]: i["entity_id"] for r, (i, _) in zip(records, pairs)}
    reviews = open_reviews(database, "conflicting_accounting_parents")
    assert reviews
    for review in reviews:
        assert set(review["affected_entities"]) <= {entity[r["subject"]] for r in (child, a, b, hub)}
        assert set(review["affected_subjects"]) <= {r["subject"] for r in (child, a, b, hub)}
        assert entity[child["subject"]] in review["affected_entities"]
    # The fix arrives through a sibling's save: the family is one closure, so
    # the conflict is found by its own records and retired.
    fixed = source("child", revision=2, relationships=[parent(a)])
    apply(database, 2, assertions=[source("sibling-0", revision=2, fields={"name": "Renamed"},
                                          relationships=[parent(hub)]), fixed])
    assert not open_reviews(database, "conflicting_accounting_parents")


def test_an_override_without_a_record_names_its_companys_records_and_is_retired_on_revoke(database):
    a = source("a")
    b = source("b", source_code="fixture.secondary")
    i, bind_a = identity_and_binding(a)
    _, bind_b = identity_and_binding(b, entity_id=i["entity_id"])
    override = decision("override", actor="reviewer", reason="verified correction", at=AT,
                        entity_id=i["entity_id"], field="name", value="Steward name",
                        evidence=[a["assertion_id"]])
    apply(database, 1, assertions=[a, b], identities=[i], decisions=[bind_a, bind_b, override])
    (review,) = open_reviews(database, "ambiguous_override_owner")
    assert set(review["affected_subjects"]) == {a["subject"], b["subject"]}
    assert review["affected_entities"] == [i["entity_id"]]
    revoke = decision("revoke", actor="reviewer", reason="owner unclear", at="2026-03-01T00:00:00Z",
                      target=override["decision_id"])
    apply(database, 2, decisions=[revoke])
    assert not open_reviews(database, "ambiguous_override_owner")
