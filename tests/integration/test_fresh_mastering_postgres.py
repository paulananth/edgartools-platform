"""One fresh PG16 store: approved Company/Person rules and a typed link.

This is bounded local qualification, with fixture Rules registration. The link
is the one type the approved rules allow today, a GLEIF accounting parent
between two Companies, read by the real GLEIF reader; the parent record itself
is synthetic, no real GLEIF fact. Person links wait for their relationship rules (platform
validation 06, step 2). It establishes no hosted cutover. Existing suites separately exercise real Rules/Bookkeeping/
Change Journal authority, GLEIF links, outages, leases and rollback.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean.consumer import ContractReader
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.publication import LocalContractSink
from edgar_warehouse.mdm.clean.store import Store, register_policy
from tests.integration import test_clean_mdm_postgres as core
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract
from tests.support.fresh_mastering import AS_OF, cohort, gleif_cohort
from tests.support.rules_authority import register_dataset

postgres = core.postgres
database = core.database


def test_fresh_company_person_and_relationship_mastering(database, tmp_path):
    policy, contracts, readings = cohort()
    level1, link = gleif_cohort()
    gleif = {f"gleif.{m}.v1": dataset_contract(m) for m in ("level1", "relationships")}
    with database.admin.begin() as conn:
        policy_digest = register_policy(conn, policy)
        for code, contract in {**contracts, **gleif}.items():
            register_dataset(conn, code, str(uuid4()), contract)
    store = Store(database.application)
    stage = MergeStage(store)
    run_id = str(uuid4())
    command = {"batch_id": "fresh-entities", "run_id": run_id,
               "consumer": "local-qualification", "policy_digest": policy_digest,
               "expected_checkpoint": 0, "checkpoint": 1, "as_of": AS_OF,
               "assertions": [*readings, *level1]}
    first = stage.apply(**command)
    assert first["generation"] == 1
    with database.application.connect() as conn:
        actual = dict(conn.execute(text("SELECT kind,count(*) FROM mdm.current_entity GROUP BY kind")).all())
        assert actual == {"company": 2, "person": 2}
        bindings = dict(conn.execute(text("SELECT subject,entity_id::text FROM mdm.stage_record")).all())
    # Bindings use the exact source subjects produced by the adapter. The two
    # GLEIF records wait for a binding: no approved rule joins them to SEC.
    person = next(r for r in readings if r["kind"] == "person")
    apple, microsoft = (r for r in readings if r["kind"] == "company")
    assert (apple["fields"]["name"]["value"], microsoft["fields"]["name"]["value"]) == ("Apple Inc.", "MICROSOFT CORP")
    child, owner = level1
    assert bindings[child["subject"]] is None and bindings[owner["subject"]] is None
    # A steward binds each GLEIF record to its SEC Company; the link then
    # resolves to those canonical Companies.
    steward = [core.identity_and_binding(g, bindings[sec["subject"]])[1]
               for g, sec in ((child, apple), (owner, microsoft))]
    second_command = {**command, "batch_id": "fresh-links", "assertions": [link],
                      "decisions": steward, "expected_checkpoint": 1, "checkpoint": 2}
    second = stage.apply(**second_command)
    with database.application.connect() as conn:
        actual = dict(conn.execute(text("SELECT kind,count(*) FROM mdm.current_entity GROUP BY kind")).all())
        assert actual == {"company": 2, "person": 2}
        edges = conn.execute(text("SELECT body FROM mdm.current_record WHERE object_type='relationship'")).scalars().all()
        direct = [e for e in edges if not e.get("derived")]
        assert len(direct) == 1, edges
        assert direct[0]["source_id"] == bindings[apple["subject"]]
        assert direct[0]["target_id"] == bindings[microsoft["subject"]]
        assert direct[0]["type"] == "IS_DIRECTLY_CONSOLIDATED_BY"
        assert sorted(e["type"] for e in edges) == ["CALCULATED_ULTIMATE_PARENT", "IS_DIRECTLY_CONSOLIDATED_BY"]
    reader = ContractReader(database.application)
    for record in (person, apple):
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
