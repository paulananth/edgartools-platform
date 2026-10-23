"""Lookup pointers share atomic saves without extra business versions or deliveries."""

from dataclasses import replace
import json

import pytest
from sqlalchemy import event, select, text, update
from sqlalchemy.exc import DBAPIError

from tests.storage_adapters.test_prepared_effects import assert_index_lookup, batch, count


@pytest.fixture
def lookup_store(adapters, storage_api):
    owner, runtime, role = adapters
    original = batch(storage_api)
    lease = runtime.claim(original.scope, "writer")
    runtime.apply(original, lease)
    with owner.engine.connect() as conn:
        baseline = [dict(row) for row in conn.execute(select(owner.tables["migration"])).mappings()]
    installed = storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=3)
    assert installed["initialized"] and installed["migration"] == 3
    assert not storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=3)["initialized"]
    owner = storage_api.Adapter(owner.engine, prefix=owner.prefix, protocol=3)
    runtime = storage_api.Adapter(runtime.engine, prefix=runtime.prefix, protocol=3)
    assert runtime.apply(original, lease)["duplicate"]
    with owner.engine.connect() as conn:
        assert [dict(row) for row in conn.execute(select(owner.tables["migration"]).where(owner.tables["migration"].c.version == 1)).mappings()] == baseline
    request = replace(original, batch="lookup-one", expected_generation=1,
                      expected_checkpoint=1, checkpoint=2, objects=(), evidence=(),
                      indexes=(storage_api.IndexChange("records-by-subject/invented", "reading-one", {"reading": "reading-one"}),))
    return owner, runtime, lease, request


def test_lookup_and_new_evidence_do_not_publish_unchanged_business_results(lookup_store, storage_api):
    owner, runtime, lease, request = lookup_store
    before = {name: count(owner, name) for name in ("current", "history", "outbox")}
    request = replace(request, evidence=(storage_api.Effect("reading", "reading-two", b'{"amount":100000000000000000000001.0000}'),))
    receipt = runtime.apply(request, lease)
    assert not receipt["changed"] and receipt["generation"] == receipt["checkpoint"] == 2
    assert {name: count(owner, name) for name in before} == before
    assert count(owner, "lookup") == 1 and count(owner, "evidence") == 2
    actual = runtime.read([("records-by-subject/invented", "reading-one")], lookup=True)
    assert actual[("records-by-subject/invented", "reading-one")]["body"] == b'{"reading":"reading-one"}'
    assert runtime.apply(request, lease)["duplicate"]
    assert count(owner, "lookup") == 1 and count(owner, "history") == before["history"]
    statement = runtime.lookup_statement([("records-by-subject/invented", "reading-one")], lookup=True)
    # Query execution above uses the restricted role. Plan inspection uses the
    # owner because SQL Server intentionally withholds SHOWPLAN from workers.
    assert_index_lookup(owner.engine, statement, runtime.tables["lookup"].name)
    assert_index_lookup(owner.engine, runtime.type_statement("records-by-subject/invented", lookup=True), runtime.tables["lookup"].name)
    assert list(runtime.iter_type("records-by-subject/invented", lookup=True))[0][0] == ("records-by-subject/invented", "reading-one")


def test_lookup_update_and_removal_obey_expected_versions(lookup_store, storage_api):
    owner, runtime, lease, request = lookup_store
    runtime.apply(request, lease)
    key = (request.indexes[0].type, request.indexes[0].id)
    changed = replace(request, batch="lookup-two", expected_generation=2, expected_checkpoint=2, checkpoint=3,
                      indexes=(replace(request.indexes[0], body={"reading": "reading-two"}, expected_version=1),))
    assert not runtime.apply(changed, lease)["changed"]
    assert runtime.read([key], lookup=True)[key]["version"] == 2
    removed = replace(changed, batch="lookup-three", expected_generation=3, expected_checkpoint=3, checkpoint=4,
                      indexes=(replace(changed.indexes[0], expected_version=2, removed=True),))
    assert not runtime.apply(removed, lease)["changed"]
    assert runtime.read([key], lookup=True) == {} and list(runtime.iter_type(key[0], lookup=True)) == []
    assert count(owner, "history") == 3 and count(owner, "outbox") == 2


