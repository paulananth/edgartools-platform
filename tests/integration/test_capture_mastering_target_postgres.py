"""SEC Person's `mastering` target on real PG16 (Issue 20 slice 20d).

Bookkeeping runs Person preparation as steps: the registered workers read the
bundle's documents, each kept whole, and prepare them as one publication. What
reaches MDM is every document unchanged, and normalizing it gives the outcome
the in-process reading gives. The merge step needs a registered MDM; the
installed proof covers it.
"""
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.mdm.clean import capture_prepare
from edgar_warehouse.mdm.clean.capture_prepare import record_shape, write_capture_manifest
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_read
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.bookkeeping_protocol import drive
from tests.support.sec_capture import document, key, write_capture

SOURCE = "sec.submissions.person"
WORKERS = {"source.read": source_read, "mdm.prepare": mdm_prepare}
PEOPLE = {1001: document(1001, "DOE JOHN", entity_type="other"), 1002: document(1002, "ROE JANE", entity_type="other"),
          320193: document(320193, "Apple Inc.")}


def bundle(tmp_path, documents=PEOPLE):
    folder, _ = write_capture(tmp_path / "capture", documents)
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(cik) for cik in documents]))
    return write_capture_manifest(source=SOURCE, capture=str(folder), documents=str(listed), capture_run="capture-1",
                                  output=str(tmp_path / "bundle"), as_of="2026-10-01T00:00:00Z", revision=0)


def run_without_merge(databases, tmp_path, book, report):
    """Submit the target as configured, less its merge step (no MDM here)."""
    for profile in WORKERS:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    target = deepcopy(files.source(SOURCE)["bookkeeping"]["targets"]["mastering"])
    assert target["steps"][-1]["name"] == "merge"
    target["steps"] = target["steps"][:-1]
    body = {"source": f"person-{uuid4().hex}", "bookkeeping": {"version": 1, "targets": {"mastering": target}}}
    steps = book.artifacts.json(report["manifest"])["steps"]
    del steps["merge"]
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    saved = databases.rules.save("source", body["source"], "1", body)
    databases.rules.prove("source", body["source"], "1",
                          {"digest": saved["digest"], "batch_hash": manifest["sha256"], "passed": True})
    databases.rules.activate("source", body["source"], "1")
    rules = databases.rules.resolve("source", body["source"], root=tmp_path.as_uri() + "/rules")
    return book.start(rules_ref=rules, inputs_ref=manifest, target="mastering", scope={"test": body["source"]})


def test_the_target_hands_mdm_every_document_whole_as_one_publication(databases, tmp_path, monkeypatch):
    monkeypatch.setattr(capture_prepare, "READ_BYTES", 1)  # every document its own reading, read in fan-in
    report = bundle(tmp_path)
    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    rid = run_without_merge(databases, tmp_path, book, report)
    state = drive(book, rid, databases.ledger, workers=WORKERS)
    assert state["run"]["state"] == "complete" and state["counts"] == {"verified": 4}  # three readings, records
    root = tmp_path / "bundle/records"
    manifest = json.loads((root / "manifest.json").read_bytes())
    found = [json.loads(line) for b in manifest["batches"] for line in (root / b["input"]["path"]).read_text().splitlines()]
    assert found == list(PEOPLE.values())  # each document unchanged, in bundle order
    publications = {json.dumps(b["input"]["publication"], sort_keys=True) for b in manifest["batches"]}
    assert publications == {json.dumps({"effective_at": None, "publication_key": report["publication"]["publication_key"],
                                        "revision": 0}, sort_keys=True)}
    assert {b["consumer"] for b in manifest["batches"]} == {report["publication"]["consumer"]}
    book.resume(rid)  # nothing is redone
    assert drive(book, rid, databases.ledger, workers=WORKERS)["counts"] == {"verified": 4}


def test_the_manifest_reads_by_receipt_and_composes_the_records(tmp_path):
    report = bundle(tmp_path)
    steps = json.loads((tmp_path / "bundle" / f"{report['manifest']['sha256']}.json").read_bytes())["steps"]
    assert {name: len(units) for name, units in steps.items()} == {"read": 1, "records": 1, "merge": 1}
    assert steps["records"][0]["input"]["compose"]["slots"]["read"] == [{"step": "read", "key": "read-0"}]
    keys = steps["records"][0]["keys"]
    assert (keys["table"], keys["record_column"], keys["dataset"], keys["revision"]) == (
        "submissions", "record", "sec.submissions.person.v1", "0")
    assert report["publication"]["publication_key"].startswith(f"capture-1:{SOURCE}:")
    assert steps["merge"][0]["input"] == {"from": {"step": "records", "key": "records"}}
    assert not list((tmp_path / "bundle").rglob("*.jsonl"))  # documents stay in the capture


def test_a_document_that_differs_from_its_receipt_is_refused(tmp_path):
    folder, _ = write_capture(tmp_path / "capture", PEOPLE)
    (folder / "bronze" / key(1001).removeprefix("warehouse/bronze/")).write_text("{}")
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(1001)]))
    with pytest.raises(Exception, match="differs from its receipt"):
        write_capture_manifest(source=SOURCE, capture=str(folder), documents=str(listed), capture_run="c",
                               output=str(tmp_path / "b"), as_of="2026-10-01T00:00:00Z", revision=0)


def test_only_a_reading_that_keeps_documents_whole_is_taken():
    assert record_shape(files.load(files.ROOT / "sources" / SOURCE / "source.yaml")) == ("submissions", "record")
    company = files.load(files.ROOT / "sources/sec.submissions.company/source.yaml")
    with pytest.raises(ValueError, match="keep each document whole"):
        record_shape(company)


def test_the_same_documents_are_one_publication_however_they_are_listed(tmp_path):
    folder, _ = write_capture(tmp_path / "capture", PEOPLE)
    found = []
    for name, order, indent in (("a", list(PEOPLE), None), ("b", list(reversed(list(PEOPLE))), 2)):
        listed = tmp_path / f"{name}.json"
        listed.write_text(json.dumps([key(cik) for cik in order], indent=indent))
        report = write_capture_manifest(source=SOURCE, capture=str(folder), documents=str(listed),
                                        capture_run="capture-1", output=str(tmp_path / name),
                                        as_of="2026-10-01T00:00:00Z", revision=0)
        steps = json.loads((tmp_path / name / f"{report['manifest']['sha256']}.json").read_bytes())["steps"]
        read = [json.loads(Path(unit["input"]["uri"].removeprefix("file://")).read_bytes())["artifacts"]
                for unit in steps["read"]]
        found.append((report["publication"], read))
    assert found[0] == found[1]  # one publication, the same documents read in the same order


def test_a_source_not_under_the_rules_is_refused(tmp_path):
    with pytest.raises(ValueError, match="No source named"):
        write_capture_manifest(source="../merge", capture=str(tmp_path), documents=str(tmp_path / "d.json"),
                               capture_run="c", output=str(tmp_path / "b"), as_of="2026-10-01T00:00:00Z", revision=0)
