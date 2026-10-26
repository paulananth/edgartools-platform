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

import pytest

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
TARGET = "mastering"


def declared(monkeypatch, groups=3, target=TARGET):
    """OpenFIGI's rules as declared, with answers in groups of `groups` files so the invented eight
    files make several units."""
    body = copy.deepcopy(files.source("openfigi"))
    steps = body["bookkeeping"]["targets"][target]["steps"]
    next(step for step in steps if step["name"] == "answers")["units"] = {"groups": groups}
    source = files.source
    monkeypatch.setattr(files, "source", lambda name, root=None: body if name == "openfigi" else source(name, root))
    return body


def capture(root, rewrite=True, words=("cusip", "isin")):
    """The invented files of each kind, each answer's receipt naming its request's sha256
    (`rewrite=False`: the receipts only, for the files as they are)."""
    keys = []
    root.mkdir(parents=True, exist_ok=True)
    with (root / "receipts.jsonl").open("w") as out:
        for word in words:
            kind = figi.KINDS[word][0]
            names = figi.capture(root, word) if rewrite else sorted(
                p.name for p in (root / kind).glob("*.json") if not p.name.endswith(".request.json"))
            for name in names:
                answer, request = root / kind / name, root / kind / name.replace(".json", ".request.json")
                out.write(json.dumps({"file": f"{kind}/{name}", "sha256": hashlib.sha256(answer.read_bytes()).hexdigest(),
                                      "bytes": answer.stat().st_size, "status": 200,
                                      "request_sha256": hashlib.sha256(request.read_bytes()).hexdigest()}) + "\n")
                keys.append(f"{kind}/{name}")
    return keys


def comparable(record):
    """A record less its publication (each chain names its own) and where its files were written."""
    record = {k: v for k, v in record.items() if k not in ("assertion_id", "revision", "publication_key")}
    return {**record, "provenance": {k: v for k, v in record["provenance"].items()
                                     if not any(word in k for word in ("sha256", "uri", "member", "artifact", "batch",
                                                                       "consumer", "publication"))}}


# One target over both kinds asked (ticket 138): 8 CUSIP and 8 ISIN request files, their 16
# answers in groups of 3, then one reduce, combine, record and prepare; no step pairs them.
STEPS = {"requests": 16, "answers": 6, "reduce": 1, "combine": 1, "record": 1, "prepare": 1, "merge": 1, "processed": 1}


def run_target(databases, tmp_path, body, target=TARGET):
    """Write `target`'s manifest over both kinds' invented files and drive it to complete in
    Bookkeeping under the source's own name, without MDM."""
    keys = capture(tmp_path / "capture")
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps(keys))
    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    report = write_manifest(source="openfigi", target=target, capture=str(tmp_path / "capture"),
                            documents=str(listed), capture_run="capture-1", output=str(tmp_path / "bundle"),
                            as_of="2026-10-17T00:00:00Z", revision=0, journal=MemoryJournal(), bookkeeping=book)
    for profile in WORKERS:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    declared_target = copy.deepcopy(body["bookkeeping"]["targets"][target])
    declared_target["steps"] = declared_target["steps"][:-2]  # no MDM here: the merge and the journal are Person's tests'
    rules_body = {"source": "openfigi", "bookkeeping": {"version": 2, "targets": {target: declared_target}}}
    steps = book.artifacts.json(report["manifest"])["steps"]
    assert {step: len(units) for step, units in steps.items()} == STEPS
    del steps["merge"], steps["processed"]
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    version = uuid4().hex
    saved = databases.rules.save("source", "openfigi", version, rules_body)
    databases.rules.prove("source", "openfigi", version,
                          {"digest": saved["digest"], "batch_hash": manifest["sha256"], "passed": True})
    databases.rules.activate("source", "openfigi", version)
    rules = databases.rules.resolve("source", "openfigi", root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=manifest, target=target, scope={"test": version})
    state = drive(book, rid, databases.ledger, workers=WORKERS)
    assert state["run"]["state"] == "complete", state
    return state, book


def test_the_declared_chain_gives_the_hand_built_chains_records(databases, tmp_path, monkeypatch):
    by_hand, refused_by_hand = figi.prepared_records(tmp_path / "hand")
    body = declared(monkeypatch)
    state, book = run_target(databases, tmp_path, body)

    prepared = tmp_path / "bundle" / "prepare" / "manifest.json"
    refused: dict[str, str] = {}
    found = chain.records(book.artifacts, tmp_path / "bundle" / "prepare",
                          {"uri": prepared.as_uri(), "sha256": hashlib.sha256(prepared.read_bytes()).hexdigest()},
                          figi.CODE, body["mdm"][figi.CODE]["contract"], refused=refused, key="id")
    assert {r["provenance"]["record_key"]: comparable(r) for r in found} == {
        r["provenance"]["record_key"]: comparable(r) for r in by_hand}
    assert refused == refused_by_hand
    # 5 CUSIP and 4 ISIN answers found; 8 not found of each kind, and BROKEN's bad FIGI.
    assert len(found) == len(by_hand) == 9 and len(refused) == 16
    # 16 requests, 6 answers groups, reduce, combine, record, prepare.
    assert state["counts"] == {"verified": 26}
