"""Real PG16: the latest-only Stage, written beside the history (ticket 10).

`mdm_v2.stage_record` keeps one row per source record: the winning reading,
the snapshot every reading up to it resolves to, and the bronze object it was
delivered in. Nothing reads it yet, so each test holds it equal to what
`survivorship.current_claims` reads from the full retained history.
"""

from __future__ import annotations

import json
import random
from unittest import mock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from edgar_warehouse.mdm.clean import store as store_module
from edgar_warehouse.mdm.clean.evidence import assertion
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.mdm.clean.survivorship import current_claims
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database

# Every reading is in force: the Stage keeps the winner whatever its effective
# time, and refusing a future one waits for slice 4.
EVER = "9999-12-31T00:00:00Z"
SHA = "a" * 64


def stage(db) -> dict[tuple[str, str], dict]:
    with db.application.connect() as conn:
        found = (
            conn.execute(
                text("""SELECT source_code,record_key,subject,kind,revision,
                   mapping_version,assertion_id,snapshot,bronze,batch_id
                   FROM mdm_v2.stage_record""")
            )
            .mappings()
            .all()
        )
    return {(r["source_code"], r["record_key"]): dict(r) for r in found}


def history(db) -> dict[str, dict]:
    with db.application.connect() as conn:
        bodies = conn.scalars(text("SELECT body FROM mdm_v2.assertion")).all()
    return current_claims(list(bodies), EVER, set())


def assert_parity(db) -> None:
    rows = stage(db)
    claims = history(db)
    assert {r["subject"]: r["snapshot"] for r in rows.values()} == claims


def reading(key, revision, fields, **kw):
    return core.source(key, revision=revision, fields=fields, **kw)


def test_every_stage_row_equals_the_history_read(database):
    rng = random.Random("ticket-10-slice-1")
    names = ["Acme", "Acme Holdings", "Acme plc"]
    plans = []
    for n in range(6):
        for revision in range(1, rng.randint(2, 5) + 1):
            fields = {}
            for field in ("name", "sic", "description", "address"):
                roll = rng.random()
                if revision == 1 and field == "name":
                    fields[field] = rng.choice(names)
                elif roll < 0.3:
                    fields[field] = (
                        {"street": f"{revision} Main", "country": "US"}
                        if field == "address"
                        else f"{field}-{revision}"
                    )
                elif roll < 0.45:
                    fields[field] = {"op": "clear"}
                elif roll < 0.55:
                    fields[field] = {"op": "retract"}
                elif roll < 0.75:
                    fields[field] = {"op": "unknown"}
            plans.append(
                reading(f"r{n}", revision, fields, identifiers={"cik": str(100 + n)})
            )
    ops = {item["op"] for a in plans for item in a["fields"].values()}
    assert ops == {"value", "clear", "retract", "unknown"}
    # Ascending per record, interleaved across records and batches.
    plans.sort(key=lambda a: (a["revision"], a["record_key"]))
    for batch, start in enumerate(range(0, len(plans), 4), start=1):
        core.apply(database, batch, assertions=plans[start : start + 4])
    assert len(stage(database)) == 6
    assert_parity(database)


def test_a_sparse_patch_erases_nothing_it_does_not_name(database):
    core.apply(
        database, 1, assertions=[reading("p", 1, {"name": "Acme", "sic": "3571"})]
    )
    core.apply(database, 2, assertions=[reading("p", 2, {"name": "Acme Inc"})])
    row = stage(database)[("fixture.primary", "p")]
    assert row["revision"] == 2
    assert row["snapshot"]["fields"]["sic"]["value"] == "3571"
    assert row["snapshot"]["fields"]["name"]["value"] == "Acme Inc"
    core.apply(database, 3, assertions=[reading("p", 3, {"sic": {"op": "retract"}})])
    assert "sic" not in stage(database)[("fixture.primary", "p")]["snapshot"]["fields"]
    assert_parity(database)


def test_a_late_older_delivery_or_a_duplicate_keeps_the_row(database):
    newer = reading("late", 2, {"name": "Newer"})
    core.apply(database, 1, assertions=[newer])
    before = stage(database)[("fixture.primary", "late")]
    core.apply(
        database, 2, assertions=[reading("late", 1, {"name": "Older", "sic": "1"})]
    )
    core.apply(database, 3, assertions=[newer])
    after = stage(database)[("fixture.primary", "late")]
    assert after == before
    assert after["snapshot"]["fields"] == {
        "name": {
            "op": "value",
            "value": "Newer",
            "assertion_id": newer["assertion_id"],
            "source_code": "fixture.primary",
            "record_key": "late",
            "effective_at": newer["effective_at"],
        }
    }


def test_two_readings_at_one_revision_are_refused(database):
    first = reading("twice", 1, {"name": "One"})
    core.apply(database, 1, assertions=[first])
    other = assertion(
        **{
            **{
                k: first[k]
                for k in (
                    "source_code",
                    "record_key",
                    "revision",
                    "effective_at",
                    "kind",
                )
            },
            "publication_key": "another",
            "fields": {"name": "Two"},
        }
    )
    with pytest.raises((Conflict, DBAPIError), match="contradictory publications"):
        core.apply(database, 2, assertions=[other])
    assert (
        stage(database)[("fixture.primary", "twice")]["assertion_id"]
        == first["assertion_id"]
    )


