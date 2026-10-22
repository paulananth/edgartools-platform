"""Real PG16: the Person link engine through the Merge Stage (mastering to-do
14), on synthetic Forms 3/4/5 filings; the reader is ticket 10.

Each filing is its own record, starting at the reporting owner's Person record
and ending at the issuer's Company record. Its sightings fold into one link per
Person, Company and capacity, and `mdm.is_insider` shows the Section 16 ones.
"""

from __future__ import annotations

import pytest

from sqlalchemy import text

from edgar_warehouse.mdm.clean.store import migrate
from tests.integration.test_clean_mdm_postgres import apply, documents, identity_and_binding, source


D1, D2, D3 = (f"2024-0{m}-15T00:00:00+00:00" for m in (1, 3, 6))


def setup(database):
    person = source("owner", kind="person", fields={"name": "Jane Roe"})
    issuer = source("issuer")
    pairs = [identity_and_binding(person), identity_and_binding(issuer)]
    apply(database, 1, assertions=[person, issuer], identities=[i for i, _ in pairs],
          decisions=[d for _, d in pairs])
    return person, issuer, [i["entity_id"] for i, _ in pairs]


def filing(n, person, issuer, *links):
    return source(f"filing-{n}", kind="person", fields={},
                  relationships=[{"source_subject": person["subject"],
                                  "target_subject": issuer["subject"], **link} for link in links])


def sighting(on, capacity, kind="EMPLOYED_BY", **more):
    return {"type": kind, "capacity": capacity, "on": on, **more}


def links(database):
    return {(e["type"], e["capacity"]): e for e in documents(database, "relationship").values()
            if not e.get("retired")}


def insiders(database):
    with database.application.connect() as conn:
        return sorted(conn.execute(text(
            "SELECT person_id, company_id, link_type, capacity FROM mdm.is_insider")).all())


def test_filings_fold_into_one_link_per_capacity_and_the_view_shows_the_insiders(database):
    person, issuer, (person_id, company_id) = setup(database)
    filings = [
        filing(1, person, issuer, sighting(D1, "director"), sighting(D1, "officer", title="CFO"),
               sighting(D1, "ten_percent_owner", kind="CONTROLS"), sighting(D1, "employee")),
        filing(2, person, issuer, sighting(D2, "director", held=False), sighting(D2, "officer", title="CEO")),
        filing(3, person, issuer, sighting(D3, "director")),
    ]
    apply(database, 2, assertions=filings)
    found = links(database)
    assert [(p["valid_from"], p["valid_to"], p["valid_to_basis"])
            for p in found[("EMPLOYED_BY", "director")]["periods"]] == [
        (D1, D2, "observed"), (D3, None, None)]
    (officer,) = found[("EMPLOYED_BY", "officer")]["periods"]
    assert officer["titles"] == [{"title": "CFO", "on": D1}, {"title": "CEO", "on": D2}]
    # An employee is no Section 16 insider.
    assert insiders(database) == sorted([
        (person_id, company_id, "CONTROLS", "ten_percent_owner"),
        (person_id, company_id, "EMPLOYED_BY", "director"),
        (person_id, company_id, "EMPLOYED_BY", "officer"),
    ])


def test_a_sighting_after_a_stated_end_opens_a_steward_review(database):
    person, issuer, _ = setup(database)
    apply(database, 2, assertions=[
        filing(1, person, issuer, sighting(D1, "officer")),
        filing(2, person, issuer, sighting(D2, "officer", held=False, basis="stated")),
        filing(3, person, issuer, sighting(D3, "officer")),
    ])
    (period,) = links(database)[("EMPLOYED_BY", "officer")]["periods"]
    assert (period["valid_to"], period["valid_to_basis"]) == (D2, "stated")
    (review,) = [r for r in documents(database, "review").values()
                 if r["reason"] == "contradicts_stated_end"]
    assert (review["open"], review["blocking"], review["on"]) == (True, True, D3)


@pytest.mark.parametrize(("kind", "relationship"), [
    ("person", {"type": "EMPLOYED_BY", "capacity": "director", "on": D1}),
    ("company", {"type": "ACCOUNTING_PARENT", "scope": "consolidated", "valid_from": D1}),
])
def test_revoking_a_record_binding_leaves_its_relationship_endpoint_unresolved(database, kind, relationship):
    from edgar_warehouse.mdm.clean.evidence import decision

    owned = source("owned", kind=kind, fields={"name": "Invented Record"})
    other = source("other")
    pairs = [identity_and_binding(owned), identity_and_binding(other)]
    apply(database, 1, assertions=[owned, other], identities=[item for item, _ in pairs], decisions=[item for _, item in pairs])
    record = source("relationship", kind=kind, fields={}, relationships=[{
        "source_subject": owned["subject"], "target_subject": other["subject"], **relationship,
    }])
    apply(database, 2, assertions=[record])
    assert documents(database, "relationship")
    original = pairs[0][1]
    revoke = decision("revoke", actor="fixture", reason="corrected source match", at="2026-02-01T00:00:00+00:00",
                      target=original["decision_id"], subject=owned["subject"], entity_id=original["entity_id"])
    apply(database, 3, decisions=[revoke])
    assert not any(not edge.get("retired") for edge in documents(database, "relationship").values())
    assert any(review["reason"] == "unresolved_endpoint" and review.get("waiting_for_end")
               and not review.get("retired") for review in documents(database, "review").values())


def test_a_populated_store_at_003_takes_004(database):
    person, issuer, _ = setup(database)
    apply(database, 2, assertions=[filing(1, person, issuer, sighting(D1, "director"))])
    before = insiders(database)
    with database.admin.begin() as conn:
        conn.execute(text("DROP VIEW mdm.is_insider"))
        # The migration ledger is append-only; only this simulation of an older
        # store goes around that, as the database owner.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM mdm.migration WHERE name='004_is_insider.sql'"))
        conn.execute(text("SET LOCAL session_replication_role = origin"))
        count = conn.scalar(text("SELECT count(*) FROM mdm.current_record"))
    migrate(database.admin, application_role="clean_application")
    assert insiders(database) == before != []
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.current_record")) == count


def test_under_the_real_names_a_ten_percent_owner_is_a_beneficial_owner_and_an_insider(database):
    """Profiling ticket 04b: CONTROLS is gone; Forms 3/4/5's ten percent owner is
    BENEFICIAL_OWNER_OF, and mdm.is_insider shows it beside the director."""
    from edgar_warehouse.mdm.clean.store import register_policy
    from edgar_warehouse.rules import files

    with database.admin.begin() as conn:
        database.policy = register_policy(conn, {
            "version": 1, "required_consumers": ["export", "graph"], "automatic_rules": [],
            "fields": {"company": {"name": {"sources": ["fixture.primary", "fixture.secondary"]},
                                   "address": {"sources": ["fixture.primary", "fixture.secondary"]}}},
            "relationships": files.policy()["relationships"]})
    person, issuer, (person_id, company_id) = setup(database)
    apply(database, 2, assertions=[filing(1, person, issuer, sighting(D1, "director"),
                                          sighting(D1, "ten_percent_owner", kind="BENEFICIAL_OWNER_OF"))])
    assert insiders(database) == sorted([
        (person_id, company_id, "BENEFICIAL_OWNER_OF", "ten_percent_owner"),
        (person_id, company_id, "EMPLOYED_BY", "director"),
    ])
