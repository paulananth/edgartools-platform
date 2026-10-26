"""Invented names, normal saves and the actual Context and owner commands."""
import io
import json
import os
import runpy
import subprocess
import sys
from argparse import Namespace
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import DBAPIError

os.environ.update(READ_ID_CASE="lookup", READ_BASE_CASE="join")
s = runpy.run_module("tests.storage_adapters.master_id_scenarios")
g = s["g"]

from edgar_warehouse.cli import main
from edgar_warehouse.context import Context, ContextError
from edgar_warehouse.mdm.clean import master_search
from edgar_warehouse.mdm.clean.evidence import decision
from edgar_warehouse.mdm.clean.record_reads import RecordReader
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.rules import files
from tests.storage_adapters.test_prepared_effects import assert_index_lookup

runtime, owner, root = s["runtime"], g["owner"], s["root"]
api, kind = g["normal"], g["KIND"]
revision = 1


def rename(name, **fields):
    global revision
    revision += 1
    return s["apply"](assertions=[g["record"]("one", revision=revision,
        fields={"invented_name": name, **fields})])


def names(words, *, limit=20, subject=None):
    return Context(runtime).answer(Namespace(subject=subject or kind, key=None, search=words,
        limit=limit, as_of=None, as_at=None, detail="full", page=None))["matches"]


def found(words):
    return [row["entity_id"] for row in names(words)]


def other(name, key):
    reading = g["record"](key, s["secondary"], identifiers={}, fields={"invented_name": name})
    floor = RecordReader(api).publications([kind])[kind]["published_at"]
    identity, bind = g["identity"](reading,
        (datetime.fromisoformat(floor) + timedelta(microseconds=1)).isoformat())
    s["apply"](assertions=[reading], identities=[identity], decisions=[bind])
    return identity["entity_id"]


def durable_counts():
    with runtime.connect() as conn:
        return {name: conn.scalar(select(func.count()).select_from(api.tables[name]))
                for name in ("batch", "current", "history", "evidence", "checkpoint", "outbox")}


def gap(name):
    with patch.object(master_search, "normal_changes", return_value=[]):
        rename(name)
    with pytest.raises(ContextError, match="complete index"):
        names(name)