def test_the_winning_reading_keeps_its_bronze_object(database):
    first = reading("bronze", 1, {"name": "Acme"})
    core.apply(
        database,
        1,
        assertions=[first],
        occurrences=[
            {
                "assertion_id": first["assertion_id"],
                "object": "b/one.json",
                "sha256": SHA,
                "locator": "record:1",
            }
        ],
    )
    assert stage(database)[("fixture.primary", "bronze")]["bronze"] == {
        "object": "b/one.json",
        "sha256": SHA,
        "locator": "record:1",
    }
    second = reading("bronze", 2, {"name": "Acme Inc"})
    core.apply(database, 2, assertions=[second])
    assert stage(database)[("fixture.primary", "bronze")]["bronze"] is None
    third = reading("bronze", 3, {"name": "Acme plc"})
    core.apply(
        database,
        3,
        assertions=[third],
        occurrences=[
            {
                "assertion_id": third["assertion_id"],
                "object": "b/three.json",
                "sha256": "b" * 64,
                "locator": "record:9",
            }
        ],
    )
    assert (
        stage(database)[("fixture.primary", "bronze")]["bronze"]["object"]
        == "b/three.json"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"sha256": "short"},
        {"assertion_id": "not-in-this-batch"},
        {"object": ""},
        {"extra": "field"},
    ],
)
def test_an_invalid_bronze_occurrence_is_refused(database, change):
    first = reading("bad", 1, {"name": "Acme"})
    occurrence = {
        "assertion_id": first["assertion_id"],
        "object": "b/x.json",
        "sha256": SHA,
        "locator": "record:1",
        **change,
    }
    with pytest.raises(Conflict, match="Invalid bronze occurrence"):
        core.apply(database, 1, assertions=[first], occurrences=[occurrence])


def test_the_sql_fold_equals_current_claims_with_profiles(database):
    def profile(role, **fields):
        return {
            "role": role,
            "authority": "RA",
            "registration": "R-1",
            "jurisdiction": "US",
            "valid_from": None,
            "fields": fields,
        }

    readings = [
        assertion(
            source_code="fixture.primary",
            record_key="prof",
            publication_key=f"p{n}",
            revision=n,
            effective_at=None,
            kind="company",
            fields=fields,
            profiles=profiles,
        )
        for n, fields, profiles in (
            (1, {"name": "Acme"}, [profile("issuer", ticker="ACME", exchange="NYSE")]),
            (
                2,
                {"name": {"op": "unknown"}},
                [profile("issuer", ticker=None), profile("lender", rating="A")],
            ),
            (3, {"sic": "1"}, [profile("lender", rating={"op": "retract"})]),
        )
    ]
    snapshot = None
    with database.admin.connect() as conn:
        for a in readings:
            snapshot = conn.scalar(
                text(
                    "SELECT mdm_v2.stage_fold(CAST(:prev AS jsonb), CAST(:a AS jsonb))"
                ),
                {
                    "prev": None if snapshot is None else json.dumps(snapshot),
                    "a": json.dumps(a),
                },
            )
    assert snapshot == current_claims(readings, EVER, set())[readings[0]["subject"]]


def test_the_runtime_role_cannot_write_the_stage(database):
    core.apply(database, 1, assertions=[reading("ro", 1, {"name": "Acme"})])
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        database.application.begin() as conn,
    ):
        conn.execute(text("UPDATE mdm_v2.stage_record SET kind='person'"))


def test_a_populated_store_backfills_the_stage_in_arrival_order(postgres):
    admin, app = postgres
    migrations = store_module.CLEAN_MDM_MIGRATIONS
    before = migrations[: migrations.index("038_clean_mdm_stage_record.sql")]
    with mock.patch.object(store_module, "CLEAN_MDM_MIGRATIONS", before):
        db = core.initialize_database(admin, app)
        core.apply(
            db,
            1,
            assertions=[
                reading("old", 1, {"name": "One", "sic": "1"}),
                reading("kept", 2, {"name": "Kept"}),
            ],
        )
        core.apply(db, 2, assertions=[reading("old", 2, {"name": "Two"})])
        # Delivered after revision 2: it keeps the row, as the trigger would.
        core.apply(db, 3, assertions=[reading("kept", 1, {"name": "Late"})])
        with app.connect() as conn:
            assert (
                conn.scalar(text("SELECT to_regclass('mdm_v2.stage_record')")) is None
            )

    store_module.migrate(admin, application_role="clean_application")
    rows = stage(db)
    assert {
        k[1]: (r["revision"], r["snapshot"]["fields"]["name"]["value"])
        for k, r in rows.items()
    } == {
        "old": (2, "Two"),
        "kept": (2, "Kept"),
    }
    assert rows[("fixture.primary", "old")]["snapshot"]["fields"]["sic"]["value"] == "1"
    assert all(r["bronze"] is None for r in rows.values())
    # The next live commit uses the installed trigger.
    core.apply(db, 4, assertions=[reading("old", 3, {"name": "Three"})])
    assert stage(db)[("fixture.primary", "old")]["revision"] == 3