def test_stale_lookup_and_absent_lookup_proposals_roll_back(lookup_store, storage_api):
    owner, runtime, lease, request = lookup_store
    runtime.apply(request, lease)
    stale_generation = replace(request, batch="overtaken", objects=(storage_api.Effect("master", "new", {"result": 1}),), indexes=())
    with pytest.raises(storage_api.AdapterError, match="stale_generation"):
        runtime.apply(stale_generation, lease)
    stale_version = replace(stale_generation, expected_generation=2, expected_checkpoint=2, checkpoint=3,
                            indexes=(replace(request.indexes[0], body={"different": True}),))
    with pytest.raises(storage_api.AdapterError, match="stale_index_version"):
        runtime.apply(stale_version, lease)
    assert runtime.generation() == runtime.checkpoint(request.scope) == 2
    assert runtime.read([("master", "new")]) == {}
    assert count(owner, "batch") == 2 and count(owner, "history") == 3


def test_runtime_cannot_write_lookup_rows_directly(lookup_store):
    owner, runtime, lease, request = lookup_store
    runtime.apply(request, lease)
    with pytest.raises(DBAPIError):
        with runtime.engine.begin() as conn:
            conn.execute(update(runtime.tables["lookup"]).values(version=7))
    assert runtime.read([(request.indexes[0].type, request.indexes[0].id)], lookup=True)[(request.indexes[0].type, request.indexes[0].id)]["version"] == 1


def test_permission_failure_on_ready_store_is_not_reported_as_pending(lookup_store, storage_api):
    owner, runtime, _, _ = lookup_store
    name = runtime.routines["claim"][0]
    role = runtime.engine.url.username
    quoted = owner.engine.dialect.identifier_preparer.quote(role)
    with owner.engine.begin() as conn:
        if owner.engine.dialect.name == "mysql":
            conn.execute(text(f"REVOKE EXECUTE ON PROCEDURE {name} FROM :role@'%'"), {"role": role})
        elif owner.engine.dialect.name == "postgresql":
            conn.exec_driver_sql(f"REVOKE EXECUTE ON FUNCTION {name}(text) FROM {quoted}")
        else:
            conn.exec_driver_sql(f"REVOKE EXECUTE ON OBJECT::{name} FROM {quoted}")
    with pytest.raises(storage_api.AdapterError, match="^database_operation_failed$"):
        runtime.claim("ready-store", "writer")


def test_lookup_failure_rolls_back_business_history_and_publication(lookup_store, storage_api):
    owner, runtime, lease, request = lookup_store
    dialect = owner.engine.dialect
    quote = dialect.identifier_preparer.quote
    table = dialect.identifier_preparer.format_table(owner.tables["lookup"])
    trigger_name = owner.prefix + "_lookup_failure"
    trigger = f"{quote(owner.schema)}.{quote(trigger_name)}"
    function = f"{quote(owner.schema)}.{quote(owner.prefix + '_lookup_failure_check')}"
    with owner.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if dialect.name == "postgresql":
            conn.execute(text(f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture_lookup_failure'; END $$"))
            conn.execute(text(f"CREATE TRIGGER {quote(trigger_name)} BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION {function}()"))
        elif dialect.name == "mysql":
            conn.execute(text(f"CREATE TRIGGER {trigger} BEFORE INSERT ON {table} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture_lookup_failure'"))
        else:
            conn.execute(text(f"CREATE TRIGGER {trigger} ON {table} AFTER INSERT AS BEGIN THROW 50002,'fixture_lookup_failure',1; END"))
    failing = replace(request, objects=(storage_api.Effect("master", "new", {"result": 1}),),
                      evidence=(storage_api.Effect("reading", "new", {"result": 1}),))
    try:
        with pytest.raises(storage_api.AdapterError, match="database_operation_failed"):
            runtime.apply(failing, lease)
        assert runtime.generation() == runtime.checkpoint(request.scope) == 1
        assert count(owner, "batch") == 1 and count(owner, "history") == 3
        assert count(owner, "outbox") == 2 and count(owner, "evidence") == 1
        assert count(owner, "lookup") == 0 and runtime.read([("master", "new")]) == {}
    finally:
        with owner.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            if dialect.name == "postgresql":
                conn.execute(text(f"DROP TRIGGER {quote(trigger_name)} ON {table}"))
                conn.execute(text(f"DROP FUNCTION {function}"))
            else:
                conn.execute(text(f"DROP TRIGGER {trigger}"))
    assert runtime.apply(failing, lease)["changed"]


def test_interrupted_lookup_upgrade_refuses_writes_and_recovers_populated_state(adapters, storage_api):
    owner, runtime, role = adapters
    original = batch(storage_api)
    lease = runtime.claim(original.scope, "writer")
    runtime.apply(original, lease)
    interrupted = False

    def fail_new_capability(conn, cursor, statement, parameters, context, executemany):
        nonlocal interrupted
        if not interrupted and "CREATE" in statement and "_lookup" in statement and ("PROCEDURE" in statement or "FUNCTION" in statement):
            interrupted = True
            raise RuntimeError("fixture_interrupted_lookup_upgrade")

    event.listen(owner.engine, "before_cursor_execute", fail_new_capability)
    try:
        with pytest.raises(RuntimeError, match="fixture_interrupted_lookup_upgrade"):
            storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=3)
    finally:
        event.remove(owner.engine, "before_cursor_execute", fail_new_capability)
    assert interrupted
    for caller in (runtime, storage_api.Adapter(runtime.engine, prefix=runtime.prefix, protocol=3)):
        with pytest.raises(storage_api.AdapterError, match="storage_not_initialized"):
            caller.claim("pending", "writer")
    assert count(owner, "batch") == 1 and count(owner, "history") == 3
    assert storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=3)["initialized"]
    resumed = storage_api.Adapter(runtime.engine, prefix=runtime.prefix, protocol=3)
    assert resumed.apply(original, lease)["duplicate"]
    request = replace(original, batch="after-lookup-upgrade", expected_generation=1, expected_checkpoint=1, checkpoint=2,
                      objects=(), evidence=(), indexes=(storage_api.IndexChange("lookup/invented", "one", {"record": "one"}),))
    assert not resumed.apply(request, lease)["changed"]
    assert resumed.read([("lookup/invented", "one")], lookup=True)


