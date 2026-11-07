"""Normal versioned consumer reads after normal restricted-role MDM saves."""

import os
import runpy
from uuid import uuid4

import pytest
from sqlalchemy import event, select

os.environ["READ_ID_CASE"] = "lookup"
case = os.environ["READ_CONSUMER_CASE"]
if case == "review_pages":
    os.environ["READ_CASE"] = "hierarchy"
    g = runpy.run_module("tests.storage_adapters.record_read_scenarios")
    s = {"g": g, "runtime": g["runtime"], "root": g["master"]["entity_id"],
         "primary": g["PRIMARY"], "secondary": g["SECONDARY"]}
else:
    s = runpy.run_module("tests.storage_adapters.master_id_scenarios")
    g = s["g"]

from edgar_warehouse.mdm.consumer import ContractReader
from edgar_warehouse.mdm.evidence import decision
from edgar_warehouse.mdm.store import digest, register_policy
from tests.storage_adapters.test_prepared_effects import assert_index_lookup

runtime, root = s["runtime"], s["root"]
reader = ContractReader(runtime)
try:
    current = reader.entity(root)
    assert current["canonical_id"] == current["identity"]["entity_id"] == root
    assert current["business_hash"] == digest(current["identity"])
    assert current["field_provenance"]["invented_name"]["evidence"]["source_code"] == s["primary"]
    assert current["field_provenance"]["invented_name"]["evidence"]["subject"] == g["holder"]["subject"]
    if case in ("history", "producer"):
        before = current
        reading = g["record"]("one", revision=2, fields={"invented_name": "INVENTED 雪",
                                                       "invented_amount": 10**80 + 1})
        producer = str(uuid4())
        command = {"batch_id": "invented-consumer-update", "run_id": producer,
                   "policy_digest": g["seed_pin"], "consumer": "invented-consumer-proof",
                   "expected_checkpoint": 0, "checkpoint": 1, "as_of": g["AS_OF"],
                   "assertions": [reading]}
        result = s["stage"].apply(**command)
        updated = reader.entity(root)
        assert updated["generation"] == result["generation"]
        assert updated["identity"]["fields"]["invented_amount"]["value"] == 10**80 + 1
        assert updated["identity"]["fields"]["invented_name"]["value"] == "INVENTED 雪"
        assert updated["projection"]["origin_run_id"] == producer
        assert updated["field_provenance"]["invented_amount"]["origin_run_id"] == producer
        assert updated["field_provenance"]["invented_amount"]["evidence"] == reading
        assert reader.entity(root, generation=before["generation"]) == before
        if case == "producer":
            origin = g["normal"].read_origins([("entity", root)])[("entity", root)]["origin"]
            assert origin["run"] == producer and type(origin["recorded_at"]) is int
            assert s["stage"].apply(**{**command, "run_id": str(uuid4())})["duplicate"]
            assert reader.entity(root) == updated
            assert g["normal"].read_origins([("entity", root)])[("entity", root)]["origin"] == origin
            s["stage"].apply(**{**command, "batch_id": "invented-consumer-unchanged",
                "run_id": str(uuid4()), "expected_checkpoint": 1, "checkpoint": 2})
            unchanged = reader.entity(root)
            assert unchanged["generation"] == updated["generation"] + 1
            assert unchanged["projection"] == updated["projection"]
            assert unchanged["identity"] == updated["identity"]
            assert unchanged["field_provenance"] == updated["field_provenance"]
            assert g["normal"].read_origins([("entity", root)])[("entity", root)]["origin"] == origin
    if case == "alias":
        other = s["later_identity"]("later")
        before = reader.entity(other)
        verdict = s["merge"](root, other)
        merged = reader.entity(other)
        assert merged["requested_id"] == other and merged["canonical_id"] == root
        assert merged["identity"] == reader.entity(root)["identity"]
        assert reader.entity(other, generation=before["generation"]) == before
        s["apply"](decisions=[decision("reverse", actor="fixture", reason="invented reversal",
            at="2026-02-02T00:00:00Z", target=verdict["decision_id"])])
        assert reader.entity(other)["canonical_id"] == other
        assert reader.entity(other, generation=merged["generation"]) == merged
    if case == "profile":
        policy = {**g["policy"], "version": "invented-profile-reader",
                  "profile_fields": {"invented-role": {"invented_metric": {
                      "sources": [s["primary"], s["secondary"]]}}}}
        with g["owner"].begin() as conn:
            pin = register_policy(conn, policy)
        reading = g["record"]("one", revision=2, profiles=[{"role": "invented-role",
            "authority": "invented-register", "registration": "invented-one",
            "valid_from": g["AT"], "fields": {"invented_metric": 10**80 + 3}}])
        s["stage"].apply(batch_id="invented-profile-reader", run_id=str(uuid4()), policy_digest=pin,
            consumer="invented-profile-reader", expected_checkpoint=0, checkpoint=1,
            as_of=g["AS_OF"], assertions=[reading])
        updated = reader.entity(root)
        profile = updated["identity"]["profiles"][0]
        assert profile["fields"]["invented_metric"]["value"] == 10**80 + 3
        assert updated["profile_field_provenance"][profile["profile_id"]]["invented_metric"]["evidence"] == reading
    if case == "details":
        lists = {generation: reader.entity(root, generation=generation)["identity"]["details"]["invented_rows"]
                 for generation in (2, 3, 4, 5)}
        assert len(lists[2]) == 3 and lists[2][0]["amount"] == 10**80 + 1
        assert lists[3][0]["amount"] == 10**80 + 2
        assert lists[4] == lists[5] == [{"key": "D1", "amount": 10**80 + 2, "sources": [s["primary"]]}]
    if case == "one_request":
        # Ticket 147: masters saved in one batch carry that batch's request; a page of
        # them reads it once, not once a master, by primary key.
        readings = [g["record"]("invented-" + name, identifiers={g["NAMESPACE"]: number})
                    for name, number in (("a", "901"), ("b", "902"), ("c", "903"))]
        s["stage"].apply(batch_id="invented-one-request", run_id=str(uuid4()), policy_digest=g["pin"],
            consumer="invented-one-request", expected_checkpoint=0, checkpoint=1,
            as_of=g["AS_OF"], assertions=readings)
        adapter, statements = g["normal"], []
        request_column = adapter.tables["batch"].name + ".intent"

        def executed(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(runtime, "before_cursor_execute", executed)
        try:
            page = reader.snapshot_page("entity", limit=1000)
        finally:
            event.remove(runtime, "before_cursor_execute", executed)
        assert len(page["items"]) >= 4  # the seed master and the three new ones
        assert sum(request_column in statement for statement in statements) == 1
        assert "intent" not in str(adapter.origin_statement([("entity", root)]))  # never once a record
        origins = adapter.read_origins([("source-reading", r["assertion_id"]) for r in readings], immutable=True)
        assert len({(o["origin"]["batch"], o["origin"]["intent"]) for o in origins.values()}) == 1
        # the batch's request is read by its primary key, a seek
        with runtime.connect() as conn:
            saved = set(conn.scalars(select(adapter.tables["batch"].c.batch_key).limit(2)))
        assert_index_lookup(runtime, adapter.origin_requests_statement(saved), adapter.tables["batch"].name)
    if case == "plans":
        adapter = g["normal"]
        for immutable, keys in ((False, [("entity", root), ("entity", "invented-missing")]),
                                (True, [("source-reading", g["holder"]["assertion_id"])])):
            query = adapter.origin_statement(keys, generation=current["generation"], immutable=immutable)
            assert keys[0] in adapter.read_origins(keys, generation=current["generation"], immutable=immutable)
            for name in (("evidence", "batch", "run", "proposal", "proposal_event") if immutable
                         else ("history", "batch", "run", "proposal", "proposal_event")):
                if runtime.dialect.name == "mysql" and name == "history":
                    # A generation-bounded primary-key range is a seek. Require
                    # every key part and actual stop-after-one behavior; the
                    # retained exact-key helper intentionally accepts only ref.
                    import json
                    import re
                    from sqlalchemy import text
                    sql = str(query.compile(dialect=runtime.dialect, compile_kwargs={"literal_binds": True}))
                    with runtime.connect() as conn:
                        plan = json.loads(conn.scalar(text("EXPLAIN FORMAT=JSON " + sql)))
                        actual = conn.scalar(text("EXPLAIN ANALYZE " + sql))

                    def nodes(node):
                        if isinstance(node, dict):
                            yield node
                            for value in node.values():
                                yield from nodes(value)
                        elif isinstance(node, list):
                            for value in node:
                                yield from nodes(value)

                    accesses = [node for node in nodes(plan)
                                if node.get("table_name") == adapter.tables[name].name]
                    assert accesses and all(node.get("access_type") == "range"
                        and node.get("key") == "PRIMARY"
                        and node.get("used_key_parts") == ["type_key", "id_key", "generation"]
                        for node in accesses)
                    # MySQL may execute a constant-key range during optimizer
                    # prefetch. JSON still identifies the complete bounded
                    # primary-key range; the actual node must emit <=1 row.
                    probes = [line for line in actual.splitlines()
                              if re.search(r"index range scan|rows fetched before execution", line, re.I)]
                    assert probes and len(probes) <= len(accesses)
                    for line in probes:
                        measured = re.search(r"actual time=[^)]* rows=([\d.]+) loops=([\d.]+)", line)
                        assert measured and float(measured[1]) <= 1 and float(measured[2]) == 1
                else:
                    assert_index_lookup(runtime, query, adapter.tables[name].name)
    if case == "unknown":
        for generation in (0, -1, True, current["generation"] + 1):
            with pytest.raises(KeyError):
                reader.entity(root, generation=generation)
        with pytest.raises(KeyError):
            reader.entity("invented-missing")
    if case == "bulk_provenance":
        readings = [g["record"]("invented-field-" + str(i), fields={"invented_metric_" + str(i): 10**80 + i})
                    for i in range(405)]
        producer = str(uuid4())
        s["stage"].apply(batch_id="invented-bulk-provenance", run_id=producer, policy_digest=g["pin"],
            consumer="invented-bulk-provenance", expected_checkpoint=0, checkpoint=1,
            as_of=g["AS_OF"], assertions=readings)
        calls = []

        def seen(conn, clause, multiparams, params, execution_options):
            calls.append(clause)

        event.listen(runtime, "before_execute", seen)
        try:
            result = reader.entity(root)
        finally:
            event.remove(runtime, "before_execute", seen)
        for i, reading in enumerate(readings):
            name = "invented_metric_" + str(i)
            assert result["identity"]["fields"][name]["value"] == 10**80 + i
            assert result["field_provenance"][name]["evidence"] == reading
            assert result["field_provenance"][name]["origin_run_id"] == producer
        assert len(calls) < 30, "Provenance must use grouped key probes, not one query per field"
    if case == "inspection":
        import io
        import json
        from contextlib import redirect_stdout
        from edgar_warehouse.cli import main

        os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
        os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
        for command, expected in (("counts", {"entity": 1}),
                                  ("check-connectivity", {"sql": True, "migrations": 7})):
            output = io.StringIO()
            with redirect_stdout(output):
                assert main(["mdm", command]) == 0
            assert json.loads(output.getvalue()) == expected
        adapter = g["normal"]
        assert_index_lookup(runtime, adapter.type_count_statement(["entity"]), adapter.tables["current"].name)
        import hashlib
        from edgar_warehouse.mdm.inspection import HASH_CONTRACT, counts
        from edgar_warehouse.mdm.store import canonical

        report = counts(runtime)
        assert report["masters"] == {g["KIND"]: 1}
        assert report["stage_records"] == {s["primary"]: 1, s["secondary"]: 1}
        assert report["decisions"] == {"bind": 2}
        assert all(report[name] == {} for name in
                   ("waiting", "open_reviews", "set_aside", "identifiers_on_two_masters"))
        assert report["records_hash_contract"] == HASH_CONTRACT
        expected = hashlib.md5((HASH_CONTRACT + "\n").encode())
        for object_type in ("entity", "relationship", "review"):
            keys = adapter.record_keys(object_type)
            rows = adapter.read([(object_type, key) for key in keys])
            for key in keys:
                expected.update(canonical([object_type, key]).encode() + b":" +
                                bytes(rows[object_type, key]["body"]) + b"\n")
        assert report["current_records_md5"] == expected.hexdigest()
        assert counts(runtime) == report
        from edgar_warehouse.mdm.evidence import deferred_record
        held = deferred_record(source_code=s["secondary"], publication_key="1",
            record_locator="invented-inspection-held", schema_version="1",
            reason="invented_missing_key", raw_record={"invented_amount": 7},
            provenance={"object": "invented/held.json"})
        command = dict(batch_id="invented-inspection-held", run_id=str(uuid4()),
            policy_digest=g["seed_pin"], consumer="invented-inspection-held",
            expected_checkpoint=0, checkpoint=1, as_of=g["AS_OF"], deferred=[held])
        s["stage"].apply(**command)
        waiting = counts(runtime)
        assert waiting["set_aside"] == waiting["waiting"] == waiting["open_reviews"] == {"invented_missing_key": 1}
        assert waiting["stage_records"] == report["stage_records"]
        assert s["stage"].apply(**command)["duplicate"]
        assert counts(runtime) == waiting
        for object_type, options, table_name in (
            ("identity", {"immutable": True}, "evidence"),
            ("source-record", {"lookup": True}, "lookup")):
            all_keys = adapter.record_keys(object_type, **options)
            found, after = [], ""
            while page := adapter.record_keys(object_type, after=after, limit=1, **options):
                assert len(page) == 1 and page[0] not in found
                found.extend(page)
                after = page[-1]
            assert found == all_keys
            query = adapter.record_keys_statement(object_type, after=all_keys[0], limit=1, **options)
            if runtime.dialect.name == "mysql":
                from sqlalchemy import text
                sql = str(query.compile(dialect=runtime.dialect, compile_kwargs={"literal_binds": True}))
                with runtime.connect() as conn:
                    plan = json.loads(conn.scalar(text("EXPLAIN FORMAT=JSON " + sql)))
                block = plan["query_block"]
                access = block.get("ordering_operation", block)["table"]
                assert access["table_name"] == adapter.tables[table_name].name
                assert access["access_type"] == "range" and access["key"] == "PRIMARY"
                assert access["used_key_parts"] == ["type_key", "id_key"]
            else:
                assert_index_lookup(runtime, query, adapter.tables[table_name].name)
    if case == "forced_publication":
        import io
        import json
        from contextlib import redirect_stdout
        from pathlib import Path
        from edgar_warehouse.cli import main

        os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
        os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
        output = Path(os.environ["EDGAR_RULES_ROOT"]) / "invented-publication"
        generation = g["normal"].generation()
        args = ["mdm", "force-publish", "--consumer", "invented-export", "--output", str(output)]
        capture = io.StringIO()
        with redirect_stdout(capture):
            assert main(args) == 0
        report = json.loads(capture.getvalue())
        assert output.exists() and report["forced"] and report["records"] > 0
        assert g["normal"].generation() == generation+report["pages"]
        retry = io.StringIO()
        with redirect_stdout(retry):
            assert main([*args,"--run-id",report["run_id"]]) == 0
        assert json.loads(retry.getvalue()) == report
        assert g["normal"].generation() == generation+report["pages"]
    if case == "pages":
        import json
        from sqlalchemy import text

        other = s["later_identity"]("invented-page-other")
        generation = reader.entity(root)["generation"]

        def pages(generation):
            cursor, found = "", []
            while True:
                page = reader.snapshot_page("entity", generation=generation, after=cursor, limit=1)
                assert page["generation"] == generation and len(page["items"]) <= 1
                assert page["business_hash"] == digest([
                    {key: row[key] for key in ("object_id", "body")} for row in page["items"]])
                found.extend(page["items"])
                if page["next_after"] is None:
                    return found
                assert page["next_after"] != cursor
                cursor = page["next_after"]

        before = pages(generation)
        assert {row["object_id"] for row in before} == {root, other}
        s["merge"](root, other)
        future = g["record"]("invented-page-future", s["secondary"], identifiers={})
        identity, bind = g["identity"](future, "2026-01-03T00:00:00Z")
        s["apply"](assertions=[future], identities=[identity], decisions=[bind])
        assert pages(generation) == before
        current_page = pages(reader.entity(root)["generation"])
        assert len(current_page) == 3
        assert next(row for row in current_page if row["object_id"] == other)["body"]["canonical_id"] == root
        assert reader.snapshot_page("relationship", generation=generation)["items"] == []
        query = g["normal"].record_keys_statement("entity", after=before[0]["object_id"], limit=2)
        if runtime.dialect.name == "mysql":
            sql = str(query.compile(dialect=runtime.dialect, compile_kwargs={"literal_binds": True}))
            with runtime.connect() as conn:
                plan = json.loads(conn.scalar(text("EXPLAIN FORMAT=JSON " + sql)))
            table = plan["query_block"]["ordering_operation"]["table"] if "ordering_operation" in plan["query_block"] else plan["query_block"]["table"]
            assert table["access_type"] == "range" and table["key"] == "PRIMARY"
            assert table["used_key_parts"] == ["type_key", "id_key"]
        else:
            assert_index_lookup(runtime, query, g["normal"].tables["current"].name)
    if case == "recording_authority":
        from sqlalchemy import select

        adapter = g["normal"]
        proposal, events = adapter.tables["proposal"], adapter.tables["proposal_event"]
        producer = str(uuid4())
        reading = g["record"]("one", revision=2, fields={"invented_name": "INVENTED RECORDING"})
        command = {"batch_id": "invented-recording-authority", "run_id": producer,
                   "policy_digest": g["seed_pin"], "consumer": "invented-recording-authority",
                   "expected_checkpoint": 0, "checkpoint": 1, "as_of": g["AS_OF"],
                   "assertions": [reading]}
        s["stage"].apply(**command)
        query = select(proposal.c.proposal_key, events.c.occurred).select_from(proposal.join(events,
            (events.c.proposal_key == proposal.c.proposal_key)
            & (events.c.observer_key == adapter._bound_key(producer))
            & (events.c.event == "applied"))).where(
                proposal.c.batch_key == adapter._bound_key(command["batch_id"]),
                proposal.c.state == "applied")
        with runtime.connect() as conn:
            before = conn.execute(query).one()
        assert type(before.occurred) is int and before.occurred > 0
        assert s["stage"].apply(**{**command, "run_id": str(uuid4())})["duplicate"]
        with runtime.connect() as conn:
            assert conn.execute(query).one() == before
        for table in (proposal, events):
            assert_index_lookup(runtime, query, table.name)
    if case == "review_pages":
        from edgar_warehouse.mdm.record_reads import RecordReader

        related = RecordReader(g["normal"]).projections(reviews=[root])
        expected = {item["object_id"]: item["body"] for item in related if item["object_type"] == "review"}
        assert expected and all(body["reason"] == "hierarchy_cycle" for body in expected.values())
        page = reader.snapshot_page("review")
        assert {item["object_id"]: item["body"] for item in page["items"]} == expected
        assert page["next_after"] is None
        assert reader.snapshot_page("review", generation=page["generation"] - 1)["items"] == []
    print("normal master read proof passed")
finally:
    runtime.dispose()
