"""The Company `mastering` target on real PG16 (Issue 20 slice 20c).

Bookkeeping runs Company preparation as steps: the registered workers read the
main documents, their name count keys, the catalog and the narrowed name count,
combine them and prepare one publication. What reaches MDM (the records files
and their publication) equals the bundle the in-process preparation wrote before
the target replaced it (`fixtures/company-mastering-records.json`, written once).
The merge step needs a registered MDM; the installed proof covers it.

The target is planned by the generic `write_manifest` (ticket 177, slice 5): the same rules, run facts and
Name Count file the dedicated writer took, with no Company-specific code.
"""
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import frozen
import json
import pytest
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.mdm.target_manifest import write_manifest
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from edgar_warehouse.mdm import limits
from tests.mdm.test_mdm_company_preparation import ACME, APPLE, CATALOG_ROWS, MSFT, PINS, company_capture, documents
from tests.support.memory_journal import MemoryJournal
from tests.support.bookkeeping_protocol import drive
from tests.support.sec_capture import CATALOG, document, key

def plan(tmp_path, folder, output="bundle", slice_bytes=None):
    """The Company target's input manifest, planned by the generic writer over the capture's documents and catalog."""
    listed = tmp_path / f"documents-{output}.json"
    listed.write_text(json.dumps([key(c) for c in CIKS] + [CATALOG]))
    real = files.source

    def source(name, *args, **kwargs):
        reading = deepcopy(real(name, *args, **kwargs))
        if name == "sec.company" and slice_bytes is not None:
            main = next(s for s in reading["bookkeeping"]["targets"]["mastering"]["steps"] if s["name"] == "main")
            main["units"] = {"slices": {"bytes": slice_bytes}}
        return reading
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(files, "source", source)
        report = write_manifest(
            source="sec.company", target="mastering", capture=str(folder), documents=str(listed),
            capture_run=PINS["capture_run"], output=str(tmp_path / output), as_of=PINS["as_of"],
            revision=PINS["revision"], journal=MemoryJournal(),
            facts={"capture_run": PINS["capture_run"], "catalog_run": PINS["catalog_run"],
                   "observed_at": PINS["observed_at"], "load_mode": "default"})
    return report


WORKERS = {"source.read": source_read, "source.combine": source_combine, "mdm.prepare": mdm_prepare}
CIKS = (320193, 789019, 42)
EXPECTED = json.loads((Path(__file__).parent / "fixtures/company-mastering-records.json").read_text())


def run_without_merge(databases, tmp_path, book, report):
    """Submit the target as configured, less its merge step (no MDM here)."""
    for profile in WORKERS:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime")
    target = deepcopy(files.source("sec.company")["bookkeeping"]["targets"]["mastering"])
    target.pop("local", None)  # this test runs every step in the database; a local target's run starts at records
    assert [step["name"] for step in target["steps"][-2:]] == ["merge", "processed"]
    target["steps"] = target["steps"][:-2]
    body = {"source": f"company-{uuid4().hex}", "bookkeeping": {"version": 2, "targets": {"mastering": target}}}
    steps = book.artifacts.json(report["manifest"])["steps"]
    del steps["merge"], steps["processed"]
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    saved = frozen.of("source", body["source"], body)
    rules = Artifacts().put(tmp_path.as_uri() + "/rules", saved)
    return book.start(rules_ref=rules, inputs_ref=manifest, target="mastering", scope={"test": body["source"]})


def test_the_mastering_target_prepares_what_the_in_process_preparation_did(databases, tmp_path):
    folder, population = company_capture(tmp_path, documents(), CATALOG_ROWS)
    report = plan(tmp_path, folder)
    book = Bookkeeping(databases.runtime)
    rid = run_without_merge(databases, tmp_path, book, report)
    state = drive(book, rid, databases.ledger, workers=WORKERS)
    # One main unit (3 small documents, under the byte budget), catalog, combine, records.
    assert state["run"]["state"] == "complete" and state["counts"] == {"verified": 4}

    prepared = json.loads((tmp_path / "bundle/records/manifest.json").read_bytes())
    root = tmp_path / "bundle/records"
    # What MDM reads: each batch's records bytes, count and publication (ids aside).
    expected = EXPECTED
    got = [{"records_jsonl": (root / b["input"]["path"]).read_text(), "record_count": b["input"]["record_count"],
             "publication": {k: v for k, v in b["input"]["publication"].items() if k != "publication_key"},
             "source_code": b["input"]["source_code"], "expected_checkpoint": b["expected_checkpoint"],
             "checkpoint": b["checkpoint"]} for b in prepared["batches"]]
    # A bundle is its documents in key order, so the records come in key order, not the order they were listed.
    def by_cik(batch):
        lines = sorted(batch["records_jsonl"].splitlines(), key=lambda line: json.loads(line)["cik"])
        return {**batch, "records_jsonl": "\n".join(lines) + "\n"}
    assert [by_cik(b) for b in got] == [by_cik(b) for b in expected["batches"]]
    assert (prepared["as_of"], prepared["policy_digest"]) == (EXPECTED["as_of"], EXPECTED["policy_digest"])
    # Ticket 22: the publication is its documents (key and receipt), as for any source, not
    # the list file's bytes the old preparation hashed; the rest of the key is the same.
    # The generic planner names a publication by its run, source and documents (the catalog is one of them); the
    # approved runs and the Name Count's digest are in the consumer and batch ids, as for any source.
    assert report["publication"]["publication_key"].startswith("capture-1:sec.company:")
    # The bundle lists the main documents and the catalog; the scope names the run, not a Company sample.
    assert (report["scope"]["listed"], report["scope"]["forced"], report["scope"]["capture_run_id"]) == (
        len(CIKS) + 1, False, "capture-1")
    assert [b["consumer"] for b in prepared["batches"]] == [report["publication"]["consumer"]]

    book.resume(rid)  # nothing is redone: every receipt and composed input is reverified
    assert drive(book, rid, databases.ledger, workers=WORKERS)["counts"] == {"verified": 4}


