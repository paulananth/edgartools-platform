"""Real PG16: who each Stage record is bound to, and its winning reading
(company mastering ticket 10, slice 2a).

The matching rules' lookups move from the full history to
`mdm_v2.stage_record`. Each test below holds a moved reader equal to the query
it replaced, kept here verbatim as the reference, over one seeded history: an
identifier that changes between revisions, an older reading delivered later,
a Name Census entry that changes, and bound and unbound records. The two
intended differences, both where the history read could match a reading that
a later one replaced, each have their own test.
"""

from __future__ import annotations

import json
from collections import defaultdict
from unittest import mock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean import binding, matching
from edgar_warehouse.mdm.clean import store as store_module
from edgar_warehouse.mdm.clean.store import rows
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_identifier_binding import CIK_ISSUED, LEI_CONTRACT

postgres = core.postgres
database = core.database

SEC = "fixture.primary"
GLEIF = "fixture.secondary"
POLICY = {
    "kinds": {"company": {"identifiers": {"cik": CIK_ISSUED, "lei": LEI_CONTRACT}}}
}
L1, L2, L3, L9 = (f"{c * 18}00" for c in "ABCZ")
CIKS = {"0001", "0002", "0003", "0033", "0004", "0005"}


def census(lei):
    return {"matching": {"name_census": {"leis": [[lei, 1]]}}}


def record(key, revision, source_code=SEC, provenance=None, **identifiers):
    return core.source(
        key,
        source_code=source_code,
        revision=revision,
        fields={"name": f"Company {key}"},
        identifiers=identifiers,
        provenance=provenance,
    )


def bind(a, entity_id):
    return core.identity_and_binding(a, entity_id)[1]


def seed(db) -> dict:
    """Four batches; returns the two entities and the records they bind."""
    e1, e2 = str(uuid4()), str(uuid4())
    a1 = record("a", 1, cik="0001", lei=L1, provenance=census(L1))
    g1 = record("g", 1, source_code=GLEIF, lei=L1)
    b1 = record("b", 1, cik="0002")
    identity = {"kind": "company", "published_at": core.AT}
    core.apply(
        db,
        1,
        assertions=[a1, g1, b1],
        identities=[{**identity, "entity_id": e1}],
        decisions=[bind(a1, e1), bind(g1, e1)],
    )
    a2 = record("a", 2, cik="0001", lei=L1, provenance=census(L9))
    c2 = record("c", 2, cik="0003")
    h1 = record("h", 1, source_code=GLEIF, lei=L2)
    core.apply(
        db,
        2,
        assertions=[a2, c2, h1],
        identities=[{**identity, "entity_id": e2}],
        decisions=[bind(c2, e2), bind(h1, e2)],
    )
    # c's revision 1 arrives after its revision 2; d's CIK changes.
    core.apply(
        db, 3, assertions=[record("c", 1, cik="0033"), record("d", 1, cik="0004")]
    )
    core.apply(
        db,
        4,
        assertions=[
            record("d", 2, cik="0005"),
            record("h", 2, source_code=GLEIF, lei=L3),
        ],
    )
    return {
        "e1": e1,
        "e2": e2,
        "subjects": {r["subject"] for r in (a1, g1, b1, c2, h1)},
    }


# The replaced queries, verbatim.


def old_holders(conn, policy, wanted):
    found = defaultdict(dict)
    for namespace, values in sorted(wanted.items()):
        path = f"body->'identifiers'->>'{namespace}'"
        found_rows = rows(
            conn,
            f"""WITH latest AS (
                SELECT DISTINCT ON (a.source_code, a.record_key)
                       a.body->>'subject' AS subject, {path.replace("body", "a.body")} AS value
                FROM mdm_v2.assertion a
                WHERE (a.source_code, a.record_key) IN (
                    SELECT source_code, record_key FROM mdm_v2.assertion
                    WHERE {path} = ANY(:values) AND source_code = ANY(:sources))
                ORDER BY a.source_code, a.record_key, a.revision DESC,
                         a.mapping_version DESC)
            SELECT l.value, d.body->>'entity_id' AS entity_id, i.kind
            FROM latest l
            JOIN mdm_v2.decision d
              ON d.operation='bind' AND d.body->>'subject'=l.subject
            JOIN mdm_v2.identity i ON i.entity_id=(d.body->>'entity_id')::uuid
            WHERE l.value = ANY(:values)""",
            values=sorted(values),
            sources=binding._issuers(policy, namespace),
        )
        merged = binding.survivors(conn, {r["entity_id"] for r in found_rows})
        for row in found_rows:
            key = (namespace, binding._normal(policy, namespace, row["value"]))
            found[key][merged.get(row["entity_id"], row["entity_id"])] = row["kind"]
    return found


