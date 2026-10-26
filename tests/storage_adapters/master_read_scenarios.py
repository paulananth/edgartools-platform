"""Normal versioned consumer reads after normal restricted-role MDM saves."""

import os
import runpy
from uuid import uuid4

import pytest
from sqlalchemy import event

os.environ["READ_ID_CASE"] = "lookup"
case = os.environ["READ_CONSUMER_CASE"]
if case in ("context_links", "context_relationships", "review_pages"):
    os.environ["READ_CASE"] = "hierarchy" if case == "review_pages" else "links"
    g = runpy.run_module("tests.storage_adapters.record_read_scenarios")
    s = {"g": g, "runtime": g["runtime"], "root": g["master"]["entity_id"],
         "primary": g["PRIMARY"], "secondary": g["SECONDARY"]}
else:
    s = runpy.run_module("tests.storage_adapters.master_id_scenarios")
    g = s["g"]

from edgar_warehouse.mdm.clean.consumer import ContractReader
from edgar_warehouse.mdm.clean.evidence import decision
from edgar_warehouse.mdm.clean.store import digest, register_policy
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
        from argparse import Namespace
        from edgar_warehouse.context import Context

        other = s["later_identity"]("later")
        before = reader.entity(other)
        args = Namespace(subject=g["KIND"], key=other, search=None, as_at=None,
                         as_of=None, detail="full", page=None)
        before_at = before["projection"]["recorded_at"]
        assert Context(runtime).answer(args)["entity_id"] == other
        verdict = s["merge"](root, other)
        merged = reader.entity(other)
        assert merged["requested_id"] == other and merged["canonical_id"] == root
        assert merged["identity"] == reader.entity(root)["identity"]
        assert reader.entity(other, generation=before["generation"]) == before
        redirected = Context(runtime).answer(args)
        assert redirected["entity_id"] == root and redirected["merged_from"] == other
        historical = Context(runtime).answer(Namespace(**{**vars(args), "as_at": before_at}))
        assert historical["entity_id"] == other
        assert historical["trust"]["generation"] == before["projection"]["generation"]
        s["apply"](decisions=[decision("reverse", actor="fixture", reason="invented reversal",
            at="2026-02-02T00:00:00Z", target=verdict["decision_id"])])
        assert reader.entity(other)["canonical_id"] == other
        assert reader.entity(other, generation=merged["generation"]) == merged
        assert Context(runtime).answer(args)["entity_id"] == other
        past_merge = Context(runtime).answer(Namespace(**{**vars(args),
            "as_at": merged["projection"]["recorded_at"]}))
        assert past_merge["entity_id"] == root and past_merge["merged_from"] == other
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
                                  ("check-connectivity", {"sql": True, "migrations": 6})):
            output = io.StringIO()
            with redirect_stdout(output):
                assert main(["mdm", command]) == 0
            assert json.loads(output.getvalue()) == expected
        adapter = g["normal"]
        assert_index_lookup(runtime, adapter.type_count_statement(["entity"]), adapter.tables["current"].name)
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
        from edgar_warehouse.mdm.clean.record_reads import RecordReader

        related = RecordReader(g["normal"]).projections(reviews=[root])
        expected = {item["object_id"]: item["body"] for item in related if item["object_type"] == "review"}
        assert expected and all(body["reason"] == "hierarchy_cycle" for body in expected.values())
        page = reader.snapshot_page("review")
        assert {item["object_id"]: item["body"] for item in page["items"]} == expected
        assert page["next_after"] is None
        assert reader.snapshot_page("review", generation=page["generation"] - 1)["items"] == []
    if case == "context_search_gap":
        import io
        import json
        from contextlib import redirect_stdout
        from edgar_warehouse.cli import main

        os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
        os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["context", g["KIND"], "--search", "INVENTED"])
        result = json.loads(output.getvalue())
        assert status == 2
        assert result["error"] == "Name search is not installed for prepared MDM storage."
        assert "<entity_id>" in result["try"] and "<namespace>:<value>" in result["try"]
    if case == "context_relationships":
        import io
        import json
        from argparse import Namespace
        from contextlib import redirect_stdout
        from edgar_warehouse.cli import main
        from edgar_warehouse.context import Context

        args = Namespace(subject="relationship", key=root, search=None, as_at=None, as_of=None,
                         detail="full", page=None, hops=2, relationship_type="")
        current_links = Context(runtime).answer(args)
        assert current_links["related_count"] == 1
        assert current_links["related"][0]["to"]["entity_id"] == g["third_id"]["entity_id"]
        assert current_links["related"][0]["sources"] == [{"source_code": s["primary"], "record_key": "one"}]
        earlier = g["normal"].batch_metadata(g["result"]["generation"] - 1, limit=1)[0]
        from datetime import UTC, datetime, timedelta
        at = (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=earlier["recorded_at"])).isoformat()
        old = Context(runtime).answer(Namespace(**{**vars(args), "as_at": at}))
        assert old["related_count"] == 1
        assert old["related"][0]["to"]["entity_id"] == g["second_id"]["entity_id"]
        assert old["trust"]["generation"] == earlier["generation"]
        old_page = reader.snapshot_page("relationship", generation=earlier["generation"])
        assert len(old_page["items"]) == 1
        assert old_page["items"][0]["body"]["target_id"] == g["second_id"]["entity_id"]
        current_page = reader.snapshot_page("relationship")
        assert len(current_page["items"]) == 2
        assert any(item["body"].get("retired") for item in current_page["items"])
        os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
        os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["context", "relationship", root, "--detail", "full", "--hops", "2", "--as-at", at])
        assert status == 0, json.loads(output.getvalue()).get("error")
        cli = json.loads(output.getvalue())
        # Each call evaluates link periods at its own current business clock.
        assert datetime.fromisoformat(cli["at"]) >= datetime.fromisoformat(old["at"])
        assert {k: v for k, v in cli.items() if k != "at"} == {k: v for k, v in old.items() if k != "at"}
    if case == "context_lookup":
        from argparse import Namespace
        from edgar_warehouse.context import Context, ContextError

        def ask(key):
            return Context(runtime).answer(Namespace(subject=g["KIND"], key=key, search=None,
                as_at=None, as_of=None, detail="full", page=None))

        namespace, value = next(iter(g["holder"]["identifiers"].items()))
        assert ask(namespace + ":" + value)["entity_id"] == root
        s["apply"](assertions=[g["record"]("one", revision=2,
            cross_references={"invented-reference": "INVENTED-X"})])
        crossed = ask("invented-reference:INVENTED-X")
        assert crossed["entity_id"] == root
        assert crossed["cross_references"] == {"invented-reference": ["INVENTED-X"]}
        s["apply"](assertions=[g["record"]("invented-waiting", s["secondary"], identifiers={},
            cross_references={"invented-reference": "INVENTED-X"})])
        assert ask("invented-reference:INVENTED-X")["entity_id"] == root
        other = s["later_identity"]("invented-other-carrier")
        s["apply"](assertions=[g["record"]("invented-other-carrier", s["secondary"], revision=2,
            identifiers={}, cross_references={"invented-reference": "INVENTED-X"})])
        with pytest.raises(ContextError, match="carried by 2 entities"):
            ask("invented-reference:INVENTED-X")
        s["merge"](root, other)
        assert ask("invented-reference:INVENTED-X")["entity_id"] == root
        with pytest.raises(ContextError):
            ask("invented-reference:INVENTED-MISSING")
    if case == "context_times":
        import json
        from argparse import Namespace
        from sqlalchemy import text
        from edgar_warehouse.context import Context, ContextError

        command = {"batch_id": "invented-context-time", "run_id": str(uuid4()),
                   "policy_digest": g["seed_pin"], "consumer": "invented-context-time",
                   "expected_checkpoint": 0, "checkpoint": 1, "as_of": "2026-04-01T00:00:00Z",
                   "assertions": [g["record"]("one", revision=2,
                       fields={"invented_name": "INVENTED LATER", "invented_metric": 10**400})]}
        saved = s["stage"].apply(**command)
        args = Namespace(subject=g["KIND"], key=root, search=None, as_at=None, as_of=None,
                         detail="full", page=None)
        old = Context(runtime).answer(Namespace(**{**vars(args), "as_at": current["projection"]["recorded_at"]}))
        assert old["trust"]["generation"] == current["projection"]["generation"]
        assert next(field["value"] for field in old["fields"] if field["field"] == "invented_name") == current["identity"]["fields"]["invented_name"]["value"]
        business = Context(runtime).answer(Namespace(**{**vars(args), "as_of": "2026-03-31T00:00:00Z"}))
        assert business["trust"]["generation"] == old["trust"]["generation"]
        later = Context(runtime).answer(Namespace(**{**vars(args), "as_of": "2026-04-01T00:00:00Z"}))
        assert later["trust"]["generation"] == saved["generation"]
        assert next(field["value"] for field in later["fields"] if field["field"] == "invented_metric") == 10**400
        for flag in ("as_at", "as_of"):
            with pytest.raises(ContextError):
                Context(runtime).answer(Namespace(**{**vars(args), flag: "2000-01-01T00:00:00Z"}))
        adapter = g["normal"]
        for path in ((), ("effects", "as_of")):
            query = adapter.batch_metadata_statement(saved["generation"], path=path)
            for name in ("proposal", "proposal_event"):
                assert_index_lookup(runtime, query, adapter.tables[name].name)
            if runtime.dialect.name == "mysql":
                sql = str(query.compile(dialect=runtime.dialect, compile_kwargs={"literal_binds": True}))
                with runtime.connect() as conn:
                    plan = json.loads(conn.scalar(text("EXPLAIN FORMAT=JSON " + sql)))

                def batch_nodes(node):
                    if isinstance(node, dict):
                        if node.get("table_name") == adapter.tables["batch"].name:
                            yield node
                        for value in node.values():
                            yield from batch_nodes(value)
                    elif isinstance(node, list):
                        for value in node:
                            yield from batch_nodes(value)

                accesses = list(batch_nodes(plan))
                assert accesses and all(n.get("access_type") == "range"
                    and n.get("key") == adapter.prefix + "_generation_unique" for n in accesses)
            else:
                assert_index_lookup(runtime, query, adapter.tables["batch"].name)
    if case == "context_concurrent":
        from argparse import Namespace
        from edgar_warehouse.context import Context

        changed = []
        reading = g["record"]("one", revision=2, fields={"invented_name": "INVENTED CONCURRENT"})

        def overtake(conn, cursor, statement, parameters, context, executemany):
            if not changed and "mdm_store_history" in statement:
                changed.append(True)
                s["stage"].apply(batch_id="invented-context-concurrent", run_id=str(uuid4()),
                    policy_digest=g["seed_pin"], consumer="invented-context-concurrent",
                    expected_checkpoint=0, checkpoint=1, as_of=g["AS_OF"], assertions=[reading])

        args = Namespace(subject=g["KIND"], key=root, search=None, as_at=None, as_of=None,
                         detail="full", page=None)
        event.listen(runtime, "after_cursor_execute", overtake)
        try:
            before = Context(runtime).answer(args)
        finally:
            event.remove(runtime, "after_cursor_execute", overtake)
        assert changed and before["trust"]["generation"] == current["projection"]["generation"]
        assert next(field["value"] for field in before["fields"] if field["field"] == "invented_name") == current["identity"]["fields"]["invented_name"]["value"]
        after = Context(runtime).answer(args)
        assert after["trust"]["generation"] > before["trust"]["generation"]
        assert next(field["value"] for field in after["fields"] if field["field"] == "invented_name") == "INVENTED CONCURRENT"
    if case in ("context_current", "context_links"):
        import io
        import json
        from argparse import Namespace
        from contextlib import redirect_stdout
        from edgar_warehouse.cli import main
        from edgar_warehouse.context import Context

        result = Context(runtime).answer(Namespace(subject=g["KIND"], key=root, search=None,
            as_at=None, as_of=None, detail="full", page=None))
        assert result["entity_id"] == root
        assert result["trust"]["recorded_at"] == current["projection"]["recorded_at"]
        assert result["trust"]["run_id"] == current["projection"]["origin_run_id"]
        expected_sources = {s["primary"]: ["one"]}
        if case == "context_current":
            expected_sources[s["secondary"]] = ["two"]
        assert result["sources"] == expected_sources
        if case == "context_links":
            from datetime import datetime

            assert result["related_count"] == 1
            assert result["related"][0]["type"] == "invented_link"
            assert result["related"][0]["from"]["entity_id"] == root
            assert result["related"][0]["to"]["entity_id"] == g["third_id"]["entity_id"]
            with runtime.connect() as conn:
                earlier, count, cut = Context(runtime)._walk(conn, root, 1,
                    datetime.fromisoformat(g["AS_OF"]), "", 10, g["result"]["generation"] - 1)
            assert count == 1 and not cut
            assert earlier[0]["to"]["entity_id"] == g["second_id"]["entity_id"]
        os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
        os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["context", g["KIND"], root, "--detail", "full"])
        assert status == 0, json.loads(output.getvalue()).get("error")
        assert json.loads(output.getvalue()) == result
    if case == "recorded_time":
        from argparse import Namespace
        from edgar_warehouse.context import Context

        args = Namespace(subject=s["kind"], key=root, search=None, as_of=None,
                         as_at="2030-01-01T00:00:00Z", detail="brief", page=None)
        answer = Context(runtime).answer(args)
        assert answer["entity_id"] == root and answer["trust"]["recorded_at"] is not None
    print("normal master read proof passed")
finally:
    runtime.dispose()
