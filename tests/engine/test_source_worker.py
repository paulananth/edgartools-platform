"""The real configured worker and immutable artifact store, without databases."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers import profile, source_read
from edgar_warehouse.workers.__main__ import main, runtime

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "crates/source-contract/contracts/thirteenf/contract.yaml"
FIXTURE = CONTRACT.parent / "fixtures/one-row.xml"


def task(tmp_path, store, data=None):
    contract = store.put_bytes((tmp_path / "contract.yaml").as_uri(), CONTRACT.read_bytes())
    refs = [store.put_bytes((tmp_path / f"{i}.xml").as_uri(), data or FIXTURE.read_bytes()) for i in range(2)]
    manifest = store.put(tmp_path.as_uri(), {"version": 1, "contract": contract, "artifacts": refs})
    return {"input": manifest, "output": (tmp_path / "rows.json").as_uri(), "checks": ["source.output"]}


def test_profile_executes_retries_and_verifies_two_files_with_two_workers(tmp_path, capsys):
    barrier = threading.Barrier(2)
    thread_ids = set()

    class ConcurrentArtifacts(Artifacts):
        enabled = False

        def verified(self, ref, **kwargs):
            if self.enabled and ref["uri"].endswith(".xml"):
                thread_ids.add(threading.get_ident())
                barrier.wait(timeout=10)
            return super().verified(ref, **kwargs)

    store = ConcurrentArtifacts()
    envelope = task(tmp_path, store)
    store.enabled = True
    assert profile("source.read") is source_read
    receipt = source_read.execute(envelope, store)
    assert len(thread_ids) == 2
    assert source_read.execute(envelope, store) == receipt
    checks, proofs = source_read.verify({**envelope, "candidate": receipt}, store)
    assert checks == {"source.output": True} and proofs == []
    rows = json.loads(store.verified(receipt))["artifacts"]
    assert len(rows) == 2
    assert all(item["tables"]["sec_thirteenf_holding"][0]["share_type"] == "SH" for item in rows)
    assert all(item["deferred"] == [] for item in rows)
    assert main(["describe", "source.read"]) == 0
    assert json.loads(capsys.readouterr().out)["runtime"] == runtime(source_read)
    assert any(path.suffix in {".so", ".pyd"} for path in source_read.runtime_files())


def test_worker_rejects_hash_mismatch_and_malformed_xml_without_writing_output(tmp_path):
    store = Artifacts()
    envelope = task(tmp_path, store, b"<informationTable/>junk")
    with pytest.raises(SourceRejected, match="malformed"):
        source_read.execute(envelope, store)
    assert not (tmp_path / "rows.json").exists()
    (tmp_path / "0.xml").write_bytes(b"changed")
    with pytest.raises(Blocked, match="hash mismatch"):
        source_read.execute(envelope, store)


def test_verifier_rejects_corrupt_output_and_other_destination(tmp_path):
    store = Artifacts()
    envelope = task(tmp_path, store)
    receipt = source_read.execute(envelope, store)
    (tmp_path / "rows.json").write_bytes(b"{}")
    with pytest.raises(Blocked, match="hash mismatch"):
        source_read.verify({**envelope, "candidate": receipt}, store)
    candidate = {**receipt, "sha256": hashlib.sha256(b"{}").hexdigest()}
    with pytest.raises(ValueError, match="differs"):
        source_read.verify({**envelope, "candidate": candidate}, store)
    candidate["uri"] = (tmp_path / "elsewhere.json").as_uri()
    with pytest.raises(ValueError, match="URI differs"):
        source_read.verify({**envelope, "candidate": candidate}, store)


def test_manifest_cannot_expand_the_bounded_worklist(tmp_path):
    store = Artifacts()
    envelope = task(tmp_path, store)
    manifest = store.json(envelope["input"])
    manifest["artifacts"].append(manifest["artifacts"][0])
    envelope["input"] = store.put(tmp_path.as_uri(), manifest)
    with pytest.raises(ValueError, match="bounded artifact count"):
        source_read.execute(envelope, store)
    assert not (tmp_path / "rows.json").exists()
