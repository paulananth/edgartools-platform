"""Invented detail rows, normal saves and the owner rebuild of the detail lookup."""
import io
import json
import os
import runpy
from argparse import Namespace
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.exc import DBAPIError

os.environ.update(READ_ID_CASE="lookup", READ_BASE_CASE="details")
s = runpy.run_module("tests.storage_adapters.master_id_scenarios")
g = s["g"]

from edgar_warehouse.cli import main
from edgar_warehouse.context import Context, ContextError
from edgar_warehouse.mdm.clean import detail_lookups
from edgar_warehouse.mdm.clean.evidence import decision
from edgar_warehouse.mdm.clean.record_reads import RecordReader
from edgar_warehouse.mdm.clean.store import Conflict

runtime, owner, root = s["runtime"], g["owner"], s["root"]
api, kind = g["normal"], g["KIND"]
revision = 3  # the details base case wrote revisions 2 and 3


def rows(*listed):
    """Detail rows of (key, venue, code, symbol); None leaves a field out."""
    return {"invented_rows": [{name: value for name, value in
                               zip(("key", "invented_venue", "invented_code", "invented_symbol"), row)
                               if value is not None} for row in listed]}


def relist(*listed):
    global revision
    revision += 1
    return s["apply"](assertions=[g["record"]("one", revision=revision, details=rows(*listed))])


def other(key, *listed):
    reading = g["record"](key, s["secondary"], identifiers={}, details=rows(*listed))
    floor = RecordReader(api).publications([kind])[kind]["published_at"]
    identity, bind = g["identity"](reading,
        (datetime.fromisoformat(floor) + timedelta(microseconds=1)).isoformat())
    s["apply"](assertions=[reading], identities=[identity], decisions=[bind])
    return identity["entity_id"]


def found(name, *values):
    with runtime.connect() as conn:
        return [row["entity_id"] for row in detail_lookups.find(api, conn, name, list(values))]


case = os.environ["READ_LOOKUP_CASE"]
try:
    if case == "keys":
        relist(("D1", "V1", "C1", "S1"), ("D2", None, "C2", "S1"), ("D3", "V1", "C3", None))
        assert found("venue", "V1", "S1") == found("code", "C1", "S1") == found("code", "C2", "S1") == [root]
        # A row without every field of a key is not found by it.
        assert found("venue", "V1", "C3") == found("code", "C3", "S1") == found("venue", "V2", "S1") == []
        with pytest.raises(Conflict, match="takes"):
            found("venue", "V1")
        with pytest.raises(Conflict, match="takes"):
            found("invented-absent-key", "V1", "S1")
    if case == "changes":
        relist(("D1", "V1", "C1", "S1"), ("D2", "V2", "C2", "S2"))
        # A row a later reading drops leaves the lookup.
        relist(("D1", "V1", "C1", "S1"))
        assert found("venue", "V2", "S2") == [] and found("venue", "V1", "S1") == [root]
        # Every master holding a key is found, never one picked.
        second = other("invented-lookup-two", ("D9", "V1", "C9", "S1"))
        assert found("venue", "V1", "S1") == sorted([root, second])
        # A merged-away master leaves it; its rows go with the survivor; a reversal restores both.
        merged = s["merge"](root, second)
        assert found("venue", "V1", "S1") == found("code", "C9", "S1") == [root]
        s["apply"](decisions=[decision("reverse", actor="fixture", reason="invented lookup reversal",
            at="2026-02-02T00:00:00Z", target=merged["decision_id"])])
        assert found("venue", "V1", "S1") == sorted([root, second]) and found("code", "C9", "S1") == [second]
    if case == "rebuild":
        relist(("D1", "V1", "C1", "S1"))
        with patch.object(detail_lookups, "normal_changes", return_value=[]):
            relist(("D2", "V2", "C2", "S2"))
        with pytest.raises(Conflict, match="complete index"):
            found("venue", "V2", "S2")
        second = other("invented-lookup-two", ("D9", "V2", "C9", "S2"))
        with pytest.raises(Conflict, match="complete index"):
            found("venue", "V2", "S2")  # A later save never conceals the gap.
        first = detail_lookups.rebuild(owner, limit=1)
        assert first["processed"] == 1 and not first["ready"]
        with pytest.raises(Conflict, match="complete index"):
            found("venue", "V2", "S2")
        rest = detail_lookups.rebuild(owner)
        assert rest["ready"] and rest["generation"] == first["generation"]
        assert found("venue", "V2", "S2") == sorted([root, second]) and found("venue", "V1", "S1") == []
        assert detail_lookups.rebuild(owner)["processed"] == 0
        with pytest.raises(DBAPIError):
            detail_lookups.rebuild(runtime, limit=1)
    if case == "retired":
        relist(("D1", "V1", "C1", "S1"))
        reading = g["record"]("invented-lookup-two", s["secondary"], identifiers={},
                              details=rows(("D9", "V1", "C9", "S1")))
        floor = RecordReader(api).publications([kind])[kind]["published_at"]
        identity, bind = g["identity"](reading,
            (datetime.fromisoformat(floor) + timedelta(microseconds=1)).isoformat())
        s["apply"](assertions=[reading], identities=[identity], decisions=[bind])
        assert found("venue", "V1", "S1") == sorted([root, identity["entity_id"]])
        # A retired master leaves the lookup; the other holder stays.
        s["apply"](decisions=[decision("retire_source", actor="fixture", reason="invented retirement",
            at="2026-02-02T00:00:00Z", source_code=s["secondary"], evidence=[reading["assertion_id"]])])
        assert found("venue", "V1", "S1") == [root] and found("code", "C9", "S1") == []
    if case == "context":
        relist(("D1", "V1", "C1", "S1"))
        second = other("invented-lookup-two", ("D9", "V1", "C9", "S1"))

        def held(*key, subject=kind):
            return Context(runtime).answer(Namespace(subject=subject, key=None, search=None, detail_key=list(key),
                limit=5, as_of=None, as_at=None, detail="brief", page=None))

        answer = held("venue", "V1", "S1")
        assert [row["entity_id"] for row in answer["matches"]] == sorted([root, second])
        assert answer["detail_key"] == {"name": "venue", "values": ["V1", "S1"],
                                        "fields": ["invented_venue", "invented_symbol"]}
        assert held("code", "C9", "S1")["matches"][0]["entity_id"] == second
        assert held("venue", "V9", "S1")["matches"] == []
        with pytest.raises(ContextError, match="takes"):
            held("venue", "V1")
        with pytest.raises(ContextError, match="No detail lookup"):
            held("venue", "V1", "S1", subject="invented-other-kind")
        os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
        os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
        output = io.StringIO()
        with redirect_stdout(output):
            assert main(["context", kind, "--detail-key", "code", "C1", "S1"]) == 0
        assert [row["entity_id"] for row in json.loads(output.getvalue())["matches"]] == [root]
        with patch.object(detail_lookups, "normal_changes", return_value=[]):
            relist(("D2", "V2", "C2", "S2"))
        with pytest.raises(ContextError, match="complete index"):
            held("venue", "V2", "S2")
        os.environ["MDM_DATABASE_URL"] = os.environ["READ_OWNER_URL"]
        with redirect_stdout(io.StringIO()):
            assert main(["mdm", "rebuild-detail-lookup", "--limit", "1"]) == 0
            assert main(["mdm", "rebuild-detail-lookup"]) == 0
        assert [row["entity_id"] for row in held("venue", "V2", "S2")["matches"]] == [root]
    print("detail lookup proof passed")
finally:
    owner.dispose()
    runtime.dispose()
