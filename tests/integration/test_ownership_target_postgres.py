"""The insider ownership filings' `silver` target through real workers on PG16 (ticket 176).

Invented SGML submissions run through Bookkeeping's claim, lease and verify path:
read (one unit a file), then the five silver landings, with no merge and an empty
MDM. What is proven is that the silver path needs no MDM run: every landing lands
its rows, and an owner not mastered yet keeps an empty id for `silver refresh-ids`.
Every name and number is invented."""
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import frozen
import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.mdm import target_manifest
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.workers import silver_land, source_read
from tests.engine.test_ownership_readings import filing
from tests.engine.test_sgml_container import document, submission
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.mdm_database import mdm  # noqa: F401
from tests.integration.test_silver_writer_postgres import RUNTIME, silver_database
from tests.support.bookkeeping_protocol import drive
from tests.support.memory_journal import MemoryJournal

SOURCE = "sec.ownership"
FOLDER = files.sources_root() / SOURCE


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


def test_the_silver_path_lands_every_row_with_no_merge_and_no_owner_mastered(databases, mdm, tmp_path, monkeypatch):
    real = files.source

    def small_slices(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == SOURCE:
            reading["bookkeeping"]["targets"]["silver"]["steps"][0]["units"] = {"slices": {"bytes": 1}}
        return reading
    monkeypatch.setattr(target_manifest.rules_files, "source", small_slices)
    report = target_manifest.write_manifest(**{**capture(tmp_path, [1, 2]), "target": "silver"})
    target = deepcopy(small_slices(SOURCE)["bookkeeping"]["targets"]["silver"])
    assert target["steps"][-1]["name"] == "processed"
    target["steps"] = target["steps"][:-1]  # the Change Journal step has its own plan test
    book = Bookkeeping(databases.runtime)
    steps = book.artifacts.json(report["manifest"])["steps"]
    del steps["processed"]
    assert len(steps["read"]) == 2  # one unit a file
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    body = {"source": f"ownership-{uuid4().hex}", "bookkeeping": {"version": 2, "targets": {"silver": target}}}
    saved = frozen.of("source", body["source"], body)
    rules = Artifacts().put(tmp_path.as_uri() + "/rules", saved)
    rid = book.start(rules_ref=rules, inputs_ref=manifest, target="silver", scope={"test": body["source"]})

    order = []

    def land(envelope, artifacts):
        order.append("land")
        return silver_land.execute(envelope, artifacts)

    workers = {"source.read": source_read, "silver.land": SimpleNamespace(execute=land, check=silver_land.check)}
    for profile in workers:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime")

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
            unlinked = conn.execute(text("SELECT count(*) FROM silver.insider_reporting_owner WHERE person_mdm_id IS NULL")).scalar()
            lines = conn.execute(text("SELECT line_table, count(*) FROM silver.insider_position GROUP BY 1")).all()

    assert state["run"]["state"] == "complete"
    assert state["counts"] == {"verified": 2 + 5 * 2}  # read x2, five landings x2 units
    assert order == ["land"] * 10
    # Two filings, each: one owner, one transaction and one holding (invented).
    assert owners == 2
    assert unlinked == 2  # no owner mastered yet: `silver refresh-ids` fills the id after the MDM path
    assert dict(lines) == {"non_derivative_transaction": 2, "non_derivative_holding": 2}
