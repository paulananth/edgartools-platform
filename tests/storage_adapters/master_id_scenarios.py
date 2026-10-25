"""Invented normal MDM saves read by the actual Silver master-ID caller."""

import os
import runpy
from uuid import uuid4

from sqlalchemy import event, select

# Reuse the normal-save fixture, including actual restricted-role seed writes.
os.environ["READ_CASE"] = os.environ.get("READ_BASE_CASE", "join")
g = runpy.run_module("tests.storage_adapters.record_read_scenarios")

from edgar_warehouse.database_connections import engine_from_env
from edgar_warehouse.mdm.clean.evidence import decision
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.relational import DatabaseSink
from edgar_warehouse.silver_writer.tables import data_table
from edgar_warehouse.silver_writer.writer import MdmIds, land, refresh_ids
from tests.unit.test_silver_writer import a_spec

runtime = g["runtime"]
kind, primary, secondary = g["KIND"], g["PRIMARY"], g["SECONDARY"]
root = g["master"]["entity_id"]
ids = MdmIds(runtime)
stage = MergeStage(Store(runtime))
position = 0


def apply(**parts):
    global position
    position += 1
    return stage.apply(batch_id="invented-reader-" + str(position), run_id=str(uuid4()),
                       policy_digest=g["seed_pin"], consumer="invented-readers",
                       expected_checkpoint=position - 1, checkpoint=position,
                       as_of=g["AS_OF"], **parts)


def later_identity(key):
    reading = g["record"](key, secondary, identifiers={})
    identity, bind = g["identity"](reading, "2026-01-02T00:00:00Z")
    apply(assertions=[reading], identities=[identity], decisions=[bind])
    return identity["entity_id"]


def merge(left, right):
    verdict = decision("merge", actor="fixture", reason="invented reviewed duplicate",
                       at="2026-02-01T00:00:00Z", left=left, right=right)
    apply(decisions=[verdict])
    return verdict


case = os.environ["READ_ID_CASE"]
try:
    assert ids(primary, kind, {"one", "missing"}) == {"one": root}
    assert ids(secondary, kind, {"two"}) == {"two": root}
    assert ids(primary, "invented-absent-kind", {"one"}) == {}
    assert ids("invented-absent-source", kind, {"one"}) == {}
    assert ids(primary, kind, set()) == {}
    if case == "waiting":
        reading = g["record"]("waiting", secondary, identifiers={})
        apply(assertions=[reading])
        assert ids(secondary, kind, {"two", "waiting", "missing"}) == {"two": root, "waiting": None}
    if case == "merge":
        other = later_identity("later")
        assert ids(secondary, kind, {"later"}) == {"later": other}
        verdict = merge(root, other)
        assert ids(secondary, kind, {"two", "later"}) == {"two": root, "later": root}
        apply(decisions=[decision("reverse", actor="fixture", reason="invented reversal",
                                  at="2026-02-02T00:00:00Z", target=verdict["decision_id"])])
        assert ids(secondary, kind, {"two", "later"}) == {"two": root, "later": other}
    if case == "unicode":
        key = "INVENTED-雪-" + "x" * 5000
        reading = g["record"](key, primary)
        apply(assertions=[reading], decisions=stage.propose(policy_digest=g["pin"],
             assertions=[reading], as_of=g["AS_OF"])["decisions"])
        assert ids(primary, kind, {key, key.upper(), "missing"}) == {key: root}
    if case == "chunks":
        records = [g["record"]("invented-" + str(i), secondary, identifiers={}) for i in range(405)]
        apply(assertions=records)
        calls = []

        def seen(conn, clause, multiparams, params, execution_options):
            calls.append(clause)

        event.listen(runtime, "before_execute", seen)
        try:
            assert ids(secondary, kind, {r["record_key"] for r in records}) == {r["record_key"]: None for r in records}
        finally:
            event.remove(runtime, "before_execute", seen)
        assert len(calls) < 30, "Master lookup must group key probes instead of querying once per record"
        from tests.storage_adapters.test_prepared_effects import assert_index_lookup

        adapter = g["normal"]
        for query in calls:
            sql = str(query.compile(dialect=runtime.dialect, compile_kwargs={"literal_binds": True}))
            for name in ("lookup", "evidence", "current"):
                table = adapter.tables[name]
                if table.name in sql:
                    assert_index_lookup(runtime, query, table.name)
    if case == "concurrent":
        other = later_identity("later")
        changed = []

        def overtake(conn, cursor, statement, parameters, context, executemany):
            if not changed and "mdm_store_lookup" in statement:
                changed.append(True)
                merge(root, other)

        event.listen(runtime, "after_cursor_execute", overtake)
        try:
            # The merge commits after reading the pointer and before fetching
            # its master. One read must remain at the original generation.
            assert ids(secondary, kind, {"later"}) == {"later": other}
        finally:
            event.remove(runtime, "after_cursor_execute", overtake)
        assert changed and ids(secondary, kind, {"later"}) == {"later": root}
    if case == "silver":
        owner = engine_from_env("READ_SILVER_OWNER_URL")
        delivery = engine_from_env("READ_SILVER_RUNTIME_URL")
        try:
            silver.migrate(owner, runtime_role=os.environ["READ_SILVER_ROLE"])
            spec = a_spec(links=[{"columns": ["member_id"], "kind": kind, "source_code": secondary,
                                  "to_part": "invented-member", "source_key": "member_id",
                                  "mdm_id_column": "member_id_mdm_id", "inclusion": 1.0}])
            silver.register(owner, spec, runtime_role=os.environ["READ_SILVER_ROLE"])
            sink = DatabaseSink(delivery)
            rows = [{"visit_id": 1, "member_id": "two"}, {"visit_id": 2, "member_id": "later"}]
            result = land(sink, "visit", [dict(row) for row in rows], ids)
            assert result["inserted"] == 2 and result["mdm_keys_found"] == 1
            target = data_table(sink.spec("visit"), delivery.dialect.name)

            def stored():
                with delivery.connect() as conn:
                    return dict(conn.execute(select(target.c.member_id, target.c.member_id_mdm_id)).all())

            assert stored() == {"two": root, "later": None}
            other = later_identity("later")
            assert refresh_ids(sink, "visit", ids)["rows_updated"] == {"member_id_mdm_id": 1}
            assert stored() == {"two": root, "later": other}
            verdict = merge(root, other)
            assert refresh_ids(sink, "visit", ids)["rows_updated"] == {"member_id_mdm_id": 1}
            assert stored() == {"two": root, "later": root}
            apply(decisions=[decision("reverse", actor="fixture", reason="invented reversal",
                                      at="2026-02-02T00:00:00Z", target=verdict["decision_id"])])
            assert refresh_ids(sink, "visit", ids)["rows_updated"] == {"member_id_mdm_id": 1}
            assert stored() == {"two": root, "later": other}
            assert refresh_ids(sink, "visit", ids)["rows_updated"] == {"member_id_mdm_id": 0}
            assert land(sink, "visit", [dict(row) for row in rows], ids)["inserted"] == 0
            assert stored() == {"two": root, "later": other}
        finally:
            owner.dispose()
            delivery.dispose()
    print("normal master-ID proof passed")
finally:
    runtime.dispose()
