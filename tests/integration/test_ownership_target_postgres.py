"""The insider ownership filings' `mastering` target through real workers on PG16 (ticket 176).

Invented SGML submissions run through Bookkeeping's claim, lease and verify path:
read (one unit a file), prepare the owners, a merge, then the five silver landings
that wait for it. The merge here is a stand-in that records itself (MDM's own
merge has its worker test); what is proven is the order: no landing can be claimed
before the merge is verified, and every landing then lands its rows in silver.
Every name and number is invented."""
import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.mdm.clean import target_manifest
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.workers import mdm_prepare, silver_land, source_read
from tests.engine.test_ownership_readings import filing
from tests.engine.test_sgml_container import document, submission
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.integration.test_mdm_merge_worker_postgres import mdm  # noqa: F401
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database
from tests.support.bookkeeping_protocol import drive
from tests.support.memory_journal import MemoryJournal

SOURCE = "sec.ownership"
FOLDER = files.ROOT / "sources" / SOURCE


def accession(n):
    return f"0000000042-26-00000{n}"


def key(n):
    return f"warehouse/bronze/filing_artifact/sec/accession={accession(n)}/{accession(n)}.txt"


def sgml(n):
    header = f"ACCESSION NUMBER:\t{accession(n)}\nFILED AS OF DATE:\t20260107\n".encode()
    return submission(document(b"form4.xml", b"<XML>\n" + filing() + b"</XML>"), header=header)


def capture(tmp_path, numbers):
    receipts = []
    for n in numbers:
        raw = sgml(n)
        path = tmp_path / "capture" / "bronze" / key(n).removeprefix("warehouse/bronze/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        receipts.append({"bytes": len(raw), "key": key(n), "sha256": hashlib.sha256(raw).hexdigest()})
    (tmp_path / "capture" / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(n) for n in numbers]))
    return {"source": SOURCE, "target": "mastering", "capture": str(tmp_path / "capture"), "documents": str(listed),
            "capture_run": "capture-1", "output": str(tmp_path / "bundle"), "as_of": "2026-11-02T00:00:00Z",
            "revision": 0, "journal": MemoryJournal()}


def test_no_landing_is_claimable_before_the_merge_and_each_then_lands_its_rows(databases, mdm, tmp_path, monkeypatch):
    real = files.source

    def small_slices(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == SOURCE:
            reading["bookkeeping"]["targets"]["mastering"]["steps"][0]["units"] = {"slices": {"bytes": 1}}
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", small_slices)
    report = target_manifest.write_manifest(**capture(tmp_path, [1, 2]))
    target = deepcopy(small_slices(SOURCE)["bookkeeping"]["targets"]["mastering"])
    assert target["steps"][-1]["name"] == "processed"
    target["steps"] = target["steps"][:-1]  # the Change Journal step has its own plan test
    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    steps = book.artifacts.json(report["manifest"])["steps"]
    del steps["processed"]
    assert len(steps["read"]) == 2  # one unit a file
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    body = {"source": f"ownership-{uuid4().hex}", "bookkeeping": {"version": 2, "targets": {"mastering": target}}}
    saved = databases.rules.save("source", body["source"], "1", body)
    databases.rules.prove("source", body["source"], "1",
                          {"digest": saved["digest"], "batch_hash": manifest["sha256"], "passed": True})
    databases.rules.activate("source", body["source"], "1")
    rules = databases.rules.resolve("source", body["source"], root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=manifest, target="mastering", scope={"test": body["source"]})

    order = []

    def merge(envelope, artifacts):
        # The read units are verified and the preparation too; only the merge stands between a landing and its claim.
        assert book.tasks(rid, "silver.land", limit=100) == []
        order.append("merge")
        return artifacts.put_bytes(envelope["output"], b"{}")

    def land(envelope, artifacts):
        order.append("land")
        return silver_land.execute(envelope, artifacts)

    workers = {"source.read": source_read, "mdm.prepare": mdm_prepare,
               "mdm.merge": SimpleNamespace(execute=merge, verify=lambda e, a: ({n: True for n in e["checks"]}, [])),
               "silver.land": SimpleNamespace(execute=land, verify=silver_land.verify)}
    for profile in workers:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")

    with silver_database(databases.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        for name in ("silver-owner.yaml", "silver-line.yaml"):
            assert silver.register(owner, spec_file(FOLDER / name, None), runtime_role=RUNTIME)["created"]
        monkeypatch.setattr(silver_land, "engines", lambda: (runtime, mdm.application))  # an empty MDM: no owner mastered
        monkeypatch.setattr(runtime, "dispose", lambda: None)
        monkeypatch.setattr(mdm.application, "dispose", lambda: None)
        state = drive(book, rid, databases.ledger, workers=workers)
        with runtime.connect() as conn:
            owners = conn.execute(text("SELECT count(*) FROM silver.insider_reporting_owner")).scalar()
            lines = conn.execute(text("SELECT line_table, count(*) FROM silver.insider_position GROUP BY 1")).all()

    assert state["run"]["state"] == "complete"
    assert state["counts"] == {"verified": 2 + 1 + 1 + 5 * 2}  # read x2, prepare, merge, five landings x2 units
    assert order == ["merge"] + ["land"] * 10  # the merge first, then every landing
    # Two filings, each: one owner, one transaction and one holding (invented).
    assert owners == 2
    assert dict(lines) == {"non_derivative_transaction": 2, "non_derivative_holding": 2}
