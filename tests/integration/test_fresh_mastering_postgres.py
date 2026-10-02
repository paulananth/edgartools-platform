"""One fresh PG16 store: approved Company/Person rules and typed links.

This is bounded local qualification, with fixture Rules registration and a
synthetic employment statement. It establishes no live employment fact or
hosted cutover. Existing suites separately exercise real Rules/Bookkeeping/
Change Journal authority, GLEIF links, outages, leases and rollback.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean.consumer import ContractReader
from edgar_warehouse.mdm.clean.evidence import assertion
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.publication import LocalContractSink
from edgar_warehouse.mdm.clean.store import Store, register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.support.fresh_mastering import AS_OF, cohort
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database


def test_fresh_company_person_and_relationship_mastering(database, tmp_path):
    policy, contracts, readings = cohort()
    with database.admin.begin() as conn:
        policy_digest = register_policy(conn, policy)
        for code, contract in contracts.items():
            register_dataset(conn, code, str(uuid4()), contract)
    store = Store(database.application)
    stage = MergeStage(store)
    run_id = str(uuid4())
    command = {"batch_id": "fresh-entities", "run_id": run_id,
               "consumer": "local-qualification", "policy_digest": policy_digest,
               "expected_checkpoint": 0, "checkpoint": 1, "as_of": AS_OF,
               "assertions": readings}
    first = stage.apply(**command)
    assert first["generation"] == 1
    with database.application.connect() as conn:
        actual = dict(conn.execute(text("SELECT kind,count(*) FROM mdm.current_entity GROUP BY kind")).all())
        assert actual == {"company": 2, "person": 2}
        bindings = dict(conn.execute(text("SELECT subject,entity_id::text FROM mdm.stage_record")).all())
    # Bindings use the exact source subjects produced by the adapter.
    person = next(r for r in readings if r["kind"] == "person")
    company = next(r for r in readings if r["kind"] == "company")
    link = assertion(
        source_code="fixture.secondary", record_key="offline-employment",
        publication_key="offline-employment-1", revision=1, effective_at=AS_OF,
        kind="company", fields={}, relationships=[{
            "type": "EMPLOYED_BY", "source_subject": person["subject"],
            "target_subject": company["subject"], "valid_from": AS_OF,
            "valid_to": None, "scope": "synthetic-local-qualification"}],
    )
    second_command = {**command, "batch_id": "fresh-links", "assertions": [link],
                      "expected_checkpoint": 1, "checkpoint": 2}
    second = stage.apply(**second_command)
    with database.application.connect() as conn:
        edges = conn.execute(text("SELECT body FROM mdm.current_record WHERE object_type='relationship'" )).scalars().all()
        assert len(edges) == 1
        assert edges[0]["source_id"] == bindings[person["subject"]]
        assert edges[0]["target_id"] == bindings[company["subject"]]
        assert edges[0]["type"] == "EMPLOYED_BY"
    reader = ContractReader(database.application)
    for record in (person, company):
        found = reader.entity(bindings[record["subject"]])
        assert found["identity"]["kind"] == record["kind"]
        assert found["identity"]["status"] == "accepted"
        assert found["field_provenance"]
    snapshot = reader.snapshot_page("relationship", generation=second["generation"])
    assert snapshot["items"]
    # Immutable publication envelopes are physically read back, for every
    # configured consumer. The journal sink here verifies the contract only;
    # real Journal delivery is covered in test_change_journal_mdm_postgres.
    for consumer in policy["required_consumers"]:
        sink = LocalContractSink(tmp_path / consumer)
        while store.deliver_one(consumer, "local-qualification", sink):
            pass
    assert store.run_status(run_id)["publication_complete"]
    assert stage.apply(**command)["duplicate"]
    assert stage.apply(**second_command)["duplicate"]
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 2
        assert conn.scalar(text("SELECT count(*) FROM mdm.master_entity")) == 4
    # A restricted runtime cannot erase or bypass the newly mastered state.
    for sql in ("DELETE FROM mdm.master_entity", "DELETE FROM mdm.source_reading",
                "CREATE TABLE mdm.bypass(id int)"):
        with pytest.raises(DBAPIError), database.application.begin() as conn:
            conn.execute(text(sql))
