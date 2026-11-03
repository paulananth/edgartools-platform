"""The 13F filings source lands each manager's 13F reports in silver (ticket 184), through real workers on
PG16: read (one unit a submissions list), then one landing a unit. Invented lists; every value is invented."""
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
from edgar_warehouse.workers import silver_land, source_read
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.integration.test_mdm_merge_worker_postgres import mdm  # noqa: F401
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database
from tests.support.bookkeeping_protocol import drive
from tests.support.memory_journal import MemoryJournal

SOURCE = "sec.thirteenf.filings"
FOLDER = files.ROOT / "sources" / SOURCE
MANAGERS = (111, 222)


def key(cik):
    return f"warehouse/bronze/submissions/sec/cik={cik}/main/2026/09/29/CIK{cik:010d}.json"


def submissions(cik):
    rows = [(f"{cik:010d}-26-000001", "13F-HR", "2026-02-10", "2025-12-31"), (f"{cik:010d}-26-000002", "10-K", "2026-02-11", "2025-12-31"),
            (f"{cik:010d}-26-000003", "13F-HR/A", "2026-03-01", "2025-12-31"), (f"{cik:010d}-26-000004", "13F-NT", "2026-02-12", "")]
    fields = ("accessionNumber", "form", "filingDate", "reportDate")
    recent = {name: [row[i] for row in rows] for i, name in enumerate(fields)}
    recent["acceptanceDateTime"] = [f"{row[2]}T16:00:00.000Z" for row in rows]
    recent["primaryDocument"] = ["primary_doc.xml"] * len(rows)
    return json.dumps({"cik": f"{cik:010d}", "filings": {"recent": recent}}).encode()


def capture(tmp_path):
    receipts = []
    for cik in MANAGERS:
        path = tmp_path / "capture" / "bronze" / key(cik).removeprefix("warehouse/bronze/")
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = submissions(cik)
        path.write_bytes(raw)
        receipts.append({"bytes": len(raw), "key": key(cik), "sha256": hashlib.sha256(raw).hexdigest()})
    (tmp_path / "capture" / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(cik) for cik in MANAGERS]))
    return {"source": SOURCE, "target": "silver", "capture": str(tmp_path / "capture"), "documents": str(listed),
            "capture_run": "capture-1", "output": str(tmp_path / "bundle"), "as_of": "2026-11-03T00:00:00Z",
            "revision": 0, "journal": MemoryJournal()}


def test_each_managers_13f_reports_land_in_silver_and_other_forms_do_not(databases, mdm, tmp_path, monkeypatch):
    real = files.source

    def small_slices(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == SOURCE:
            reading["bookkeeping"]["targets"]["silver"]["steps"][0]["units"] = {"slices": {"bytes": 1}}
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", small_slices)
    report = target_manifest.write_manifest(**capture(tmp_path))
    target = deepcopy(small_slices(SOURCE)["bookkeeping"]["targets"]["silver"])
    assert [step["name"] for step in target["steps"]] == ["filings", "land", "processed"]
    target["steps"] = target["steps"][:-1]  # the Change Journal step has its own plan test
    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    steps = book.artifacts.json(report["manifest"])["steps"]
    recorded = book.artifacts.json(steps["processed"][0]["input"])["files"]
    assert [f["key"] for f in recorded] == [key(cik) for cik in MANAGERS]  # the Change Journal notes each list
    del steps["processed"]
    assert len(steps["filings"]) == len(steps["land"]) == 2  # one unit and one landing a manager
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    body = {"source": f"filings-{uuid4().hex}", "bookkeeping": {"version": 2, "targets": {"silver": target}}}
    saved = databases.rules.save("source", body["source"], "1", body)
    databases.rules.prove("source", body["source"], "1",
                          {"digest": saved["digest"], "batch_hash": manifest["sha256"], "passed": True})
    databases.rules.activate("source", body["source"], "1")
    rules = databases.rules.resolve("source", body["source"], root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=manifest, target="silver", scope={"test": body["source"]})
    workers = {"source.read": source_read, "silver.land": SimpleNamespace(execute=silver_land.execute, verify=silver_land.verify)}
    for profile in workers:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    with silver_database(databases.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=RUNTIME)
        assert silver.register(owner, spec_file(FOLDER / "silver-filing.yaml", None), runtime_role=RUNTIME)["created"]
        monkeypatch.setattr(silver_land, "engines", lambda: (runtime, mdm.application))  # an empty MDM: no manager mastered
        monkeypatch.setattr(runtime, "dispose", lambda: None)
        monkeypatch.setattr(mdm.application, "dispose", lambda: None)
        state = drive(book, rid, databases.ledger, workers=workers)
        with runtime.connect() as conn:
            rows = list(conn.execute(text("SELECT * FROM silver.thirteenf_filing ORDER BY accession_number")).mappings())

    assert state["run"]["state"] == "complete" and state["counts"] == {"verified": 4}
    assert [(r["cik"], r["form"], str(r["report_date"] or "")) for r in rows] == [
        (111, "13F-HR", "2025-12-31"), (111, "13F-HR/A", "2025-12-31"), (111, "13F-NT", ""),
        (222, "13F-HR", "2025-12-31"), (222, "13F-HR/A", "2025-12-31"), (222, "13F-NT", "")]  # the 10-K is left out
    assert rows[0]["accession_number"] == "0000000111-26-000001" and str(rows[0]["filing_date"]) == "2026-02-10"
    assert all(r["manager_mdm_id"] is None for r in rows)  # nothing is mastered in this empty MDM
    assert not {"name", "entity_name"} & set(rows[0])  # the manager's name is the Company's
