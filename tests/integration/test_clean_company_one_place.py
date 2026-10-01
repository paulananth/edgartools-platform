"""Real PG16: each Company is kept in one place, the dated Company table.

Company mastering ticket 17. The operator chose, on 2026-09-26 at 13:03 ET,
to remove the Company copy steps rather than tune them. The Merge Stage
writes a Company to `mdm.company`, or `mdm.company_alias` for a
merged-away ID, and reads it there through `mdm.current_entity`.
`mdm.current_record` keeps every other kind, and all relationships and
reviews.

Before this ticket, `projection` held each Company as well. A trigger copied
it to the Company table, and another rewrote each publication from that table
with the bytes it already held.
"""

from __future__ import annotations


from sqlalchemy import text

from edgar_warehouse.mdm.clean.consumer import ContractReader
from edgar_warehouse.mdm.clean.store import canonical
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database


def companies_in_projection(db) -> dict[str, dict]:
    with db.application.connect() as conn:
        return dict(
            conn.execute(
                text(
                    "SELECT object_id, body FROM mdm.current_record "
                    "WHERE object_type='entity' AND body->>'kind'='company'"
                )
            ).all()
        )


def computed(db, batch_id: str) -> dict[str, dict]:
    """The entity objects the Merge Stage sent in one batch."""
    with db.application.connect() as conn:
        effects = conn.scalar(
            text("SELECT effects FROM mdm.batch WHERE batch_id=:b"), {"b": batch_id}
        )
    return {
        p["object_id"]: p["body"]
        for p in effects["projections"]
        if p["object_type"] == "entity"
    }


def merged_pair(db) -> tuple[str, str]:
    """Two steward Companies, the second merged into the first."""
    a = core.source("a", fields={"name": "First"})
    b = core.source("b", fields={"name": "Second"})
    i, bind_a = core.identity_and_binding(a)
    j, bind_b = core.identity_and_binding(b)
    j["published_at"] = "2026-01-02T00:00:00Z"
    core.apply(db, 1, assertions=[a, b], identities=[i, j], decisions=[bind_a, bind_b])
    merge = core.decision(
        "merge",
        actor="reviewer",
        reason="reviewed match",
        at="2026-02-01T00:00:00Z",
        left=i["entity_id"],
        right=j["entity_id"],
    )
    core.apply(db, 2, decisions=[merge])
    return i["entity_id"], j["entity_id"]


def test_a_commit_writes_each_company_only_to_the_company_table(database):
    a = core.source("a")
    identity, bind = core.identity_and_binding(a)
    core.apply(database, 1, assertions=[a], identities=[identity], decisions=[bind])
    assert companies_in_projection(database) == {}
    with database.application.connect() as conn:
        stored = dict(
            conn.execute(
                text(
                    "SELECT entity_id::text, body FROM mdm.company WHERE valid_to IS NULL"
                )
            ).all()
        )
    assert stored == computed(database, "work-1")


def test_a_merged_away_company_is_only_an_alias_row(database):
    survivor, merged = merged_pair(database)
    assert companies_in_projection(database) == {}
    with database.application.connect() as conn:
        aliases = conn.execute(
            text(
                "SELECT alias_id::text, canonical_id::text FROM mdm.company_alias "
                "WHERE valid_to IS NULL"
            )
        ).all()
    assert aliases == [(merged, survivor)]
    current = core.documents(database, "entity")
    assert (
        current[merged]
        == computed(database, "work-2")[merged]
        == {
            "entity_id": merged,
            "kind": "company",
            "canonical_id": survivor,
            "status": "alias",
        }
    )
    assert current[survivor]["fields"]["name"]["value"] == "First"
    # The as-of read builds the same alias object from company_alias.
    page = ContractReader(database.application).snapshot_page("entity", generation=2)
    assert {i["object_id"]: i["body"] for i in page["items"]}[merged] == current[merged]


def test_a_person_stays_in_projection(database):
    person = core.source("p", kind="person", fields={"name": "Jane Roe"})
    identity, bind = core.identity_and_binding(person)
    core.apply(
        database, 1, assertions=[person], identities=[identity], decisions=[bind]
    )
    with database.application.connect() as conn:
        kinds = (
            conn.execute(
                text(
                    "SELECT body->>'kind' FROM mdm.current_record WHERE object_type='entity'"
                )
            )
            .scalars()
            .all()
        )
    assert kinds == ["person"]
    assert core.documents(database, "entity") == computed(database, "work-1")


def test_a_company_change_alone_changes_the_assessment_snapshot(database):
    """The snapshot reads each Company from the Company table.

    Only the Company row changes: no assertion, decision or identity in the
    scope does. Before 042 the snapshot read projection and missed it.
    """
    a = core.source("a")
    identity, bind = core.identity_and_binding(a)
    core.apply(database, 1, assertions=[a], identities=[identity], decisions=[bind])
    person = core.source("p", kind="person", fields={"name": "Jane Roe"})
    other, bind_other = core.identity_and_binding(person)
    core.apply(
        database, 2, assertions=[person], identities=[other], decisions=[bind_other]
    )
    scope = canonical({"keys": [identity["entity_id"]], "sources": []})
    snapshot = text("SELECT mdm.match_proposal_snapshot(CAST(:s AS jsonb))")
    with database.admin.begin() as conn:
        before = conn.scalar(snapshot, {"s": scope})
        body = conn.scalar(
            text("SELECT body FROM mdm.company WHERE valid_to IS NULL")
        )
        body["fields"]["name"]["value"] = "Renamed"
        conn.execute(
            text(
                "SELECT mdm.record_company_version(CAST(:b AS jsonb),'work-2',now())"
            ),
            {"b": canonical(body)},
        )
        assert conn.scalar(snapshot, {"s": scope}) != before


def test_the_company_copy_steps_are_gone(database):
    with database.admin.connect() as conn:
        triggers = (
            conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger WHERE tgname IN "
                    "('project_company_version','publish_company_authority')"
                )
            )
            .scalars()
            .all()
        )
        functions = (
            conn.execute(
                text(
                    "SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname='mdm' AND proname IN "
                    "('company_payload_from_table','publish_company_authority',"
                    "'project_company_version')"
                )
            )
            .scalars()
            .all()
        )
    assert triggers == [] and functions == []


def test_a_publication_carries_the_objects_the_merge_stage_computed(database):
    """Characterization: true before and after this ticket."""
    merged_pair(database)
    with database.application.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT p.batch_id, p.payload->'objects', b.effects->'projections' "
                "FROM mdm.outbox p JOIN mdm.batch b USING (batch_id)"
            )
        ).all()
    assert rows and all(objects == sent for _, objects, sent in rows)