def test_retained_readings_and_decisions_are_retrieved_through_their_references(lookup_store, storage_api):
    from edgar_warehouse.mdm.clean.evidence import assertion, decision, subject_key
    from edgar_warehouse.rules.source_engine import prepare_record_history
    from edgar_warehouse.mdm.clean.record_reads import read_affected_records

    owner, runtime, lease, request = lookup_store
    at = "2026-01-01T00:00:00+00:00"
    target = subject_key("fixture.employers", "one")
    first = assertion(source_code="fixture.history", record_key="one", publication_key="first",
                      revision=1, effective_at=at, kind="person", fields={"amount": 10**80})
    second = assertion(source_code="fixture.history", record_key="one", publication_key="second",
                       revision=2, effective_at=at, kind="person", fields={"amount": 10**80 + 1},
                       relationships=[{"type": "EMPLOYED_BY", "target_subject": target, "on": at}])
    identity = {"entity_id": "00000000-0000-0000-0000-000000000001", "kind": "person", "published_at": at}
    bind = decision("bind", actor="fixture", reason="reviewed", at=at, subject=first["subject"],
                    entity_id=identity["entity_id"], evidence=[first["assertion_id"]])
    revoke = decision("revoke", actor="fixture", reason="corrected", at="2026-01-02T00:00:00+00:00",
                      target=bind["decision_id"], subject=first["subject"], entity_id=identity["entity_id"])
    inputs = {"readings": [second, first], "decisions": [bind, revoke], "identities": [identity]}
    evidence, indexes = prepare_record_history(inputs)
    prepared = replace(request, evidence=tuple(storage_api.Effect(entry["type"], entry["id"], entry["body_json"]) for entry in evidence),
                       indexes=tuple(storage_api.IndexChange(entry["type"], entry["id"], entry["body_json"]) for entry in indexes))
    assert not runtime.apply(prepared, lease)["changed"]

    def references(name, key):
        # This is the documented opaque index identity, not a second rule.
        bucket = "lookup/" + name + "/" + json.dumps([key], ensure_ascii=False, separators=(",", ":"))
        return [json.loads(record["body"]) for _, record in runtime.iter_type(bucket, lookup=True)]

    readings = references("record_readings", first["subject"])
    assert {entry["id"] for entry in readings} == {first["assertion_id"], second["assertion_id"]}
    assert {entry["id"] for entry in references("related_readings", target)} == {second["assertion_id"]}
    assert {entry["id"] for entry in references("related_decisions", bind["decision_id"])} == {bind["decision_id"], revoke["decision_id"]}
    retained = runtime.read([(entry["type"], entry["id"]) for entry in readings], immutable=True)
    assert {json.loads(body["body"])["fields"]["amount"]["value"] for body in retained.values()} == {10**80, 10**80 + 1}
    assert runtime.read([("identity", identity["entity_id"])], immutable=True)
    assert count(owner, "history") == 3 and count(owner, "outbox") == 2
    frame = read_affected_records(runtime, [second], [])
    assert frame["generation"] == 2 and frame["subjects"] == {first["subject"]}
    assert set(frame["readings"]) == {first["assertion_id"], second["assertion_id"]}
    assert set(frame["decisions"]) == {bind["decision_id"], revoke["decision_id"]}
    assert frame["identities"] == [identity]
    assert target not in frame["subjects"]  # Plain link ends do not expand identity scope.
    buckets = {entry["type"] for entry in indexes}
    assert runtime.read_lookup_groups(sorted(buckets))
    assert_index_lookup(owner.engine, runtime.lookup_groups_statement(sorted(buckets)), runtime.tables["lookup"].name)
    with pytest.raises(ValueError, match="contradictory content"):
        prepare_record_history({**inputs, "readings": [first, {**first, "fields": {}}]})



