"""A steward splits a merge through the real Merge Stage (ticket 142), on the engine the test selects:
a preview changes nothing, the confirmed split returns both masters, and a second split is refused."""

import os
import runpy
from uuid import uuid4

os.environ["READ_CASE"] = os.environ.get("READ_BASE_CASE", "join")
g = runpy.run_module("tests.storage_adapters.record_read_scenarios")

from edgar_warehouse.mdm import steward
from edgar_warehouse.mdm.evidence import decision
from edgar_warehouse.mdm.merge import MergeStage
from edgar_warehouse.mdm.record_reads import RecordReader
from edgar_warehouse.mdm.store import Conflict, Store
from tests.support.old_master_ids import OldIds as MdmIds

runtime = g["runtime"]
kind, secondary = g["KIND"], g["SECONDARY"]
root = g["master"]["entity_id"]
ids = MdmIds(runtime)
store = Store(runtime)
stage = MergeStage(store)
position = 0


def apply(**parts):
    global position
    position += 1
    return stage.apply(batch_id="invented-steward-" + str(position), run_id=str(uuid4()),
                       policy_digest=g["seed_pin"], consumer="invented-steward-seed",
                       expected_checkpoint=position - 1, checkpoint=position, as_of=g["AS_OF"], **parts)


try:
    reading = g["record"]("later", secondary, identifiers={})
    identity, bind = g["identity"](reading, "2026-01-02T00:00:00Z")
    apply(assertions=[reading], identities=[identity], decisions=[bind])
    other = identity["entity_id"]
    verdict = decision("merge", actor="fixture", reason="invented rule merge", at="2026-02-01T00:00:00Z",
                       left=root, right=other)
    apply(decisions=[verdict])
    merge_id = verdict["decision_id"]
    assert ids(secondary, kind, {"two", "later"}) == {"two": root, "later": root}  # consolidated

    words = {"actor": "Sam", "reason": "two different issuers", "at": "2026-03-01T00:00:00Z"}
    shown = steward.split(store, merge_id=merge_id, **words)
    assert shown["written"] is False and (shown["left"], shown["right"]) == (root, other)
    assert ids(secondary, kind, {"two", "later"}) == {"two": root, "later": root}  # a preview writes nothing

    done = steward.split(store, merge_id=merge_id, confirm=True, **words)
    assert done["written"] is True and done["by"] == "Sam" and done["reason"] == "two different issuers"
    assert ids(secondary, kind, {"two", "later"}) == {"two": root, "later": other}  # both masters return

    from edgar_warehouse.mdm.prepared_registry import require_installed

    with runtime.connect() as conn:
        reader = RecordReader(require_installed(conn), connection=conn)
        kept = reader.inputs([("decision", done["decision"])])["decision", done["decision"]]
        related = [d["decision_id"] for d in reader.related_decisions([merge_id])]
    assert (kept["operation"], kept["target"], kept["actor"]) == ("reverse", merge_id, "Sam")  # a retained decision
    assert done["decision"] in related  # found from the merge it names
    with runtime.connect() as conn:  # the agent context shows the split and its exclusion on both masters
        reader = RecordReader(require_installed(conn), connection=conn)
        for master, partner in ((root, other), (other, root)):
            assert steward.splits_of(reader, master) == [{
                "merge": merge_id, "split_from": partner, "by": "Sam", "reason": "two different issuers",
                "at": "2026-03-01T00:00:00+00:00", "excluded": True}], master

    for again in ({}, {"confirm": True}):
        try:
            steward.split(store, merge_id=merge_id, **words, **again)
        except Conflict as error:
            assert "already split" in str(error)
        else:
            raise AssertionError("a split merge was split twice")
    try:
        steward.split(store, merge_id="0" * 64, **words)
    except Conflict as error:
        assert "holds no decision" in str(error)
    else:
        raise AssertionError("a merge MDM never held was split")
    print("steward split proof passed")
finally:
    runtime.dispose()