case = os.environ["READ_SEARCH_CASE"]
try:
    if case == "words":
        rename("A The Snow x-y a.b@c/d 雪 %_")
        for words in ("A", "THE", '"The Snow"', "the -missing", "missing OR snow", "x-y", "x", "a.b@c/d", "雪"):
            assert found(words) == [root]
            assert names(words)[0]["matched_by"] == "words"
        for words in ("he sno", "%_", "."):
            assert found(words) == [root]
            assert names(words)[0]["matched_by"] == "contains"
        assert found("the -snow") == found("-snow") == found("a%b") == []
        another = "invented-other-kind" if kind == "invented-kind" else "invented-kind"
        assert names("snow", subject=another) == []
        rename("FALLBACK", invented_display="PREFERRED")
        assert found("preferred") == [root] and found("fallback") == []
        rename("FALLBACK", invented_display="")
        assert found("fallback") == [root]
        rename(None, invented_display=None)
        assert found("fallback") == [root]  # Unknown evidence does not clear an earlier value.
        nameless = other(None, "invented-nameless")
        assert found("-fallback") == [nameless] and names("-fallback")[0]["name"] is None
        before = durable_counts()
        with pytest.raises((Conflict, ValueError), match="Search name must be text"):
            rename("FALLBACK", invented_display=23)
        assert durable_counts() == before and found("fallback") == [root]
    if case == "ranking":
        rename("Z Snow")
        second = other("A Snow", "invented-search-two")
        assert found("snow") == [second, root]
        assert names("snow", limit=1)[0]["entity_id"] == second
        third = other("A Snowy", "invented-search-three")
        assert found("snow") == [second, root] and third not in found("snow")
        assert found("nowy") == [third]
        unnamed = other(None, "invented-unnamed")
        assert found("-missing") == [second, third, root, unnamed]
    if case == "changes":
        rename("FIRST")
        rename("SECOND")
        assert found("first") == [] and found("second") == [root]
        second = other("OTHER", "invented-search-two")
        assert found("other") == [second]
        merged = s["merge"](root, second)
        assert found("other") == [] and found("second") == [root]
        s["apply"](decisions=[decision("reverse", actor="fixture", reason="invented search reversal",
            at="2026-02-02T00:00:00Z", target=merged["decision_id"])])
        assert found("other") == [second]
        os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
        os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
        output = io.StringIO()
        with redirect_stdout(output):
            assert main(["context", kind, "--search", "OTHER"]) == 0
        assert json.loads(output.getvalue())["matches"][0]["entity_id"] == second
    if case == "legacy_gap":
        gap("OVERTAKEN")
        rename("LATEST")
        with pytest.raises(ContextError, match="complete index"):
            names("latest")
        before, generation = durable_counts(), api.generation()
        with pytest.raises(DBAPIError):
            master_search.rebuild(runtime, limit=1)
        assert durable_counts() == before and api.generation() == generation
        report = master_search.rebuild(owner)
        assert report == {"generation": generation, "processed": 1, "ready": True}
        assert found("latest") == [root] and found("overtaken") == []
        assert durable_counts() == before and api.generation() == generation
        assert master_search.rebuild(owner)["processed"] == 0
    if case == "rebuild":
        other("SECOND", "invented-search-two")
        other("THIRD", "invented-search-three")
        gap("REBUILT")
        before, generation = durable_counts(), api.generation()
        first = master_search.rebuild(owner, limit=1)
        assert first == {"generation": generation, "processed": 1, "ready": False}
        with pytest.raises(ContextError, match="complete index"):
            names("rebuilt")
        pin = master_search.digest(master_search.configuration())
        with owner.connect() as conn:
            checkpoint = master_search.state(api, conn, pin, generation)
        original = type(api).maintain_lookups

        def interrupted(self, conn, **kwargs):
            original(self, conn, **kwargs)
            raise RuntimeError("invented owner interruption")

        with patch.object(type(api), "maintain_lookups", interrupted):
            with pytest.raises(RuntimeError, match="invented owner interruption"):
                master_search.rebuild(owner, limit=1)
        with owner.connect() as conn:
            assert master_search.state(api, conn, pin, generation) == checkpoint
        rename("CURRENT")
        with pytest.raises(Conflict, match="stale"):
            master_search.rebuild(owner, limit=1)
        os.environ["MDM_DATABASE_URL"] = os.environ["READ_OWNER_URL"]
        output = io.StringIO()
        with redirect_stdout(output):
            assert main(["mdm", "rebuild-name-index", "--restart", "--limit", "1"]) == 0
        assert json.loads(output.getvalue())["processed"] == 1
        final = master_search.rebuild(owner)
        assert final["ready"] and final["processed"] == 2
        assert found("current") == [root]
        assert durable_counts()["batch"] == before["batch"] + 1
        assert api.generation() == generation + 1
    if case == "concurrent":
        rename("BEFORE")
        fired = []

        def replacing(conn, clause, multiparams, params, execution_options):
            if not fired and api.tables["current"].name in str(clause):
                fired.append(True)
                rename("AFTER")

        event.listen(runtime, "before_execute", replacing)
        try:
            assert found("before") == [root]
        finally:
            event.remove(runtime, "before_execute", replacing)
        assert fired and found("before") == [] and found("after") == [root]
    if case == "plans":
        rename("A The Snow %_ 雪")
        pin = master_search.digest(master_search.configuration())
        plan = master_search.prepare("query", words="the")
        groups = [RecordReader.group("master_name_words", pin, kind, token)
                  for alternative in plan["alternatives"] for token in alternative]
        groups += [RecordReader.group("master_name_fragments", pin, kind, token)
                   for token in plan["fragments"]]
        groups += [RecordReader.group("master_name_scope", pin, kind)]
        for group in groups:
            assert_index_lookup(runtime, api.type_statement(group, lookup=True), api.tables["lookup"].name)
            assert_index_lookup(runtime, api.lookup_statement([(group, root)], lookup=True), api.tables["lookup"].name)
        assert found("the") == [root]
    if case == "pages":
        rename("COMMON ROOT")
        floor = datetime.fromisoformat(RecordReader(api).publications([kind])[kind]["published_at"])
        readings, identities, decisions = [], [], []
        for i in range(400):
            reading = g["record"]("invented-page-" + str(i), s["secondary"], identifiers={},
                fields={"invented_name": "COMMON " + str(i).zfill(4)})
            identity, bind = g["identity"](reading, (floor + timedelta(microseconds=i + 1)).isoformat())
            readings.append(reading)
            identities.append(identity)
            decisions.append(bind)
        s["apply"](assertions=readings, identities=identities, decisions=decisions)
        from edgar_warehouse.mdm.clean import master_search as search_module
        original = search_module.prepare
        cohort_sizes = []

        def bounded(operation, **values):
            if operation == "rank":
                cohort_sizes.append(len(values["rows"]))
            return original(operation, **values)

        with patch.object(search_module, "prepare", bounded):
            result = names("common", limit=3)
        assert [row["entity_id"] for row in result] == [identity["entity_id"] for identity in identities[:3]]
        assert len(cohort_sizes) >= 3 and max(cohort_sizes) <= 203
    if case == "maintenance":
        pin = master_search.digest(master_search.configuration())
        key = master_search.state_key(pin)
        before, generation = durable_counts(), api.generation()
        original = api.read([key], lookup=True)[key]
        from edgar_warehouse.mdm.clean.store import storage_adapter
        module = storage_adapter()
        stale = module.IndexChange(*key, original["body"], expected_version=original["version"] + 1)
        for arguments, message in [
            ({"expected_generation": generation - 1, "changes": []}, "stale_generation"),
            ({"expected_generation": generation, "batch": "invented-missing", "changes": []}, "provenance"),
            ({"expected_generation": generation, "changes": [stale]}, "stale_object_version"),
            ({"expected_generation": generation, "changes": [stale, stale]}, "Duplicate")]:
            with owner.begin() as conn:
                with pytest.raises(module.AdapterError, match=message):
                    api.maintain_lookups(conn, **arguments)
        with owner.begin() as conn:
            conn.execute(update(api.tables["migration"]).values(complete=0))
            with pytest.raises(module.AdapterError, match="storage_not_initialized"):
                api.maintain_lookups(conn, expected_generation=generation, changes=[])
            conn.rollback()
        assert api.read([key], lookup=True)[key] == original
        assert durable_counts() == before and api.generation() == generation
        # 401 opaque references cross the 200-row write boundary. Count actual
        # driver executions: executemany must not hide one update per record.
        statements = []
        def counted(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                statements.append(statement)
        event.listen(owner, "before_cursor_execute", counted)
        try:
            changes = [module.IndexChange("invented-maintenance", str(i), b'{}') for i in range(401)]
            with owner.begin() as conn:
                api.maintain_lookups(conn, expected_generation=generation, changes=changes)
            assert len(statements) == 3
            statements.clear()
            changes = [module.IndexChange("invented-maintenance", str(i), b'{"changed":true}',
                       expected_version=1, removed=i < 200) for i in range(401)]
            with owner.begin() as conn:
                api.maintain_lookups(conn, expected_generation=generation, changes=changes)
            assert len(statements) == 3
            held = api.read([("invented-maintenance", str(i)) for i in range(401)], lookup=True)
            assert len(held) == 201 and all(row["version"] == 2 for row in held.values())
            assert all(row["body"] == b'{"changed":true}' for row in held.values())
        finally:
            event.remove(owner, "before_cursor_execute", counted)
        assert durable_counts() == before and api.generation() == generation
    if case == "configuration":
        rename("ALTERNATE", invented_display="PREFERRED")
        assert found("preferred") == [root] and found("alternate") == []
        before, generation = durable_counts(), api.generation()
        incoming = g["record"]("one", revision=revision + 1,
            fields={"invented_name": "AFTER", "invented_display": "PREFERRED"})
        path = Path(os.environ["EDGAR_RULES_ROOT"]) / "mastering/engine-v1.yaml"
        body = files.load(path)
        body["version"] = "invented-search-catalog-v2"
        body["master_search"]["version"] = "invented-master-search-v2"
        body["master_search"]["name_fields"] = ["invented_name", "invented_display"]
        path.write_text(files.dumps(body))
        with pytest.raises(ValueError, match="catalog changed"):
            names("preferred")
        code = '''
import os
from argparse import Namespace
from uuid import uuid4
import pytest
from sqlalchemy import func,select
from edgar_warehouse.context import Context,ContextError
from edgar_warehouse.database_connections import engine_from_env
from edgar_warehouse.mdm.clean import master_search
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store,migrate,storage_adapter
owner,runtime=engine_from_env("READ_OWNER_URL"),engine_from_env("READ_RUNTIME_URL")
try:
    migrate(owner,application_role=os.environ["READ_RUNTIME_ROLE"],prepared=True)
    api=storage_adapter().Adapter(runtime,prefix="mdm_store",protocol=6)
    def names(words):
        return Context(runtime).answer(Namespace(subject=KIND,key=None,search=words,limit=20,
            as_of=None,as_at=None,detail="full",page=None))["matches"]
    def counts():
        with runtime.connect() as conn:
            return {name:conn.scalar(select(func.count()).select_from(api.tables[name]))
                for name in ("batch","current","history","evidence","checkpoint","outbox")}
    assert api.generation()==GENERATION and counts()==COUNTS
    with pytest.raises(ContextError,match="complete index"):
        names("preferred")
    assert master_search.rebuild(owner,limit=1)=={"generation":GENERATION,"processed":1,"ready":True}
    assert counts()==COUNTS and api.generation()==GENERATION
    assert names("alternate")[0]["entity_id"]==ROOT and names("preferred")==[]
    stage=MergeStage(Store(runtime))
    command={"batch_id":"invented-reconfigured-save","run_id":str(uuid4()),"policy_digest":POLICY,
        "consumer":"invented-reconfigured-save","expected_checkpoint":0,"checkpoint":1,
        "as_of":AS_OF,"assertions":[READING]}
    assert stage.apply(**command)["generation"]==GENERATION+1
    assert names("after")[0]["entity_id"]==ROOT and names("alternate")==[]
    pin=master_search.digest(master_search.configuration())
    key=master_search.state_key(pin)
    original=api.read([key],lookup=True)[key]
    before=counts()
    assert stage.apply(**{**command,"run_id":str(uuid4())})["duplicate"]
    assert counts()==before and api.read([key],lookup=True)[key]==original
finally:
    owner.dispose();runtime.dispose()
'''
        constants = {"KIND": kind, "ROOT": root, "GENERATION": generation, "COUNTS": before,
                     "READING": incoming, "POLICY": g["seed_pin"], "AS_OF": g["AS_OF"]}
        program = "\n".join(name + "=" + repr(value) for name, value in constants.items()) + "\n" + code
        child = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, timeout=45)
        if child.returncode:
            (path.parent / "reconfigured-search-diagnostic.log").write_text(child.stdout + "\n" + child.stderr)
        assert child.returncode == 0, "reconfigured search failed; private diagnostic retained"
    print("normal master search proof passed")
finally:
    owner.dispose()
    runtime.dispose()