OLD_LOOKUPS = {
    "lei": "body->'identifiers'->>'lei'",
    "census_lei": "body->'provenance'->'matching'->'name_census'->'leis'->0->>0",
}


def old_stored(conn, source, lookup, values):
    return [
        r["body"]
        for r in rows(
            conn,
            f"""SELECT DISTINCT ON (source_code, record_key) body
            FROM mdm_v2.assertion
            WHERE source_code = :source AND {OLD_LOOKUPS[lookup]} = ANY(:values)
            ORDER BY source_code, record_key, revision DESC, mapping_version DESC""",
            source=source,
            values=sorted(set(values)),
        )
    ]


def old_bound_subjects(conn, subjects):
    return {
        r["subject"]: r["entity_id"]
        for r in rows(
            conn,
            """SELECT body->>'subject' AS subject, body->>'entity_id' AS entity_id
            FROM mdm_v2.decision
            WHERE operation='bind' AND body->>'subject' = ANY(:subjects)""",
            subjects=sorted(subjects),
        )
    }


def old_held_leis(conn, source, entities):
    held = defaultdict(set)
    for r in rows(
        conn,
        """SELECT DISTINCT d.body->>'entity_id' AS entity_id,
               a.body->'identifiers'->>'lei' AS lei
        FROM mdm_v2.decision d
        JOIN mdm_v2.assertion a ON a.body->>'subject' = d.body->>'subject'
        WHERE d.operation='bind' AND d.body->>'entity_id' = ANY(:entities)
          AND a.source_code = :source
          AND a.body->'identifiers'->>'lei' IS NOT NULL""",
        entities=sorted(entities),
        source=source,
    ):
        held[r["entity_id"]].add(r["lei"])
    return held


def bindings_on_stage(db) -> dict[str, str]:
    """Each bound Stage record's key and the entity it is bound to."""
    with db.application.connect() as conn:
        return dict(
            conn.execute(
                text(
                    "SELECT record_key, entity_id::text FROM mdm_v2.stage_record "
                    "WHERE entity_id IS NOT NULL"
                )
            ).all()
        )


def by_id(bodies):
    return sorted(bodies, key=lambda b: b["assertion_id"])


def test_who_holds_an_identifier_reads_as_before(database):
    seed(database)
    wanted = {"cik": CIKS, "lei": {L1, L2, L3}}
    with database.application.connect() as conn:
        new = binding.holders(conn, POLICY, wanted)
        assert new == old_holders(conn, POLICY, wanted)
    # The late older reading of c and d's earlier CIK hold nothing.
    assert ("cik", "33") not in new and ("cik", "4") not in new
    assert set(new) == {("cik", "1"), ("cik", "3"), ("lei", L1), ("lei", L3)}


def test_the_latest_stored_readings_read_as_before(database):
    seed(database)
    with database.application.connect() as conn:
        for source, lookup, values in (
            (GLEIF, "lei", [L1, L2, L3]),
            (SEC, "lei", [L1]),
            (SEC, "census_lei", [L1, L9]),
        ):
            new = matching._stored(conn, source, lookup, values)
            assert by_id(new) == by_id(old_stored(conn, source, lookup, values))
        (latest,) = matching._stored(conn, SEC, "census_lei", [L1, L9])
        assert latest["revision"] == 2


def test_a_replaced_census_entry_no_longer_matches(database):
    seed(database)
    with database.application.connect() as conn:
        new = matching._stored(conn, SEC, "census_lei", [L1])
        (old,) = old_stored(conn, SEC, "census_lei", [L1])
    # An intended difference: the history read took the latest reading that
    # matched, so a's revision 1 still matched on the census LEI its revision
    # 2 replaced. The Stage matches the current reading only.
    assert old["revision"] == 1
    assert new == []


