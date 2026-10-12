"""The Company `mastering` target on real PG16 (Issue 20 slice 20c).

Bookkeeping runs Company preparation as steps: the registered workers read the
main documents, their census keys, the catalog and the narrowed census,
combine them and prepare one publication. What reaches MDM (the records files
and their publication) equals the frozen in-process preparation's bundle. The
merge step needs a registered MDM; the installed proof covers it.
"""
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.mdm.clean.company_prepare import write_company_manifest
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from edgar_warehouse.mdm.clean import limits
from tests.mdm.test_clean_company_preparation import ACME, APPLE, CATALOG_ROWS, MSFT, PINS, census_capture, documents
from tests.support.bookkeeping_protocol import drive
from tests.support.retired_company_bundle import prepare_company_bundle
from tests.support.sec_capture import CATALOG, document, key

WORKERS = {"source.read": source_read, "source.combine": source_combine, "mdm.prepare": mdm_prepare}
CIKS = (320193, 789019, 42)


def run_without_merge(databases, tmp_path, book, report):
    """Submit the target as configured, less its merge step (no MDM here)."""
    for profile in WORKERS:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    target = deepcopy(files.source("sec.submissions.company")["bookkeeping"]["targets"]["mastering"])
    assert target["steps"][-1]["name"] == "merge"
    target["steps"] = target["steps"][:-1]
    body = {"source": f"company-{uuid4().hex}", "bookkeeping": {"version": 1, "targets": {"mastering": target}}}
    steps = book.artifacts.json(report["manifest"])["steps"]
    del steps["merge"]
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    saved = databases.rules.save("source", body["source"], "1", body)
    databases.rules.prove("source", body["source"], "1",
                          {"digest": saved["digest"], "batch_hash": manifest["sha256"], "passed": True})
    databases.rules.activate("source", body["source"], "1")
    rules = databases.rules.resolve("source", body["source"], root=tmp_path.as_uri() + "/rules")
    return book.start(rules_ref=rules, inputs_ref=manifest, target="mastering", scope={"test": body["source"]})


def test_the_mastering_target_prepares_what_the_in_process_preparation_did(databases, tmp_path):
    capture = census_capture(tmp_path, documents(), CATALOG_ROWS)
    folder, population, census = capture
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(c) for c in CIKS]))
    args = {"capture": str(folder), "documents": str(listed), "population": str(population), "catalog": CATALOG,
            "name_census": str(census), **PINS}
    report = write_company_manifest(output=str(tmp_path / "bundle"), **args)
    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    rid = run_without_merge(databases, tmp_path, book, report)
    state = drive(book, rid, databases.ledger, workers=WORKERS)
    # One main unit (3 small documents, under the byte budget), one key reading, catalog, census, combine, records.
    assert state["run"]["state"] == "complete" and state["counts"] == {"verified": 6}

    prepared = json.loads((tmp_path / "bundle/records/manifest.json").read_bytes())
    oracle_report = prepare_company_bundle(output=str(tmp_path / "oracle"), **args)
    oracle = json.loads((tmp_path / "oracle/manifest.json").read_bytes())

    def landed(manifest, root):
        """What MDM reads: each batch's records bytes, count and publication (ids aside)."""
        return [((root / b["input"]["path"]).read_bytes(), b["input"]["record_count"], b["input"]["publication"],
                 b["input"]["source_code"], b["expected_checkpoint"], b["checkpoint"]) for b in manifest["batches"]]

    assert landed(prepared, tmp_path / "bundle/records") == landed(oracle, tmp_path / "oracle")
    assert (prepared["as_of"], prepared["policy_digest"]) == (oracle["as_of"], oracle["policy_digest"])
    assert report["scope"] == oracle_report["scope"]
    assert [b["consumer"] for b in prepared["batches"]] == [report["publication"]["consumer"]]

    book.resume(rid)  # nothing is redone: every receipt and composed input is reverified
    assert drive(book, rid, databases.ledger, workers=WORKERS)["counts"] == {"verified": 6}


def test_the_manifest_freezes_documents_by_receipt_and_composes_census_and_combine(tmp_path):
    folder, population, census = census_capture(tmp_path, documents(), CATALOG_ROWS)
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(c) for c in CIKS]))
    report = write_company_manifest(capture=str(folder), documents=str(listed), population=str(population),
                                    catalog=CATALOG, name_census=str(census), output=str(tmp_path / "b"), **PINS)
    steps = json.loads(Path(report["manifest"]["uri"].removeprefix("file://")).read_bytes())["steps"]
    assert {name: len(units) for name, units in steps.items()} == {
        "main": 1, "keys": 1, "catalog": 1, "census": 1, "combine": 1, "records": 1, "merge": 1}
    census_input = steps["census"][0]["input"]["compose"]
    assert census_input["slots"]["lookups"]["compose"]["slots"]["keys"] == [{"step": "keys", "key": "keys"}]
    assert set(steps["combine"][0]["input"]["compose"]["slots"]) == {"main", "census", "catalog"}
    assert steps["merge"][0]["input"] == {"from": {"step": "records", "key": "records"}}
    assert steps["records"][0]["keys"]["revision"] == str(PINS["revision"])
    assert not list((tmp_path / "b").rglob("*.jsonl"))  # documents stay in the capture, by receipt


def mastered(databases, tmp_path, found=None):
    """The records the target prepares for a capture of `found` documents, by CIK, and the manifest."""
    folder, population, census = census_capture(tmp_path, found or documents(), CATALOG_ROWS)
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(c) for c in CIKS]))
    report = write_company_manifest(capture=str(folder), documents=str(listed), population=str(population),
                                    catalog=CATALOG, name_census=str(census), output=str(tmp_path / "bundle"), **PINS)
    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    assert drive(book, run_without_merge(databases, tmp_path, book, report), databases.ledger,
                 workers=WORKERS)["run"]["state"] == "complete"
    root = tmp_path / "bundle/records"
    manifest = json.loads((root / "manifest.json").read_bytes())
    found = {r["cik"]: r for b in manifest["batches"]
             for r in map(json.loads, (root / b["input"]["path"]).read_text().splitlines())}
    return found, manifest, folder


def test_forms_tickers_address_origin_and_census_entry_come_from_configured_readings(databases, tmp_path):
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
    assert found[APPLE]["name_census"]["leis"][0][0] == "HWUPKR0MPOU8FGXBT394"
    assert "_name_key" not in found[APPLE]


def test_main_units_are_cut_by_document_bytes_and_still_prepare_the_same_records(databases, tmp_path, monkeypatch):
    from edgar_warehouse.mdm.clean import company_prepare
    monkeypatch.setattr(company_prepare, "MAIN_READING_BYTES", 1)  # every document its own main unit
    found, _, folder = mastered(databases, tmp_path)
    (manifest,) = [p for p in (tmp_path / "bundle").glob("*.json") if len(p.stem) == 64]  # the input manifest
    steps = json.loads(manifest.read_bytes())["steps"]
    assert (len(steps["main"]), len(steps["combine"]), len(steps["keys"])) == (3, 3, 1)
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
