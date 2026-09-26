"""Real PG16: each Company is kept in one place, the dated Company table.

Company mastering ticket 17. The operator chose, on 2026-09-26 at 13:03 ET,
to remove the Company copy steps rather than tune them. The Merge Stage
writes a Company to `mdm_v2.company`, or `mdm_v2.company_alias` for a
merged-away ID, and reads it there through `mdm_v2.current_entity`.
`mdm_v2.projection` keeps every other kind, and all relationships and
reviews.

Before this ticket, `projection` held each Company as well. A trigger copied
it to the Company table, and another rewrote each publication from that table
with the bytes it already held.
"""

from __future__ import annotations

from unittest import mock
from uuid import uuid4

from sqlalchemy import text

import edgar_warehouse.mdm.clean.store as store_module
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_identifier_binding import (
    APPLE_CIK,
    _command,
    load,
    matching_policy,
    record,
)

postgres = core.postgres
database = core.database


def companies_in_projection(db) -> dict[str, dict]:
    with db.application.connect() as conn:
        return dict(
            conn.execute(
                text(
                    "SELECT object_id, body FROM mdm_v2.projection "
                    "WHERE object_type='entity' AND body->>'kind'='company'"
                )
            ).all()
        )


def computed(db, batch_id: str) -> dict[str, dict]:
    """The entity objects the Merge Stage sent in one batch."""
    with db.application.connect() as conn:
        effects = conn.scalar(
            text("SELECT effects FROM mdm_v2.batch WHERE batch_id=:b"), {"b": batch_id}
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
                    "SELECT entity_id::text, body FROM mdm_v2.company WHERE valid_to IS NULL"
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
                "SELECT alias_id::text, canonical_id::text FROM mdm_v2.company_alias "
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
                    "SELECT body->>'kind' FROM mdm_v2.projection WHERE object_type='entity'"
                )
            )
            .scalars()
            .all()
        )
    assert kinds == ["person"]
    assert core.documents(database, "entity") == computed(database, "work-1")


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
                    "WHERE n.nspname='mdm_v2' AND proname IN "
                    "('company_payload_from_table','publish_company_authority',"
                    "'project_company_version')"
                )
            )
            .scalars()
            .all()
        )
    assert triggers == [] and functions == []
    assert not hasattr(Store, "_company_output_from_table")


def test_a_publication_carries_the_objects_the_merge_stage_computed(database):
    """Characterization: true before and after this ticket."""
    merged_pair(database)
    with database.application.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT p.batch_id, p.payload->'objects', b.effects->'projections' "
                "FROM mdm_v2.publication p JOIN mdm_v2.batch b USING (batch_id)"
            )
        ).all()
    assert rows and all(objects == sent for _, objects, sent in rows)


def test_migration_042_applies_to_a_populated_store(postgres):
    """CLAUDE.md: over real rows, in production's order.

    A store at 040 holds a Company created by the CIK rule, two steward
    Companies (one merged into the other), a Person, and a `ready` assessment
    not yet applied. After 042:
    - no Company is left in `projection`;
    - each Company reads back unchanged;
    - the stored assessment's snapshot still matches, so it applies without
      being assessed again.
    """
    admin, app = postgres
    names = list(store_module.CLEAN_MDM_MIGRATIONS)
    through_041 = tuple(n for n in names if n < "042")
    with mock.patch.object(store_module, "CLEAN_MDM_MIGRATIONS", through_041):
        db = core.initialize_database(admin, app)
        policy = matching_policy(db)
        load(db, policy, "b1", record("x", cik=APPLE_CIK))
        merged_pair(db)
        person = core.source("p", kind="person", fields={"name": "Jane Roe"})
        identity, bind = core.identity_and_binding(person)
        core.apply(db, 3, assertions=[person], identities=[identity], decisions=[bind])
        stage = MergeStage(Store(db.application))
        late = _command(policy, "late", record("m", cik="0000789019"))
        prepared = stage.assess(**late, automatic=stage.propose(**late))
        before = core.documents(db, "entity")
        held = companies_in_projection(db)
        assert len(held) == 3  # the CIK rule's Company, the survivor, the alias
    core.migrate(admin, application_role="clean_application")
    assert companies_in_projection(db) == {}
    assert core.documents(db, "entity") == before
    with db.application.connect() as conn:
        stored, now = conn.execute(
            text(
                "SELECT body->>'snapshot', mdm_v2.assessment_snapshot(body->'scope') "
                "FROM mdm_v2.assessment WHERE assessment_id=:a"
            ),
            {"a": prepared["assessment_id"]},
        ).one()
    assert now == stored
    MergeStage(Store(db.application)).apply_assessment(
        prepared["assessment_id"], run_id=str(uuid4())
    )
    assert (
        sum(v["kind"] == "company" for v in core.documents(db, "entity").values()) == 4
    )
