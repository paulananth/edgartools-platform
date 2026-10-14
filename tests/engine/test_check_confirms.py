"""A check confirms a step's output, and redoes a sample of units (ticket 72).

`confirm` checks the inputs and contract with the step's own checks and the
written output's shape, without redoing the work. Bookkeeping pins the
worker's runtime per run and hashes the input and output; the check loop
redoes the work in full for the step's first unit in a run and for a 5% draw.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import __main__ as workers, source_combine, source_read
from tests.engine.test_source_combine import envelope as combine_task, plan, reading, table
from tests.engine.test_source_worker import task as read_task


def _rewrite(store, ref, change):
    """Write the output again with one change, under the same URI; returns its new receipt."""
    body = change(json.loads(store.verified(ref)))
    Path(urlparse(ref["uri"]).path).unlink()
    return store.put_bytes(ref["uri"], json.dumps(body, sort_keys=True, separators=(",", ":")).encode())


def _read(tmp_path):
    store = Artifacts()
    work = read_task(tmp_path, store)
    return store, work, source_read.execute(work, store)


def test_read_confirm_passes_the_written_output_without_reading_the_files(tmp_path, monkeypatch):
    store, work, receipt = _read(tmp_path)
    monkeypatch.setattr(source_read.source_engine.SourceEngine, "read",
                        lambda *a, **k: pytest.fail("confirm must not redo the work"))
    assert source_read.confirm({**work, "candidate": receipt}, store) == ({"source.output": True}, [])


@pytest.mark.parametrize("change", ["contract", "inputs", "order", "table", "rows", "deferred"])
def test_read_confirm_refuses_an_output_of_the_wrong_shape(tmp_path, change):
    store, work, receipt = _read(tmp_path)
    edits = {
        "contract": lambda b: {**b, "contract": {"uri": "file:///other.yaml", "sha256": "0" * 64}},
        "inputs": lambda b: {**b, "artifacts": b["artifacts"][:1]},
        "order": lambda b: {**b, "artifacts": [{**b["artifacts"][0], "input": {"uri": "file:///x", "sha256": "1" * 64}},
                                              b["artifacts"][1]]},
        "table": lambda b: {**b, "artifacts": [{**a, "tables": {**a["tables"], "undeclared": []}} for a in b["artifacts"]]},
        "rows": lambda b: {**b, "artifacts": [{**a, "tables": {k: ["not a row"] for k in a["tables"]}} for a in b["artifacts"]]},
        "deferred": lambda b: {**b, "artifacts": [{**a, "deferred": None} for a in b["artifacts"]]},
    }
    changed = _rewrite(store, receipt, edits[change])
    with pytest.raises(ValueError):
        source_read.confirm({**work, "candidate": changed}, store)


def test_read_confirm_refuses_another_output_uri(tmp_path):
    store, work, receipt = _read(tmp_path)
    with pytest.raises(ValueError, match="intended output"):
        source_read.confirm({**work, "candidate": {**receipt, "uri": (tmp_path / "other.json").as_uri()}}, store)


def test_a_wrong_value_passes_confirm_and_is_caught_by_the_redo(tmp_path):
    """What confirm does not see, and why a sample is still redone."""
    store, work, receipt = _read(tmp_path)

    def wrong(body):
        for artifact in body["artifacts"]:
            for rows in artifact["tables"].values():
                for row in rows:
                    row.update({k: "WRONG" for k, v in row.items() if isinstance(v, str)})
        return body

    changed = _rewrite(store, receipt, wrong)
    assert source_read.confirm({**work, "candidate": changed}, store) == ({"source.output": True}, [])
    with pytest.raises(ValueError, match="differs"):
        source_read.verify({**work, "candidate": changed}, store)


def _combine(tmp_path):
    store = Artifacts()
    ref = reading(store, tmp_path, {"companies": [{"cik": 1}, {"cik": 2}]})
    work = combine_task(store, tmp_path, plan({}, {"companies": table("main", "companies", {})}), {"main": ref})
    return store, work, source_combine.execute(work, store)


def test_combine_confirm_passes_without_combining_again(tmp_path, monkeypatch):
    store, work, receipt = _combine(tmp_path)
    import edgar_warehouse.rules.source_engine as engine
    monkeypatch.setattr(engine, "combine_tables", lambda *a, **k: pytest.fail("confirm must not combine again"))
    assert source_combine.confirm({**work, "candidate": receipt}, store) == ({source_combine.CHECK: True}, [])


@pytest.mark.parametrize("change", ["contract", "readings", "scope", "deferred"])
def test_combine_confirm_refuses_an_output_of_the_wrong_shape(tmp_path, change):
    store, work, receipt = _combine(tmp_path)
    edits = {
        "contract": lambda b: {**b, "contract": {"uri": "file:///other.json", "sha256": "0" * 64}},
        "readings": lambda b: {**b, "readings": {}},
        "scope": lambda b: {**b, "artifacts": [{**b["artifacts"][0], "input": {"uri": "file:///x", "sha256": "1" * 64}}]},
        "deferred": lambda b: {**b, "artifacts": [{**b["artifacts"][0], "deferred": [{"x": 1}]}]},
    }
    changed = _rewrite(store, receipt, edits[change])
    with pytest.raises(ValueError):
        source_combine.confirm({**work, "candidate": changed}, store)


def test_combine_confirm_refuses_a_changed_scope(tmp_path):
    store, work, receipt = _combine(tmp_path)
    scope = store.json(receipt)["artifacts"][0]["input"]
    Path(urlparse(scope["uri"]).path).write_bytes(b"{}")
    with pytest.raises(ValueError):
        source_combine.confirm({**work, "candidate": receipt}, store)


@pytest.mark.parametrize("ordinal, draw, redone", [(0, 99, True), (3, 4, True), (3, 5, False), (3, 99, False)])
def test_the_first_unit_and_a_five_percent_draw_are_redone(monkeypatch, ordinal, draw, redone):
    monkeypatch.setattr(workers.secrets, "randbelow", lambda n: draw)
    decision = workers.sample({"ordinal": ordinal})
    assert decision == {"redone": redone, "first_unit": ordinal == 0, "draw": draw, "percent": 5}


def test_the_loop_confirms_redoes_and_records_the_decision(tmp_path, monkeypatch):
    calls, admitted = [], []

    class Module:
        __file__ = workers.__file__

        @staticmethod
        def verify(v, a):
            calls.append(("verify", v["ordinal"]))
            return {"x": True}, []

        @staticmethod
        def confirm(v, a):
            calls.append(("confirm", v["ordinal"]))
            return {"x": True}, []

    units = [{"ordinal": n, "claim": {"run_id": "r", "step": "s", "key": f"k{n}", "attempt": "a"},
              "candidate": {"uri": "file:///c", "sha256": "0" * 64}, "heartbeat_seconds": 60} for n in range(3)]
    monkeypatch.setattr(workers, "load_profile", lambda name: Module)
    monkeypatch.setattr(workers.control, "verifications", lambda run, name, n: [units.pop(0)] if units else [])
    monkeypatch.setattr(workers.control, "admit", lambda envelope, report: admitted.append(report))
    monkeypatch.setattr(workers.control, "report_document",
                        lambda verification, checks, proofs, digest: {"proofs": proofs})
    monkeypatch.setattr(workers.secrets, "randbelow", lambda n: 50)
    assert workers.verify("p", "r", tmp_path.as_uri(), 10) == 0
    assert calls == [("verify", 0), ("confirm", 1), ("confirm", 2)]
    store = Artifacts()
    reports = [store.json(ref) for ref in admitted]
    decisions = [store.json(report["proofs"][-1])["sample"] for report in reports]
    assert [d["redone"] for d in decisions] == [True, False, False]


def test_a_profile_without_confirm_always_redoes(tmp_path, monkeypatch):
    calls = []

    class Module:
        __file__ = workers.__file__

        @staticmethod
        def verify(v, a):
            calls.append(v["ordinal"])
            return {"x": True}, []

    units = [{"ordinal": n, "claim": {"run_id": "r", "step": "s", "key": f"k{n}", "attempt": "a"},
              "candidate": {"uri": "file:///c", "sha256": "0" * 64}, "heartbeat_seconds": 60} for n in range(2)]
    monkeypatch.setattr(workers, "load_profile", lambda name: Module)
    monkeypatch.setattr(workers.control, "verifications", lambda run, name, n: [units.pop(0)] if units else [])
    monkeypatch.setattr(workers.control, "admit", lambda envelope, report: None)
    monkeypatch.setattr(workers.control, "report_document", lambda *a: {"proofs": a[2]})
    assert workers.verify("p", "r", tmp_path.as_uri(), 10) == 0
    assert calls == [0, 1]


def test_combine_confirm_refuses_an_undeclared_table(tmp_path):
    store, work, receipt = _combine(tmp_path)
    changed = _rewrite(store, receipt, lambda b: {**b, "artifacts": [
        {**b["artifacts"][0], "tables": {**b["artifacts"][0]["tables"], "undeclared": []}}]})
    with pytest.raises(ValueError, match="does not declare"):
        source_combine.confirm({**work, "candidate": changed}, store)


def test_reduce_confirm_passes_and_holds_its_output_bound(tmp_path):
    from tests.engine.test_source_reduction import member, partitioned, plan as reduce_plan
    store = Artifacts()
    refs = {"main": partitioned(store, tmp_path, [{"legal": [{"key": "a", "holder": "A"}, {"key": "b", "holder": "B"}]}])}
    work = combine_task(store, tmp_path, reduce_plan({"legal": member("legal")}), refs)
    receipt = source_combine.execute(work, store)
    assert source_combine.confirm({**work, "candidate": receipt}, store) == ({source_combine.CHECK: True}, [])
    # The same two rows, written for a contract that allows one.
    narrow = combine_task(store, tmp_path / "narrow", reduce_plan({"legal": member("legal")}, max_output_rows=1), refs)
    scope_ref, scope = source_combine._scope(narrow, store.json(narrow["input"]))
    store.put_bytes(scope_ref["uri"], scope)
    body = store.json(receipt)
    body["contract"], body["artifacts"][0]["input"] = store.json(narrow["input"])["contract"], scope_ref
    written = store.put_bytes(narrow["output"], json.dumps(body, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="output rows"):
        source_combine.confirm({**narrow, "candidate": written}, store)


def test_read_confirm_compares_each_inputs_context_receipt(tmp_path):
    store = Artifacts()
    contract = store.put_bytes((tmp_path / "contract.yaml").as_uri(), (Path(__file__).resolve().parents[2]
                               / "crates/source-contract/contracts/thirteenf/contract.yaml").read_bytes())
    fixture = (Path(__file__).resolve().parents[2] / "crates/source-contract/contracts/thirteenf/fixtures/one-row.xml").read_bytes()
    ref = store.put_bytes((tmp_path / "0.xml").as_uri(), fixture)
    context = store.put(tmp_path.as_uri(), {"version": 1, "input": ref, "values": {}})
    manifest = store.put(tmp_path.as_uri(), {"version": 2, "contract": contract, "artifacts": [{"input": ref, "context": context}]})
    work = {"input": manifest, "output": (tmp_path / "rows.json").as_uri(), "checks": ["source.output"]}
    receipt = source_read.execute(work, store)
    assert source_read.confirm({**work, "candidate": receipt}, store) == ({"source.output": True}, [])
    other = store.put(tmp_path.as_uri(), {"version": 1, "input": ref, "values": {"other": 1}})
    changed = _rewrite(store, receipt, lambda b: {**b, "artifacts": [{**b["artifacts"][0], "context": other}]})
    with pytest.raises(ValueError, match="in order"):
        source_read.confirm({**work, "candidate": changed}, store)


def test_a_streamed_extract_is_redone_and_recorded_as_redone(tmp_path, monkeypatch):
    from tests.engine.test_source_stream_worker import task as stream_task
    store = Artifacts()
    work = stream_task(tmp_path, store, [json.dumps({"records": [{"n": 1}]}).encode()])
    receipt = source_read.execute(work, store)
    with pytest.raises(workers.Redo):
        source_read.confirm({**work, "candidate": receipt}, store)
    admitted = []
    unit = {**work, "candidate": receipt, "ordinal": 4, "heartbeat_seconds": 60,
            "claim": {"run_id": "r", "step": "s", "key": "k", "attempt": "a"}}
    units = [unit]
    monkeypatch.setattr(workers, "load_profile", lambda name: source_read)
    monkeypatch.setattr(workers.control, "verifications", lambda run, name, n: [units.pop(0)] if units else [])
    monkeypatch.setattr(workers.control, "admit", lambda envelope, report: admitted.append(report))
    monkeypatch.setattr(workers.control, "report_document", lambda verification, checks, proofs, digest: {"proofs": proofs})
    monkeypatch.setattr(workers.secrets, "randbelow", lambda n: 50)
    assert workers.verify("source.read", "r", (tmp_path / "reports").as_uri(), 1) == 0
    decision = store.json(store.json(admitted[0])["proofs"][-1])["sample"]
    assert decision["redone"] is True and "streamed" in decision["why"]
