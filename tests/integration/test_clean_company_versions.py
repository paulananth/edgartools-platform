"""The dated Company table is populated and maintained by the Merge Stage."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from edgar_warehouse.mdm.clean.consumer import ContractReader
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Conflict, Store, register_policy
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database


def versions(db):
    with db.application.connect() as conn:
        return conn.execute(
            text("""SELECT from_generation,to_generation,valid_from,valid_to,
                   cik,lei,name,address,status,fields,body
                   FROM mdm.company ORDER BY from_generation""")
        ).mappings().all()


def test_company_versions_close_only_when_master_changes(database):
    address = {"street": "1 Main Street", "city": "Boston", "country": "US"}
    initial = core.source(
        "dated", fields={"name": "Acme", "address": address}, identifiers={"cik": "42"}
    )
    identity, binding = core.identity_and_binding(initial)
    core.apply(database, 1, assertions=[initial], identities=[identity], decisions=[binding])
    first = versions(database)
    assert len(first) == 1
    assert first[0]["cik"] == "42"
    assert first[0]["lei"] is None
    assert first[0]["name"] == "Acme"
    assert first[0]["address"] == address
    assert first[0]["valid_to"] is None

    # Reprojecting the same source state in another committed batch is not a
    # new business version. A corrected source reading is.
    core.apply(database, 2)
    assert len(versions(database)) == 1
    changed = core.source(
        "dated", revision=2, fields={"name": "Acme Holdings"}, identifiers={"cik": "42"}
    )
    core.apply(database, 3, assertions=[changed])
    history = versions(database)
    assert len(history) == 2
    assert history[0]["to_generation"] == 3
    assert history[0]["valid_to"] == history[1]["valid_from"]
    assert history[0]["valid_from"] < history[0]["valid_to"]
    assert history[1]["name"] == "Acme Holdings"
    assert history[1]["address"] == address
    assert history[1]["fields"]["name"]["winner"]["assertion_id"] == changed["assertion_id"]
    cleared = core.source(
        "dated", revision=3, fields={"address": {"op": "clear"}},
        identifiers={"cik": "42"},
    )
    core.apply(database, 4, assertions=[cleared])
    assert versions(database)[-1]["address"] is None
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT to_regclass('mdm.company_master')")) is None
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        database.application.begin() as conn,
    ):
        conn.execute(text("UPDATE mdm.company SET name='forged'"))


def test_alias_and_reversal_read_from_dated_company_authority(database):
    left_source, right_source = core.source("left"), core.source("right")
    left, bind_left = core.identity_and_binding(left_source)
    right, bind_right = core.identity_and_binding(right_source)
    core.apply(
        database, 1,
        assertions=[left_source, right_source],
        identities=[left, right], decisions=[bind_left, bind_right],
    )
    merge = core.decision(
        "merge", actor="steward", reason="reviewed", at="2026-02-01T00:00:00Z",
        left=left["entity_id"], right=right["entity_id"], survivor=left["entity_id"],
    )
    core.apply(database, 2, decisions=[merge])
    reader = ContractReader(database.application)
    merged = reader.entity(right["entity_id"])
    assert merged["canonical_id"] == left["entity_id"]
    assert merged["identity"]["subjects"] == sorted(
        [left_source["subject"], right_source["subject"]]
    )
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.company WHERE valid_to IS NULL")) == 1
        assert conn.scalar(text("SELECT count(*) FROM mdm.company_alias WHERE valid_to IS NULL")) == 1
    reverse = core.decision(
        "reverse", actor="steward", reason="separate Companies",
        at="2026-03-01T00:00:00Z", target=merge["decision_id"],
    )
    core.apply(database, 3, decisions=[reverse])
    assert reader.entity(right["entity_id"])["canonical_id"] == right["entity_id"]
    assert reader.entity(right["entity_id"], generation=2)["canonical_id"] == left["entity_id"]
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.company WHERE valid_to IS NULL")) == 2
        assert conn.scalar(text("SELECT count(*) FROM mdm.company_alias WHERE valid_to IS NULL")) == 0
    page = reader.snapshot_page("entity", generation=2)
    assert {item["object_id"] for item in page["items"]} == {
        left["entity_id"], right["entity_id"]
    }
    assert next(i for i in page["items"] if i["object_id"] == right["entity_id"])["body"]["status"] == "alias"


def test_company_fill_rule_refuses_an_unlisted_arriving_source(database):
    with database.admin.begin() as conn:
        policy = register_policy(
            conn,
            {
                "version": "typo-probe",
                "required_consumers": ["export", "graph"],
                "automatic_rules": [],
                "kinds": {
                    "company": {
                        "version": "1",
                        "defaults": {"sources": ["fixture.primary", "fixture.typo"]},
                    }
                },
            },
        )
    incoming = core.source("new", source_code="fixture.secondary")
    with pytest.raises(Conflict, match="no source priority for: fixture.secondary"):
        MergeStage(Store(database.application)).apply(
            batch_id="bad-company-source",
            run_id=str(uuid4()),
            policy_digest=policy,
            consumer="fixture",
            expected_checkpoint=0,
            checkpoint=1,
            as_of=core.AS_OF,
            assertions=[incoming],
        )
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 0