def test_native_candidate_routes_reindex_without_business_versions(lookup_store, storage_api):
    from edgar_warehouse.mdm.clean.evidence import assertion
    from edgar_warehouse.rules.source_engine import prepare_record_lookups, prepare_record_history
    from edgar_warehouse.mdm.clean.record_reads import RecordReader

    owner, runtime, lease, request = lookup_store
    item = assertion(source_code="invented.source",record_key="one",publication_key="first",
        revision=1,effective_at="2026-01-01T00:00:00+00:00",kind="person",fields={"amount":10**80},
        provenance={"matching":{"invented_old":"old-target","invented_new":"new-target"}})
    command = {"readings":[item],"previous":{},"subjects":[item["subject"]], "bindings":{},
        "quarantined":{},"policy":{},"normalizers":{},"batch_id":"lookup-one","occurrences":{},
        "candidate_routes":{"invented-route":["provenance","matching","invented_old"]}}
    current, changes = prepare_record_lookups(command)
    def effects(changes):
        keys = [(change["type"],change["id"]) for change in changes]
        versions = runtime.read(keys,lookup=True)
        return tuple(storage_api.IndexChange(change["type"],change["id"],change["body_json"] or {},
            expected_version=versions.get((change["type"],change["id"]),{}).get("version",0),
            removed=change["removed"]) for change in changes)
    evidence, history_indexes = prepare_record_history({"readings":[item],"decisions":[],"identities":[]})
    initial = replace(request,indexes=effects(changes + [{**entry,"removed":False} for entry in history_indexes]),
        evidence=tuple(storage_api.Effect(entry["type"],entry["id"],entry["body_json"]) for entry in evidence))
    before = {name:count(owner,name) for name in ("current","history","outbox")}
    assert not runtime.apply(initial,lease)["changed"]
    old = 'lookup/name_candidates/["invented.source","invented-route","old-target"]'
    new = 'lookup/name_candidates/["invented.source","invented-route","new-target"]'
    assert len(runtime.read_lookup_groups([old])) == 1
    reader = RecordReader(runtime,routes=command["candidate_routes"])
    assert reader.candidates("invented.source","invented-route",["old-target"]) == [item]
    assert reader.candidates("invented.source","invented-route",["missing"]) == []
    corrected, changes = prepare_record_lookups({**command,"previous":current,
        "candidate_routes":{"invented-route":["provenance","matching","invented_new"]}})
    upgrade = replace(initial,batch="route-upgrade",expected_generation=2,expected_checkpoint=2,
        checkpoint=3,indexes=effects(changes))
    assert not runtime.apply(upgrade,lease)["changed"]
    assert runtime.apply(upgrade,lease)["duplicate"]
    assert runtime.read_lookup_groups([old]) == {}
    assert len(runtime.read_lookup_groups([new])) == 1
    reader = RecordReader(runtime,routes={"invented-route":["provenance","matching","invented_new"]})
    assert reader.candidates("invented.source","invented-route",["old-target"]) == []
    assert reader.candidates("invented.source","invented-route",["new-target"]) == [item]
    assert {name:count(owner,name) for name in before} == before
    assert corrected[item["subject"]]["assertion_id"] == item["assertion_id"]
    assert corrected[item["subject"]]["batch_id"] == "lookup-one"
    again, changes = prepare_record_lookups({**command,"previous":corrected,
        "candidate_routes":{"invented-route":["provenance","matching","invented_new"]}})
    assert again == corrected and changes == []
    assert_index_lookup(owner.engine,runtime.lookup_groups_statement([new]),runtime.tables["lookup"].name)



