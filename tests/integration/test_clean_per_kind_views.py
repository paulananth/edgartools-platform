"""Per-kind read views over the one evidence table and the one master table.

Clean MDM keeps every kind in one table with the kind as a value inside it.
Migration 033 presents that as one pair of views per kind, so a reader can ask
for Company evidence without repeating the filter and without a second copy of
the data to keep in step.

These tests hold the two things that can rot: the kind list, which now lives in
SQL and in Python and cannot be derived across that boundary, and the column
lists, which a view freezes at creation.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

import edgar_warehouse.mdm.migrations
from edgar_warehouse.mdm.clean.classification import CLASSIFICATION_VERDICTS
from edgar_warehouse.mdm.clean.evidence import KINDS
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database

SHAPES = ("evidence", "evidence_field", "master", "master_field")


def installed_views(database) -> set[str]:
    with database.application.connect() as conn:
        return {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.views "
                    "WHERE table_schema='mdm_v2'"
                )
            )
        }


def permitted_kinds(database) -> set[str]:
    """The kinds mdm_v2.identity itself allows, read from its constraint.

    Anchored on the kind list rather than scanning the whole definition, for the
    same reason migration 033 is: a later migration may add another condition to
    this constraint, and its literals are not kinds.
    """
    with database.application.connect() as conn:
        definitions = [
            r[0]
            for r in conn.execute(
                text("""SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid='mdm_v2.identity'::regclass AND contype='c'
                  AND pg_get_constraintdef(oid) LIKE '%kind%'""")
            )
        ]
    assert len(definitions) == 1, (
        f"expected exactly one kind CHECK on mdm_v2.identity, found {definitions}"
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
                    "WHERE table_schema='mdm_v2' AND table_name=:t "
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
        "mdm_v2.identity and evidence.KINDS name different kinds"
    )
    # classification.CLASSIFICATION_VERDICTS is derived from KINDS rather than
    # restated, so it needs no copy of its own -- only its two extra verdicts.
    assert CLASSIFICATION_VERDICTS - KINDS == {"entity_undetermined", "deferred"}
    assert installed_views(database) == {
        f"{kind}_{shape}" for kind in schema_kinds for shape in SHAPES
    }


# What a whole-record view deliberately does not show under the base table's own
# name, and why. Anything outside this map must appear, or a structural column
# has gone missing from a view without anyone deciding that it should.
RENAMED_OR_DROPPED = {
    "assertion": {},
    # object_id is the entity under this view; object_type is constant 'entity'
    # for every row a <kind>_master view can return, so it carries no meaning.
    "projection": {"object_id": "entity_id", "object_type": None},
}


@pytest.mark.parametrize(
    ("base", "view"),
    [("assertion", "company_evidence"), ("projection", "company_master")],
)
def test_a_whole_record_view_shows_every_column_of_its_base_table(database, base, view):
    """A view freezes its column list at creation.

    The migration lists columns rather than using SELECT *, precisely so that a
    structural column added to a base table later is a deliberate edit rather
    than a silent omission: with SELECT * the views would keep serving the old
    column set for ever, and nothing would say so.

    This is what makes it deliberate. Add a column to mdm_v2.assertion or to
    mdm_v2.projection and it fails here until 033's column lists are updated, or
    until the column is named in RENAMED_OR_DROPPED with a reason.
    """
    shown = set(columns(database, view))
    missing = set()
    for column in columns(database, base):
        alias = RENAMED_OR_DROPPED[base].get(column, column)
        if alias is not None and alias not in shown:
            missing.add(column)
    assert not missing, (
        f"mdm_v2.{base} has columns {sorted(missing)} that mdm_v2.{view} does "
        "not show; add them to migration 033's column lists, or to "
        "RENAMED_OR_DROPPED with the reason they are left out"
    )


def test_a_reader_may_select_from_a_view_but_never_write_through_it(database):
    """A single-table view with no set-returning function is auto-updatable.

    company_evidence is exactly that shape, so an INSERT through it would reach
    mdm_v2.assertion and bypass commit_batch entirely. The immutable_row trigger
    does not help: it fires on UPDATE and DELETE, not INSERT. What refuses the
    write is the privilege, and this proves the privilege rather than trusting
    store.migrate()'s blanket re-grant to have covered views.
    """
    a = core.source(key="write-probe", fields={"name": "Acme"})
    core.apply(database, 1, assertions=[a])
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.company_evidence")) == 1
    for statement in (
        (
            "INSERT INTO mdm_v2.company_evidence(assertion_id,source_code,record_key,"
            "publication_key,revision,effective_at,batch_id,body) "
            "VALUES('forged','fixture.primary','x','p1',1,now(),'work-1','{}'::jsonb)"
        ),
        "UPDATE mdm_v2.company_evidence SET record_key='moved'",
        "DELETE FROM mdm_v2.company_evidence",
    ):
        with (
            pytest.raises(ProgrammingError, match="permission denied"),
            database.application.begin() as conn,
        ):
            conn.execute(text(statement))
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.assertion")) == 1


def test_the_privilege_is_what_refuses_the_write_not_the_view_shape(database):
    """Without this the test above could pass for the wrong reason.

    If PostgreSQL considered the whole-record view read-only, the refusal above
    would prove nothing about privileges and would stop proving anything the day
    the shape changed. It does not: PostgreSQL reports company_evidence as
    insertable and updatable, and the application role holds SELECT alone.
    """
    with database.application.connect() as conn:
        assert conn.execute(
            text(
                "SELECT is_insertable_into,is_updatable FROM information_schema.views "
                "WHERE table_schema='mdm_v2' AND table_name='company_evidence'"
            )
        ).all() == [("YES", "YES")]
        # The exploded shape is inherently safe: jsonb_each makes it read-only.
        assert conn.execute(
            text(
                "SELECT is_insertable_into,is_updatable FROM information_schema.views "
                "WHERE table_schema='mdm_v2' AND table_name='company_evidence_field'"
            )
        ).all() == [("NO", "NO")]
        assert conn.execute(
            text(
                "SELECT privilege_type FROM information_schema.table_privileges "
                "WHERE table_schema='mdm_v2' AND table_name='company_evidence' "
                "AND grantee='clean_application' ORDER BY privilege_type"
            )
        ).all() == [("SELECT",)]


def test_the_migration_refuses_a_kind_list_that_has_drifted(database):
    """Migration 033's own guard, run against a deliberately wrong list.

    The guard is the only thing standing between a future ninth kind and a set
    of views that quietly omits it, and a guard that cannot fail is not a guard.

    This runs the migration's real text rather than a copy of it: the file's own
    DO block, with nothing changed but the kind array. A transcribed guard would
    only ever prove the transcription, and would keep passing after the original
    was edited or deleted.
    """
    source = (
        Path(edgar_warehouse.mdm.migrations.__file__).parent
        / "033_clean_mdm_per_kind_views.sql"
    ).read_text()
    block = source[source.index("DO $$") : source.index("$$;") + 3]
    declared = re.search(r"kinds text\[\] := ARRAY\[[^\]]*\];", block)
    assert declared, "migration 033 no longer declares its kind array as expected"
    drifted = block.replace(
        declared.group(0), "kinds text[] := ARRAY['company','person'];"
    )
    assert drifted != block
    with (
        pytest.raises(DBAPIError, match="but mdm_v2.identity permits"),
        database.admin.begin() as conn,
    ):
        conn.execute(text(drifted))


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
            for r in conn.execute(
                text("SELECT record_key FROM mdm_v2.company_evidence")
            )
        ] == ["issuer-1"]
        assert [
            r[0]
            for r in conn.execute(text("SELECT record_key FROM mdm_v2.person_evidence"))
        ] == ["owner-1"]
        # A kind nothing asserted is empty, not missing.
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.venue_evidence")) == 0


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
                    "FROM mdm_v2.company_evidence_field ORDER BY field_name"
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
                "FROM mdm_v2.company_master_field ORDER BY field_name"
            )
        ).all() == [
            ("address", "1 Way", "fixture.primary", 0),
            # fixture.primary outranks fixture.secondary in the policy, and the
            # loser is counted rather than lost.
            ("name", "Acme", "fixture.primary", 1),
        ]
        assert conn.execute(
            text("SELECT entity_id,status FROM mdm_v2.company_master")
        ).all() == [(identity["entity_id"], "accepted")]
        # The same entity is absent from every other kind's master view.
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.person_master")) == 0


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
                "FROM mdm_v2.company_master_field"
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


def test_migration_033_applies_to_a_populated_store(postgres):
    """CLAUDE.md: test every migration against a genuinely populated table.

    Every other test here migrates an empty schema, so 033's two new indexes are
    built over nothing and the views are created against empty tables. This one
    commits real evidence and a real master record under 023-032 first, then
    applies 033 over it, which is the only order production will ever see.
    """
    from unittest import mock

    import edgar_warehouse.mdm.clean.store as store_module

    admin, app = postgres
    names = list(store_module.CLEAN_MDM_MIGRATIONS)
    cut = next(i for i, name in enumerate(names) if name.startswith("033"))
    through_032 = tuple(names[:cut])
    assert names[cut:] == [n for n in names if n >= "033"], (
        "migrations must be listed in order for a staged upgrade test to mean anything"
    )

    with mock.patch.object(store_module, "CLEAN_MDM_MIGRATIONS", through_032):
        database = core.initialize_database(admin, app)
        company = core.source(key="pop-1", fields={"name": "Acme"})
        person = core.source(key="pop-2", kind="person", fields={"name": "Ada"})
        identity, binding = core.identity_and_binding(company)
        core.apply(
            database,
            1,
            assertions=[company, person],
            identities=[identity],
            decisions=[binding],
        )
        with database.application.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM mdm_v2.assertion")) == 2
            assert (
                conn.scalar(text("SELECT to_regclass('mdm_v2.company_evidence')"))
                is None
            )

    core.migrate(admin, application_role="clean_application")
    with database.application.connect() as conn:
        # migrate() returns a dict that is always truthy, so asserting on it
        # would prove nothing. Ask the store what it recorded instead.
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM mdm_v2.migration "
                    "WHERE name='033_clean_mdm_per_kind_views.sql'"
                )
            )
            == 1
        )
    # The views see evidence and master records written before they existed.
    with database.application.connect() as conn:
        assert [
            r[0]
            for r in conn.execute(
                text("SELECT record_key FROM mdm_v2.company_evidence")
            )
        ] == ["pop-1"]
        assert [
            r[0]
            for r in conn.execute(text("SELECT record_key FROM mdm_v2.person_evidence"))
        ] == ["pop-2"]
        assert conn.execute(
            text("SELECT entity_id FROM mdm_v2.company_master")
        ).all() == [(identity["entity_id"],)]
        assert (
            conn.scalar(text("SELECT count(*) FROM mdm_v2.company_master_field")) == 1
        )
    # The store still commits after the migration, and new evidence shows up.
    later = core.source(key="pop-3", fields={"name": "Beta"})
    core.apply(database, 2, assertions=[later])
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.company_evidence")) == 2
