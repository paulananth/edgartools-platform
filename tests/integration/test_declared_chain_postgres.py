"""A declared chain on real PG16 (ticket 14, slice 2c): requests read each file
alone beside their answers, answers read in groups with each file's pair set
from its own request reading, a reduce over every answers reading, a combine,
the record read over the combine's pieces, and the preparation, all formed by
the declared writer and run by Bookkeeping's workers. Its records equal the
hand-built chain's (`test_openfigi_security`) on the same invented files.
"""
import copy
import hashlib
import json
from uuid import uuid4

from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.mdm.clean.target_manifest import write_manifest
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read
from tests.integration import test_openfigi_security as figi
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support import source_chain as chain
from tests.support.bookkeeping_protocol import drive
from tests.support.memory_journal import MemoryJournal

WORKERS = {"source.read": source_read, "source.combine": source_combine, "mdm.prepare": mdm_prepare}
LEASE = {"key": "{unit}", "leases": ["artifact:{destination}"]}
ASKED = {"from": "requests", "table": "asked", "column": "key", "value_column": "id",
         "max_input_bytes": 1048576, "max_input_rows": 1000}
STEPS = [
    {"name": "requests", "operation": "source.read", "requires": [], **LEASE,
     "checks": ["input.hash", "output.receipt", "source.output"], "units": {"each": "file"},
     "input": {"contract": "requests.yaml", "beside": {"path": "{dir}/{base}.request.json", "sha256": "request_sha256"},
               "context": {"batch": "{dir}/{base}"}}},
    {"name": "answers", "operation": "source.read", "requires": ["requests"], **LEASE,
     "checks": ["input.hash", "output.receipt", "source.output"], "units": {"groups": 3},
     "input": {"context": {"batch": "{dir}/{base}", "id_type": "cusip"}, "lookups": {"asked": ASKED}}},
    {"name": "reduce", "operation": "source.combine", "requires": ["answers"], **LEASE,
     "checks": ["input.hash", "output.receipt", "source.combined"],
     "input": {"contract": "reduce.yaml", "readings": {"answers": {"all": "answers"}}}},
    {"name": "combine", "operation": "source.combine", "requires": ["reduce"], **LEASE,
     "checks": ["input.hash", "output.receipt", "source.combined"],
     "input": {"contract": "combine.yaml", "readings": {"counts": {"step": "reduce"}}}},
    {"name": "record", "operation": "source.read", "requires": ["combine"], **LEASE,
     "checks": ["input.hash", "output.receipt", "source.output"],
     "input": {"contract": "record.yaml", "pieces": {"step": "combine"}}},
    {"name": "prepare", "operation": "mdm.prepare", "requires": ["record"], **LEASE,
     "checks": ["input.hash", "output.receipt", "mdm.prepared"],
     "input": {"keys": {"table": "security", "record_column": "record", "dataset": figi.CODE},
               "readings": {"record": {"all": "record"}}}},
    {"name": "merge", "operation": "mdm.merge", "requires": ["prepare"], "key": "{batch_id}",
     "leases": ["mdm:consumer:{consumer}"], "checks": ["input.hash", "output.receipt", "mdm.committed"]},
    {"name": "processed", "operation": "journal.record", "requires": ["merge"], **LEASE,
     "checks": ["input.hash", "output.receipt", "journal.recorded"]},
]


