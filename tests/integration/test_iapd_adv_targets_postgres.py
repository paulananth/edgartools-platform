"""The Form ADV bulk file's two targets through real workers on PG16 (ticket 176).

An invented monthly file runs through Bookkeeping's claim, lease and verify path up to the
preparation (read, combine, record, prepare; the merge and the Change Journal have their own
tests): the filings carry their custodians, and the custodians are one record each however
many advisers name them. Every name and number is invented."""
import hashlib
import io
import json
import zipfile
from copy import deepcopy
from uuid import uuid4

import pytest

from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.mdm import target_manifest
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read
from tests.integration.test_adv_custodian_link import BASE, BD, CUSTODY, LEI, csv_text, custody, filing
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.bookkeeping_protocol import drive
from tests.support.memory_journal import MemoryJournal

WORKERS = {"source.read": source_read, "source.combine": source_combine, "mdm.prepare": mdm_prepare}
SOURCE = "iapd.adv"
KEY = "warehouse/bronze/reference/iapd_adv_bulk/2026-05/ADV_Filing_Data_20260501_20260531.zip"
# One filing naming four custody rows: the BD custodian twice, one by LEI, one by name only.
ROWS = [custody("F1", "EXAMPLE CLEARING LLC", bd=BD), custody("F1", "EXAMPLE CLEARING LLC", bd=BD),
        custody("F1", "EXAMPLE BANK NA", lei=LEI), custody("F1", "EXAMPLE TRUST CO")]
IDS = [f"bd:{BD}", f"lei:{LEI}", "name:EXAMPLE TRUST CO"]


def archive() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("IA_ADV_Base_A_20260501_20260531.csv", csv_text(BASE, [filing("F1")]))
        z.writestr("IA_Schedule_D_5K3_20260501_20260531.csv", csv_text(CUSTODY, ROWS))
    return out.getvalue()


def capture(tmp_path):
    raw = archive()
    path = tmp_path / "capture" / "bronze" / KEY.removeprefix("warehouse/bronze/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    (tmp_path / "capture" / "receipts.jsonl").write_text(
        json.dumps({"bytes": len(raw), "key": KEY, "sha256": hashlib.sha256(raw).hexdigest()}) + "\n")
    (tmp_path / "documents.json").write_text(json.dumps([KEY]))
    return {"source": SOURCE, "capture": str(tmp_path / "capture"), "documents": str(tmp_path / "documents.json"),
            "capture_run": "capture-1", "output": str(tmp_path / "bundle"), "as_of": "2026-11-02T00:00:00Z",
            "revision": 0, "journal": MemoryJournal(), "facts": {"published": "2026-05-31T00:00:00Z"}}


def prepared(databases, tmp_path, target):
    """Plan the target, run it without merge and journal, and return the prepared records."""
    report = target_manifest.write_manifest(**capture(tmp_path), target=target)
    for profile in WORKERS:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    reading = deepcopy(target_manifest.rules_files.source(SOURCE))
    plan = deepcopy(reading["bookkeeping"]["targets"][target])
    names = [s["name"] for s in plan["steps"]]
    assert names[names.index("merge"):] in (["merge", "processed"], ["merge", "land_custody", "processed"])
    plan["steps"] = plan["steps"][:names.index("merge")]  # the merge, the silver landing and the journal step have their own tests
    body = {"source": f"iapd-{uuid4().hex}", "bookkeeping": {"version": 2, "targets": {target: plan}}}
    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    steps = book.artifacts.json(report["manifest"])["steps"]
    for later in ("merge", "land_custody", "processed"):
        steps.pop(later, None)
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    saved = databases.rules.save("source", body["source"], "1", body)
    databases.rules.prove("source", body["source"], "1",
                          {"digest": saved["digest"], "batch_hash": manifest["sha256"], "passed": True})
    databases.rules.activate("source", body["source"], "1")
    rules = databases.rules.resolve("source", body["source"], root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=manifest, target=target, scope={"test": body["source"]})
    state = drive(book, rid, databases.ledger, workers=WORKERS)
    assert state["run"]["state"] == "complete"
    book.resume(rid)  # nothing is redone
    assert drive(book, rid, databases.ledger, workers=WORKERS)["counts"] == state["counts"]
    lines = (tmp_path / "bundle/prepare/records.0.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


def test_the_filing_carries_its_custodians(databases, tmp_path):
    (record,) = prepared(databases, tmp_path, "mastering")
    assert (record["filing_id"], record["crd"]) == ("F1", "999001")
    assert record["custodians"] == IDS  # the BD custodian once, however many rows name it


def test_a_custodian_named_by_several_rows_is_one_record(databases, tmp_path):
    records = prepared(databases, tmp_path, "custodians")
    assert sorted(r["custodian_id"] for r in records) == IDS  # four rows, three custodians
