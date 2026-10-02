"""Per-kind Stage and Master views over the one evidence and master table.

Clean MDM keeps every kind in one table with the kind as a value inside it.
Migration 033 presents that as one pair of views per kind, so a reader can ask
for the Company stage without repeating the filter and without a second copy of
the data to keep in step; 034 gave the source-side pair the Stage name.

  <kind>_stage         one row per source record, the whole claim
  <kind>_stage_field   one row per (source record, field)
  <kind>_master        one row per entity
  <kind>_master_field  one row per (entity, field), naming the winning source

These tests hold the three things that can rot: the kind list, which now lives
in SQL and in Python and cannot be derived across that boundary; the column
lists, which a view freezes at creation; and the names themselves, since 033's
generator still spells the Stage pair `_evidence` and cannot be corrected.
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from edgar_warehouse.mdm.clean.classification import CLASSIFICATION_VERDICTS
from edgar_warehouse.mdm.clean.evidence import KINDS
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database

SHAPES = ("stage", "stage_field", "master", "master_field")


def installed_views(database) -> set[str]:
    with database.application.connect() as conn:
        return {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.views "
                    "WHERE table_schema='mdm'"
                )
            )
        }


def permitted_kinds(database) -> set[str]:
    """The kinds mdm.master_entity itself allows, read from its constraint.

    Anchored on the kind list rather than scanning the whole definition, for the
    same reason migration 033 is: a later migration may add another condition to
    this constraint, and its literals are not kinds.
    """
    with database.application.connect() as conn:
        definitions = [
            r[0]
            for r in conn.execute(
                text("""SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid='mdm.master_entity'::regclass AND contype='c'
                  AND pg_get_constraintdef(oid) LIKE '%kind%'""")
            )
        ]
    assert len(definitions) == 1, (
        f"expected exactly one kind CHECK on mdm.master_entity, found {definitions}"
    )
    listed = re.search(r"kind[^=]*= ANY \(ARRAY\[(.*?)\]\)", definitions[0])
    assert listed, f"cannot read the permitted kinds out of {definitions[0]}"
    return set(re.findall(r"'([a-z_]+)'", listed.group(1)))


def columns(database, relation: str) -> list[str]:
    with database.application.connect() as conn:
        return [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='mdm' AND table_name=:t "
                    "ORDER BY ordinal_position"
                ),
                {"t": relation},
            )
        ]


def test_one_view_per_kind_per_shape_and_no_others(database):
    """The schema, Python and the views name the same set of kinds.

    The kind list cannot be derived across the SQL/Python boundary, so this is
    what holds the copies equal. The migration itself refuses to install if its
    own list has drifted from the constraint; this proves the Python copy too,
    and that the loop produced every view it promised.
    """
    schema_kinds = permitted_kinds(database)
    assert schema_kinds == KINDS, (
        "mdm.master_entity and evidence.KINDS name different kinds"
    )
    # classification.CLASSIFICATION_VERDICTS is derived from KINDS rather than
    # restated, so it needs no copy of its own -- only its two extra verdicts.
    assert CLASSIFICATION_VERDICTS - KINDS == {"entity_undetermined", "deferred"}
    # Plus two views across every kind: the records still waiting, each with
    # its Probable Kind (036), and the one read of a current entity (042);
    # and the Section 16 insiders over the Person links (004).
    assert installed_views(database) == ({
        f"{kind}_{shape}" for kind in schema_kinds for shape in SHAPES
    } | {"stage_waiting", "current_entity", "is_insider"}) - {"company_master"}
    assert columns(database, "company")
    # Exact equality above already forbids it, but say it outright: 034 renamed
    # 033's source-side pair, so not one view still carries the old name.
    assert not [v for v in installed_views(database) if "_evidence" in v]


# What a whole-record view deliberately does not show under the base table's own
# name, and why. Anything outside this map must appear, or a structural column
# has gone missing from a view without anyone deciding that it should.
RENAMED_OR_DROPPED = {
    "source_reading": {},
    # object_id is the entity under this view; object_type is constant 'entity'
    # for every row a <kind>_master view can return, so it carries no meaning.
    "current_record": {"object_id": "entity_id", "object_type": None},
}


@pytest.mark.parametrize(
    ("base", "view"),
    [("source_reading", "company_stage"), ("current_record", "person_master")],
)
def test_a_whole_record_view_shows_every_column_of_its_base_table(database, base, view):
    """A view freezes its column list at creation.

    The migration lists columns rather than using SELECT *, precisely so that a
    structural column added to a base table later is a deliberate edit rather
    than a silent omission: with SELECT * the views would keep serving the old
    column set for ever, and nothing would say so.

    This is what makes it deliberate. Add a column to mdm.source_reading or to
    mdm.current_record and it fails here until 033's column lists are updated, or
    until the column is named in RENAMED_OR_DROPPED with a reason.
    """
    shown = set(columns(database, view))
    missing = set()
    for column in columns(database, base):
        alias = RENAMED_OR_DROPPED[base].get(column, column)
        if alias is not None and alias not in shown:
            missing.add(column)
    assert not missing, (
        f"mdm.{base} has columns {sorted(missing)} that mdm.{view} does "
        "not show; add them to migration 033's column lists, or to "
        "RENAMED_OR_DROPPED with the reason they are left out"
    )


def test_a_reader_may_select_from_a_view_but_never_write_through_it(database):
    """A single-table view with no set-returning function is auto-updatable.

    company_stage is exactly that shape, so an INSERT through it would reach
    mdm.source_reading and bypass save_batch entirely. The immutable_row trigger
    does not help: it fires on UPDATE and DELETE, not INSERT. What refuses the
    write is the privilege, and this proves the privilege rather than trusting
    store.migrate()'s blanket re-grant to have covered views.
    """
    a = core.source(key="write-probe", fields={"name": "Acme"})
    core.apply(database, 1, assertions=[a])
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.company_stage")) == 1
    for statement in (
        (
            "INSERT INTO mdm.company_stage(assertion_id,source_code,record_key,"
            "publication_key,revision,effective_at,batch_id,body) "
            "VALUES('forged','fixture.primary','x','p1',1,now(),'work-1','{}'::jsonb)"
        ),
        "UPDATE mdm.company_stage SET record_key='moved'",
        "DELETE FROM mdm.company_stage",
    ):
        with (
            pytest.raises(ProgrammingError, match="permission denied"),
            database.application.begin() as conn,
        ):
            conn.execute(text(statement))
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.source_reading")) == 1


def test_the_privilege_is_what_refuses_the_write_not_the_view_shape(database):
    """Without this the test above could pass for the wrong reason.

    If PostgreSQL considered the whole-record view read-only, the refusal above
    would prove nothing about privileges and would stop proving anything the day
    the shape changed. It does not: PostgreSQL reports company_stage as
    insertable and updatable, and the application role holds SELECT alone.
    """
    with database.application.connect() as conn:
        assert conn.execute(
            text(
                "SELECT is_insertable_into,is_updatable FROM information_schema.views "
                "WHERE table_schema='mdm' AND table_name='company_stage'"
            )
        ).all() == [("YES", "YES")]
        # The exploded shape is inherently safe: jsonb_each makes it read-only.
        assert conn.execute(
            text(
                "SELECT is_insertable_into,is_updatable FROM information_schema.views "
                "WHERE table_schema='mdm' AND table_name='company_stage_field'"
            )
        ).all() == [("NO", "NO")]
        assert conn.execute(
            text(
                "SELECT privilege_type FROM information_schema.table_privileges "
                "WHERE table_schema='mdm' AND table_name='company_stage' "
                "AND grantee='clean_application' ORDER BY privilege_type"
            )
        ).all() == [("SELECT",)]


def test_every_permitted_kind_has_its_views(database):
    """The views are generated from master_entity's own kind check, so a new
    kind gets its views without a second list that could drift from it."""
    with database.admin.connect() as conn:
        permitted = set(conn.scalars(text(
            "SELECT m[1] FROM pg_constraint c, "
            "LATERAL regexp_matches(pg_get_constraintdef(c.oid), '''([a-z_]+)''', 'g') m "
            "WHERE c.conname = 'master_entity_kind_check'")))
        views = set(conn.scalars(text(
            "SELECT viewname FROM pg_views WHERE schemaname = 'mdm'")))
    assert len(permitted) == 8
    for kind in permitted:
        assert {kind + "_stage", kind + "_stage_field"} <= views
        if kind != "company":
            assert {kind + "_master", kind + "_master_field"} <= views


def test_two_kinds_from_one_batch_separate_into_their_own_views(database):
    """A Form 4 is the real case: one filing, an issuer and a reporting owner.

    Both land in one assertion table in one batch. The views are what make them
    look like a Company shelf and a Person shelf.
    """
    company = core.source(key="issuer-1", fields={"name": "Acme"})
    person = core.source(key="owner-1", kind="person", fields={"name": "Ada Lovelace"})
    core.apply(database, 1, assertions=[company, person])
    with database.application.connect() as conn:
        assert [
            r[0]
            for r in conn.execute(text("SELECT record_key FROM mdm.company_stage"))
        ] == ["issuer-1"]
        assert [
            r[0]
            for r in conn.execute(text("SELECT record_key FROM mdm.person_stage"))
        ] == ["owner-1"]
        # A kind nothing asserted is empty, not missing.
        assert conn.scalar(text("SELECT count(*) FROM mdm.venue_stage")) == 0


def test_a_field_no_view_names_needs_no_migration(database):
    """The maintenance claim, proved rather than asserted.

    A field is a key inside the jsonb body, so a field the policy has never
    carried before arrives as a new row in the exploded shape with no schema
    change, no view edit and no migration.
    """
    a = core.source(
        key="new-field-1",
        fields={"name": "Acme", "lei_registration_status": "ISSUED"},
    )
    core.apply(database, 1, assertions=[a])
    with database.application.connect() as conn:
        assert sorted(
            conn.execute(
                text(
                    "SELECT field_name,field_value,operation "
                    "FROM mdm.company_stage_field ORDER BY field_name"
                )
            ).all()
        ) == [
            ("lei_registration_status", "ISSUED", "value"),
            ("name", "Acme", "value"),
        ]


def test_the_master_field_view_names_the_source_that_won_each_field(database):
    """The stage shape over the master record: one row per mastered field.

    This is the question the legacy per-source stage table existed to answer --
    which source supplied the value that survived -- without a stage table.
    """
    primary = core.source(key="m1", fields={"name": "Acme", "address": "1 Way"})
    secondary = core.source(
        key="m1", source_code="fixture.secondary", fields={"name": "Acme Holdings"}
    )
    identity, binding = core.identity_and_binding(primary)
    second_binding = core.decision(
        "bind",
        actor="steward",
        reason="fixture source reviewed",
        at=core.AT,
        subject=secondary["subject"],
        entity_id=identity["entity_id"],
        evidence=[secondary["assertion_id"]],
    )
    core.apply(
        database,
        1,
        assertions=[primary, secondary],
        identities=[identity],
        decisions=[binding, second_binding],
    )
    with database.application.connect() as conn:
        assert conn.execute(
            text(
                "SELECT field_name,field_value,source_code,conflict_count "
                "FROM mdm.company_master_field ORDER BY field_name"
            )
        ).all() == [
            ("address", "1 Way", "fixture.primary", 0),
            # fixture.primary outranks fixture.secondary in the policy, and the
            # loser is counted rather than lost.
            ("name", "Acme", "fixture.primary", 1),
        ]
        assert conn.execute(
            text("SELECT entity_id::text,status FROM mdm.company WHERE valid_to IS NULL")
        ).all() == [(identity["entity_id"], "accepted")]
        # The same entity is absent from every other kind's master view.
        assert conn.scalar(text("SELECT count(*) FROM mdm.person_master")) == 0


def test_the_master_field_view_carries_the_kind_version_beside_the_digest(database):
    """survivorship.py:316 puts the version beside the digest on purpose.

    A digest alone tells a reader only that something differs, never which
    authored document it came from. <kind>_master_field is exactly the reader
    that would otherwise lose it, so the view must carry both.

    The shared fixture policy is the older `fields` shape, which authors no kind
    version at all, so this registers a `kinds`-shaped policy of its own rather
    than asserting against a null and calling it proof.
    """
    from edgar_warehouse.mdm.clean.merge import MergeStage
    from edgar_warehouse.mdm.clean.store import Store, register_policy

    sources = ["fixture.primary", "fixture.secondary"]
    with database.admin.begin() as conn:
        versioned = register_policy(
            conn,
            {
                "version": 1,
                "required_consumers": ["export", "graph"],
                "automatic_rules": [],
                "kinds": {
                    "company": {
                        "version": "company-1",
                        "fields": {"name": {"sources": sources}},
                    }
                },
            },
        )
    a = core.source(key="kv-1", fields={"name": "Acme"})
    identity, binding = core.identity_and_binding(a)
    MergeStage(Store(database.application)).apply(
        batch_id="work-1",
        run_id=str(uuid4()),
        policy_digest=versioned,
        consumer="fixture",
        expected_checkpoint=0,
        checkpoint=1,
        as_of=core.AS_OF,
        assertions=[a],
        identities=[identity],
        decisions=[binding],
    )
    with database.application.connect() as conn:
        field = conn.execute(
            text(
                "SELECT field_name,kind_version,policy_digest "
                "FROM mdm.company_master_field"
            )
        ).one()
    assert field.field_name == "name"
    assert field.kind_version == "company-1"
    # The body's policy_digest key holds the *kind's* authority digest, not the
    # digest of the policy the batch ran under (ticket 02 decision 3): a
    # classification edit elsewhere in the document must not churn this field.
    # The two are deliberately different values, which is why the version beside
    # it is the only thing naming the authored document.
    assert field.policy_digest != versioned
    assert re.fullmatch(r"[0-9a-f]{64}", field.policy_digest)




def test_stage_waiting_shows_every_waiting_record_with_its_probable_kind(database):
    """A record no kind accepted waits in the Stage with the kind it probably
    is, whether or not a classification step named one; an accepted record
    is not waiting."""
    from edgar_warehouse.mdm.clean.evidence import deferred_record

    def waiting(line, **probable):
        return deferred_record(
            source_code="fixture.primary",
            publication_key="p1",
            record_locator=f"line:{line}",
            schema_version="1",
            reason="classification_deferred",
            raw_record={"key": f"wait-{line}"},
            provenance={
                "adapter_version": "v1",
                "classification": {"rule_id": "r", "version": "1", "step": "6", "verdict": "deferred"},
            },
            **probable,
        )

    core.apply(
        database,
        1,
        assertions=[core.source(key="accepted", fields={"name": "Acme"})],
        deferred=[waiting(1, probable_kind="person"), waiting(2)],
    )
    with database.application.connect() as conn:
        rows = conn.execute(text(
            "SELECT record_locator, probable_kind, reason, rule_id, rule_step "
            "FROM mdm.stage_waiting ORDER BY record_locator")).all()
    assert [tuple(r) for r in rows] == [
        ("line:1", "person", "classification_deferred", "r", "6"),
        ("line:2", None, "classification_deferred", "r", "6"),
    ]