def test_the_manifest_freezes_documents_by_receipt_and_composes_combine(tmp_path):
    folder, population = company_capture(tmp_path, documents(), CATALOG_ROWS)
    report = plan(tmp_path, folder, output="b")
    steps = json.loads(Path(report["manifest"]["uri"].removeprefix("file://")).read_bytes())["steps"]
    assert {name: len(units) for name, units in steps.items()} == {
        "main": 1, "catalog": 1, "combine": 1, "records": 1, "merge": 1, "processed": 1}
    assert set(steps["combine"][0]["input"]["compose"]["slots"]) == {"main", "catalog_exchange"}
    assert steps["merge"][0]["input"] == {"from": {"step": "records", "key": "records"}}
    assert steps["records"][0]["keys"]["revision"] == str(PINS["revision"])
    assert not list((tmp_path / "b").rglob("*.jsonl"))  # documents stay in the capture, by receipt


def mastered(databases, tmp_path, found=None, slice_bytes=None):
    """The records the target prepares for a capture of `found` documents, by CIK, and the manifest."""
    folder, population = company_capture(tmp_path, found or documents(), CATALOG_ROWS)
    report = plan(tmp_path, folder, slice_bytes=slice_bytes)
    book = Bookkeeping(databases.runtime)
    assert drive(book, run_without_merge(databases, tmp_path, book, report), databases.ledger,
                 workers=WORKERS)["run"]["state"] == "complete"
    root = tmp_path / "bundle/records"
    manifest = json.loads((root / "manifest.json").read_bytes())
    found = {r["cik"]: r for b in manifest["batches"]
             for r in map(json.loads, (root / b["input"]["path"]).read_text().splitlines())}
    return found, manifest, folder


def test_forms_tickers_address_and_origin_come_from_configured_readings(databases, tmp_path):
    found, _, folder = mastered(databases, tmp_path)
    assert found[APPLE]["forms"] == ["10-K", "10-Q"]
    assert found[APPLE]["tickers"] == ["AAPL", "APLE"]  # catalog rank order, listed once
    assert found[MSFT]["tickers"] == ["MSFT"] and found[ACME]["tickers"] == []
    assert found[APPLE]["business_address"]["street"] == "ONE APPLE PARK WAY"
    assert found[ACME]["business_address"]["country"] == "GB"
    assert found[APPLE]["last_sync_run_id"] == "capture-1"
    receipts = {r["key"]: r["sha256"] for r in map(json.loads, (folder / "receipts.jsonl").read_text().splitlines())}
    for cik, record in found.items():
        assert record["_origin"]["bronze"] == {"object": key(cik), "sha256": receipts[key(cik)], "locator": "$"}
        assert record["raw_object_id"] == receipts[key(cik)]
    assert "_name_key" not in found[APPLE]


def test_main_units_are_cut_by_document_bytes_and_still_prepare_the_same_records(databases, tmp_path):
    found, _, folder = mastered(databases, tmp_path, slice_bytes=1)  # every document its own main unit
    (manifest,) = [p for p in (tmp_path / "bundle").glob("*.json") if len(p.stem) == 64]  # the input manifest
    steps = json.loads(manifest.read_bytes())["steps"]
    assert (len(steps["main"]), len(steps["combine"])) == (3, 3)
    assert set(found) == set(CIKS) and found[APPLE]["tickers"] == ["AAPL", "APLE"]


def test_a_filer_without_a_business_address_carries_none(databases, tmp_path):
    found, _, _ = mastered(databases, tmp_path, documents({MSFT: document(MSFT, "MICROSOFT CORP")}))
    assert found[MSFT].get("business_address") is None


def test_the_publication_is_cut_by_the_records_byte_budget(databases, tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "BATCH_RECORD_BYTES", 1)  # past its first record, every record its own batch
    _, manifest, _ = mastered(databases, tmp_path)
    batches = manifest["batches"]
    assert [b["input"]["record_count"] for b in batches] == [1, 1, 1]
    assert [(b["expected_checkpoint"], b["checkpoint"]) for b in batches] == [(0, 1), (1, 2), (2, 3)]
    assert len({b["consumer"] for b in batches}) == 1 and len({b["batch_id"] for b in batches}) == 3
    assert len({b["input"]["publication"]["publication_key"] for b in batches}) == 1
