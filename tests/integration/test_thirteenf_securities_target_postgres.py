"""The 13F Securities' `mastering` target through real workers on PG16 (ticket 172).

Invented information tables run through Bookkeeping's claim, lease and verify
path: read (one unit per file), reduce over every unit, combine, record and
prepare. No MDM here, so the merge and journal steps are left out; the plan
test covers them. Every name and number is invented."""
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import frozen
import hashlib
import json
from copy import deepcopy
from uuid import uuid4

from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.mdm import target_manifest
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.bookkeeping_protocol import drive
from tests.support.memory_journal import MemoryJournal

WORKERS = {"source.read": source_read, "source.combine": source_combine, "mdm.prepare": mdm_prepare}
SOURCE = "sec.thirteenf.securities"
# Invented CUSIPs: the first two have valid check digits, the third does not.
GOOD, ALSO, BAD = "ZZ0000906", "ZZ0000914", "ZZ0000999"


def table(*rows):
    body = "".join(f"<infoTable><nameOfIssuer>{name}</nameOfIssuer><titleOfClass>COM</titleOfClass>"
                   f"<cusip>{cusip}</cusip><value>1</value></infoTable>" for cusip, name in rows)
    return f"<informationTable>{body}</informationTable>".encode()


def key(n):
    return f"warehouse/bronze/thirteenf_infotable/sec/accession=0000000042-26-00000{n}/infotable.xml"


def capture(tmp_path, tables):
    receipts = []
    for n, raw in enumerate(tables, 1):
        path = tmp_path / "capture" / "bronze" / key(n).removeprefix("warehouse/bronze/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        receipts.append({"bytes": len(raw), "key": key(n), "sha256": hashlib.sha256(raw).hexdigest()})
    (tmp_path / "capture" / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(n) for n in range(1, len(tables) + 1)]))
    return {"source": SOURCE, "target": "mastering", "capture": str(tmp_path / "capture"), "documents": str(listed),
            "capture_run": "capture-1", "output": str(tmp_path / "bundle"), "as_of": "2026-11-02T00:00:00Z",
            "revision": 0, "journal": MemoryJournal()}


def run(databases, tmp_path, monkeypatch, tables):
    """Plan the target with one read unit per file, run it without merge and journal; return the book and run."""
    real = files.source
    def small_slices(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == SOURCE:
            reading["bookkeeping"]["targets"]["mastering"]["steps"][0]["units"] = {"slices": {"bytes": 1}}
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", small_slices)
    report = target_manifest.write_manifest(**capture(tmp_path, tables))
    for profile in WORKERS:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime")
    target = deepcopy(small_slices(SOURCE)["bookkeeping"]["targets"]["mastering"])
    assert [step["name"] for step in target["steps"][-3:]] == ["merge", "land_holding", "processed"]
    target["steps"] = target["steps"][:-3]  # the merge, the silver landing (its own test) and the journal
    body = {"source": f"thirteenf-{uuid4().hex}", "bookkeeping": {"version": 2, "targets": {"mastering": target}}}
    book = Bookkeeping(databases.runtime)
    steps = book.artifacts.json(report["manifest"])["steps"]
    del steps["merge"], steps["land_holding"], steps["processed"]
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    saved = frozen.of("source", body["source"], body)
    rules = Artifacts().put(tmp_path.as_uri() + "/rules", saved)
    rid = book.start(rules_ref=rules, inputs_ref=manifest, target="mastering", scope={"test": body["source"]})
    return book, rid, steps


def test_the_target_reduces_every_read_unit_and_prepares_one_record_per_cusip(databases, tmp_path, monkeypatch):
    tables = [table((GOOD, "EXAMPLE CORP"), (ALSO, "OTHER CORP")), table((GOOD, "EXAMPLE CORP"), (BAD, "ODD CORP")),
              table((ALSO, "OTHER CORP"))]
    book, rid, steps = run(databases, tmp_path, monkeypatch, tables)
    assert len(steps["read"]) == 3  # one unit a file
    state = drive(book, rid, databases.ledger, workers=WORKERS)
    assert state["run"]["state"] == "complete"
    assert state["counts"] == {"verified": 3 + 1 + 1 + 1 + 1}  # read x3, reduce, combine, record, prepare
    lines = (tmp_path / "bundle/prepare/records.0.jsonl").read_text().splitlines()
    # One record a CUSIP over all three units, a CUSIP filed in two files counts both holdings; the bad check digit is
    # kept for the Dataset Contract to set aside, not dropped here.
    assert {r["cusip"]: r["holdings"] for r in map(json.loads, lines)} == {GOOD: 2, ALSO: 2, BAD: 1}
    book.resume(rid)  # nothing is redone: every receipt and composed input is reverified
    assert drive(book, rid, databases.ledger, workers=WORKERS)["counts"] == state["counts"]