def test_which_records_are_bound_reads_as_before(database):
    seeded = seed(database)
    everyone = seeded["subjects"] | {"nobody"}
    with database.application.connect() as conn:
        assert binding.bound(conn, everyone) == old_bound_subjects(conn, everyone)
        # The in-batch half is unchanged; the stored half now reads the Stage.
        assert matching._bindings(conn, everyone, []) == {
            s: {e} for s, e in old_bound_subjects(conn, everyone).items()
        }
    assert bindings_on_stage(database) == {
        "a": seeded["e1"],
        "g": seeded["e1"],
        "c": seeded["e2"],
        "h": seeded["e2"],
    }


def test_the_leis_a_company_holds_are_its_records_latest(database):
    seeded = seed(database)
    entities = {seeded["e1"], seeded["e2"]}
    with database.application.connect() as conn:
        new = matching._held_leis(conn, GLEIF, entities)
        old = old_held_leis(conn, GLEIF, entities)
    # An intended difference: h's LEI changed from L2 to L3. The history read
    # kept both; the Stage keeps the latest, as `holders` always did. A GLEIF
    # level 1 record's key is its LEI, so real GLEIF data never differs here.
    assert new == {seeded["e1"]: {L1}, seeded["e2"]: {L3}}
    assert old == {seeded["e1"]: {L1}, seeded["e2"]: {L2, L3}}


def test_the_winning_reading_is_kept_whole(database):
    seed(database)
    with database.application.connect() as conn:
        found = conn.execute(
            text("SELECT record_key, reading, assertion_id FROM mdm_v2.stage_record")
        ).all()
        latest = {
            r["record_key"]: r["body"]
            for r in rows(
                conn,
                """SELECT DISTINCT ON (source_code, record_key) record_key, body
                FROM mdm_v2.assertion
                ORDER BY source_code, record_key, revision DESC, mapping_version DESC""",
            )
        }
    assert {k: reading for k, reading, _ in found} == latest
    assert all(reading["assertion_id"] == aid for _, reading, aid in found)


def call(database, sql, **params):
    with database.admin.begin() as conn:
        conn.execute(text(sql), {k: json.dumps(v) for k, v in params.items()})


def test_a_binding_never_moves_on_the_stage(database):
    """Binding again to the same entity is a no-op; another entity is refused."""
    seeded = seed(database)
    with database.application.connect() as conn:
        (subject,) = conn.scalars(
            text("SELECT subject FROM mdm_v2.stage_record WHERE record_key='a'")
        ).all()
    same = {"subject": subject, "entity_id": seeded["e1"]}
    call(database, "SELECT mdm_v2.record_binding(CAST(:d AS jsonb))", d=same)
    moved = {"subject": subject, "entity_id": seeded["e2"]}
    with pytest.raises(DBAPIError, match="requires a correction contract"):
        call(database, "SELECT mdm_v2.record_binding(CAST(:d AS jsonb))", d=moved)
    stray = {"subject": "no-such-record", "entity_id": seeded["e1"]}
    with pytest.raises(DBAPIError, match="names no Stage record"):
        call(database, "SELECT mdm_v2.record_binding(CAST(:d AS jsonb))", d=stray)


def test_a_populated_store_backfills_bindings_and_readings(postgres):
    admin, app = postgres
    migrations = store_module.CLEAN_MDM_MIGRATIONS
    before = migrations[: migrations.index("039_clean_mdm_stage_binding.sql")]
    with mock.patch.object(store_module, "CLEAN_MDM_MIGRATIONS", before):
        db = core.initialize_database(admin, app)
        seeded = seed(db)
    store_module.migrate(admin, application_role="clean_application")
    bound_now = bindings_on_stage(db)
    with db.application.connect() as conn:
        wanted = {"cik": CIKS, "lei": {L1, L2, L3}}
        assert binding.holders(conn, POLICY, wanted) == old_holders(
            conn, POLICY, wanted
        )
        assert (
            conn.scalar(
                text("SELECT count(*) FROM mdm_v2.stage_record WHERE reading IS NULL")
            )
            == 0
        )
    assert bound_now == {
        "a": seeded["e1"],
        "g": seeded["e1"],
        "c": seeded["e2"],
        "h": seeded["e2"],
    }
    # The next live bind is kept through the evidence wrapper.
    k = record("k", 1, source_code=GLEIF, lei=L1)
    core.apply(db, 5, assertions=[k], decisions=[bind(k, seeded["e1"])])
    with db.application.connect() as conn:
        assert binding.bound(conn, {k["subject"]}) == {k["subject"]: seeded["e1"]}