def declared(monkeypatch):
    """OpenFIGI's rules with this target declared, and reduce.yaml naming every answers reading once."""
    body = copy.deepcopy(files.source("openfigi"))
    body["bookkeeping"] = {"version": 2, "targets": {"mastering_cusip": {
        "steps": copy.deepcopy(STEPS), "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}}}
    source, load = files.source, files.load
    monkeypatch.setattr(files, "source", lambda name, root=None: body if name == "openfigi" else source(name, root))

    def reduce_once(path, *args, **kwargs):
        found = load(path, *args, **kwargs)
        if path.name == "reduce.yaml" and path.parent.name == "openfigi":
            found = copy.deepcopy(found)
            for group in found["reduce"]["groups"].values():
                group["source"] = ["answers"]
        return found
    monkeypatch.setattr(files, "load", reduce_once)
    return body


def capture(root, rewrite=True):
    """The invented CUSIP files, each answer's receipt naming its request's sha256 (`rewrite=False`:
    the receipts only, for the files as they are)."""
    names = figi.capture(root, "cusip") if rewrite else sorted(
        p.name for p in (root / "id_cusip").glob("*.json") if not p.name.endswith(".request.json"))
    with (root / "receipts.jsonl").open("w") as out:
        for name in names:
            answer, request = root / "id_cusip" / name, root / "id_cusip" / name.replace(".json", ".request.json")
            out.write(json.dumps({"file": f"id_cusip/{name}", "sha256": hashlib.sha256(answer.read_bytes()).hexdigest(),
                                  "bytes": answer.stat().st_size, "status": 200,
                                  "request_sha256": hashlib.sha256(request.read_bytes()).hexdigest()}) + "\n")
    return [f"id_cusip/{name}" for name in names]


def comparable(record):
    """A record less its publication (each chain names its own) and where its files were written."""
    record = {k: v for k, v in record.items() if k not in ("assertion_id", "revision", "publication_key")}
    return {**record, "provenance": {k: v for k, v in record["provenance"].items()
                                     if not any(word in k for word in ("sha256", "uri", "member", "artifact", "batch",
                                                                       "consumer", "publication"))}}


def test_the_declared_chain_gives_the_hand_built_chains_records(databases, tmp_path, monkeypatch):
    by_hand, refused_by_hand = figi.prepared_records(tmp_path / "hand")
    body = declared(monkeypatch)
    keys = capture(tmp_path / "capture")
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps(keys))
    report = write_manifest(source="openfigi", target="mastering_cusip", capture=str(tmp_path / "capture"),
                            documents=str(listed), capture_run="capture-1", output=str(tmp_path / "bundle"),
                            as_of="2026-10-17T00:00:00Z", revision=0, journal=MemoryJournal())
    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    for profile in WORKERS:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    target = copy.deepcopy(body["bookkeeping"]["targets"]["mastering_cusip"])
    target["steps"] = target["steps"][:-2]  # no MDM here: the merge and the journal are Person's tests'
    name = f"figi-{uuid4().hex}"
    rules_body = {"source": name, "bookkeeping": {"version": 2, "targets": {"mastering_cusip": target}}}
    steps = book.artifacts.json(report["manifest"])["steps"]
    assert {step: len(units) for step, units in steps.items()} == {
        "requests": 8, "answers": 3, "reduce": 1, "combine": 1, "record": 1, "prepare": 1, "merge": 1, "processed": 1}
    del steps["merge"], steps["processed"]
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    saved = databases.rules.save("source", name, "1", rules_body)
    databases.rules.prove("source", name, "1", {"digest": saved["digest"], "batch_hash": manifest["sha256"], "passed": True})
    databases.rules.activate("source", name, "1")
    rules = databases.rules.resolve("source", name, root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=manifest, target="mastering_cusip", scope={"test": name})

    state = drive(book, rid, databases.ledger, workers=WORKERS)

    assert state["run"]["state"] == "complete", state
    prepared = tmp_path / "bundle" / "prepare" / "manifest.json"
    refused: dict[str, str] = {}
    found = chain.records(book.artifacts, tmp_path / "bundle" / "prepare",
                          {"uri": prepared.as_uri(), "sha256": hashlib.sha256(prepared.read_bytes()).hexdigest()},
                          figi.CODE, body["mdm"][figi.CODE]["contract"], refused=refused, key="id")
    assert {r["provenance"]["record_key"]: comparable(r) for r in found} == {
        r["provenance"]["record_key"]: comparable(r) for r in by_hand}
    assert refused == refused_by_hand
    assert len(found) == len(by_hand) == 5 and len(refused) == 8  # five found, eight OpenFIGI did not find
    assert state["counts"] == {"verified": 15}  # 8 requests, 3 answers groups, reduce, combine, record, prepare