def test_record_reader_serves_binding_and_correction_from_native_indexes(lookup_store,storage_api):
    from edgar_warehouse.mdm.clean import binding,correction,matching
    from edgar_warehouse.mdm.clean.evidence import assertion,decision
    from edgar_warehouse.mdm.clean.record_reads import RecordReader
    from edgar_warehouse.rules.source_engine import prepare_record_history,prepare_record_lookups

    owner,runtime,lease,request = lookup_store
    at = "2026-01-01T00:00:00+00:00"
    identity = "00000000-0000-0000-0000-000000000001"
    survivor = "00000000-0000-0000-0000-000000000002"
    item = assertion(source_code="invented.source",record_key="one",publication_key="first",
        revision=1,effective_at=at,kind="person",fields={"amount":10**80},identifiers={"invented-id":"target"})
    bind = decision("bind",actor="fixture",reason="reviewed",at=at,
        subject=item["subject"],entity_id=identity)
    quarantine = decision("quarantine",actor="fixture",reason="reviewed",at=at,
        subject=item["subject"],policy="invented-policy")
    routes = {"invented-route":["identifiers","invented-id"]}
    _,pointers = prepare_record_lookups({"readings":[item],"previous":{},"subjects":[item["subject"]],
        "bindings":{item["subject"]:identity},"quarantined":{},"policy":{},"normalizers":{},
        "batch_id":"lookup-one","occurrences":{},"candidate_routes":routes})
    evidence,indexes = prepare_record_history({"readings":[item],"decisions":[bind,quarantine],"identities":[]})
    def saved(entries):
        return tuple(storage_api.IndexChange(e["type"],e["id"],e["body_json"]) for e in entries)
    initial = replace(request,
        objects=(storage_api.Effect("entity",identity,{"entity_id":identity,"canonical_id":survivor,"status":"review"}),),
        evidence=tuple(storage_api.Effect(e["type"],e["id"],e["body_json"]) for e in evidence),
        indexes=saved(pointers+indexes))
    runtime.apply(initial,lease)
    reader = RecordReader(runtime,routes=routes)
    assert binding.bound(reader,{item["subject"],"absent"}) == {item["subject"]:identity}
    assert binding.survivors(reader,{identity,"absent"}) == {identity:survivor}
    assert binding.in_review(reader,{identity,"absent"}) == {identity}
    assert reader.members({identity}) == {item["subject"]}
    assert correction.readings(reader,{item["subject"]}) == [item]
    assert correction.quarantined(reader,{item["subject"]},[]) == {item["subject"]}
    revoke_bind = decision("revoke",actor="fixture",reason="corrected",at=at,target=bind["decision_id"],
        subject=item["subject"],rule_id="invented-rule",rule_version=1)
    revoke_quarantine = decision("revoke",actor="fixture",reason="corrected",at=at,
        target=quarantine["decision_id"],subject=item["subject"])
    assert correction.released(reader,[revoke_bind]) == {item["subject"]}
    assert correction.lifted(reader,[revoke_quarantine]) == {item["subject"]}
    assert correction.quarantined(reader,{item["subject"]},[revoke_quarantine]) == set()
    assert matching._stored(reader,"invented.source",tuple(routes["invented-route"]),["target"]) == [item]
    assert dict(matching._held_identifiers(reader,"invented.source","invented-id",{identity},set())) == {identity:{"target"}}
    assert not matching._held_identifiers(reader,"invented.source","invented-id",{identity},{item["subject"]})

    evidence,indexes = prepare_record_history({"readings":[],"decisions":[revoke_bind,revoke_quarantine],"identities":[]})
    later = replace(initial,batch="corrections",expected_generation=2,expected_checkpoint=2,checkpoint=3,objects=(),
        evidence=tuple(storage_api.Effect(e["type"],e["id"],e["body_json"]) for e in evidence),indexes=saved(indexes))
    runtime.apply(later,lease)
    assert correction.quarantined(reader,{item["subject"]},[]) == set()
    assert correction.refused(reader,{item["subject"]},[]) == {(item["subject"],"invented-rule",1)}
    assert correction.refused(reader,{"absent"},[]) == set()
    assert runtime.apply(later,lease)["duplicate"]
