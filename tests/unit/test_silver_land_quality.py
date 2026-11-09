"""Synthetic receipt tests for per-work-unit silver quality evidence."""

from __future__ import annotations

import copy
import json

import pytest

from edgar_warehouse.workers import silver_land


SPEC = {
    "table": "sample_table",
    "key": ["record_key"],
    "columns": [{"name": "record_key", "type": "VARCHAR"}],
    "checks": [{"id": "valid_category", "check": "in_set", "column": "category",
                "values": ["known"], "why": "category is registered", "on_fail": "flag"},
               {"id": "allowed_tier", "check": "in_set", "column": "tier",
                "values": ["keep"], "why": "tier is allowed", "on_fail": "exception"}],
}
ROWS = [{"record_key": "synthetic-1", "category": "known", "tier": "keep"},
        {"record_key": "synthetic-2", "category": "other", "tier": "keep"},
        {"record_key": "synthetic-3", "category": "known", "tier": "drop"}]


class Artifacts:
    def __init__(self):
        self.written = {}

    def put_bytes(self, uri, data):
        self.written[uri] = data
        return {"uri": uri, "sha256": "a" * 64}

    def read(self, uri, **_):
        if uri not in self.written:
            raise ValueError("Artifact missing or unreadable")
        return self.written[uri]

    def verified(self, ref, **_):
        return self.written[ref["uri"]]


class Sink:
    def spec(self, _table):
        return SPEC


class Engine:
    def dispose(self):
        pass


def envelope(v2=True):
    requested = [silver_land.CHECK, silver_land.QUALITY_CHECK] if v2 else [silver_land.CHECK]
    return {"checks": requested, "output": "memory://receipt", "input": {"uri": "memory://input"},
            "keys": {"unit": "unit-a", "table": "sample_table", "silver": "sample_table"},
            "claim": {"run_id": "run-a", "step": "land", "key": "unit-a", "attempt": "attempt-a"},
            "candidate": {"uri": "memory://receipt", "sha256": "a" * 64}}


@pytest.fixture
def worker(monkeypatch):
    from edgar_warehouse.silver_writer import checks
    from edgar_warehouse.silver_writer import writer
    from edgar_warehouse.silver_writer.relational import DatabaseSink

    source_artifact = {"tables": {"sample_table": copy.deepcopy(ROWS)}}
    monkeypatch.setenv(silver_land.QUALITY_V2_GATE, "enabled")
    monkeypatch.setattr(silver_land, "_artifacts", lambda *_args, **_kwargs: iter([copy.deepcopy(source_artifact)]))
    monkeypatch.setattr(silver_land, "engines", lambda: (Engine(), None))
    monkeypatch.setattr(DatabaseSink, "__init__", lambda self, _engine: None)
    monkeypatch.setattr(DatabaseSink, "spec", Sink.spec)
    monkeypatch.setattr(silver_land, "_missing", lambda *_args: 0)

    def fake_land(_sink, _table, rows, _ids, *, record_quality_results=True):
        assert record_quality_results is False
        _, report = checks.run(SPEC, copy.deepcopy(rows))
        return {"rows_written": len(rows), "quality": report}

    monkeypatch.setattr(writer, "land", fake_land)
    return Artifacts()


def test_execute_keeps_real_quality_report_in_the_immutable_receipt(worker):
    result = silver_land.execute(envelope(), worker)
    receipt = json.loads(worker.written[result["uri"]])

    assert receipt["version"] == 2
    assert receipt["rows"] == 3
    assert receipt["quality"]["run_id"] == "run-a"
    assert receipt["quality"]["step"] == "land"
    assert len(receipt["quality"]["work_unit_ref"]) == 24
    assert "unit-a" not in json.dumps(receipt["quality"])
    assert "attempt-a" not in json.dumps(receipt["quality"])
    assert receipt["quality"]["rows_checked"] == 3
    assert receipt["quality"]["rows_flagged"] == 1
    assert receipt["quality"]["rows_refused"] == 1
    assert receipt["quality"]["checks"]["valid_category"] == {
        "kind": "in_set", "failure_action": "flag", "rows_checked": 3, "rows_failed": 1}
    assert receipt["quality"]["checks"]["allowed_tier"] == {
        "kind": "in_set", "failure_action": "exception", "rows_checked": 3, "rows_failed": 1}


def test_verify_recomputes_quality_and_rejects_altered_outcomes(worker):
    result = silver_land.execute(envelope(), worker)
    assert silver_land.verify(envelope(), worker) == ({"silver.landed": True, silver_land.QUALITY_CHECK: True}, [])

    receipt = json.loads(worker.written[result["uri"]])
    receipt["quality"]["checks"]["valid_category"]["rows_failed"] = 0
    worker.written[result["uri"]] = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ValueError, match="quality outcomes"):
        silver_land.verify(envelope(), worker)


def test_v2_requires_bookkeeping_load_identity(worker):
    with pytest.raises(ValueError, match="Bookkeeping run, step and unit"):
        silver_land.execute({**envelope(), "claim": {}}, worker)


def test_v2_receipt_creation_is_disabled_until_the_recovery_gate_is_set(worker, monkeypatch):
    monkeypatch.delenv(silver_land.QUALITY_V2_GATE)
    with pytest.raises(ValueError, match="disabled until recovery gates are met"):
        silver_land.execute(envelope(), worker)


def test_a_reexecuted_unit_writes_the_same_receipt_bytes(worker):
    """A unit re-executed after a lost report writes the same receipt.

    The output is immutable and named by the work unit, so the re-execution
    must reuse the observation time already written for it.
    """
    first = silver_land.execute(envelope(), worker)
    first_bytes = worker.written[first["uri"]]

    second = silver_land.execute({**envelope(), "claim": {**envelope()["claim"], "attempt": "attempt-b"}}, worker)

    assert second == first
    assert worker.written[second["uri"]] == first_bytes


def test_a_retained_receipt_of_another_unit_is_never_reused(worker):
    """A receipt retained for another unit is never taken for this one."""
    other = {**envelope(), "output": "memory://other-receipt",
             "claim": {**envelope()["claim"], "key": "unit-b"}}
    silver_land.execute(other, worker)
    retained = json.loads(worker.written["memory://other-receipt"])
    retained["quality"]["observed_at"] = "2020-01-01T00:00:00.000+00:00"
    # The other unit's receipt sits at this unit's output: it is not this unit's.
    worker.written["memory://receipt"] = json.dumps(retained, sort_keys=True, separators=(",", ":")).encode()

    result = silver_land.execute(envelope(), worker)
    receipt = json.loads(worker.written[result["uri"]])

    assert receipt["quality"]["work_unit_ref"] != retained["quality"]["work_unit_ref"]
    assert receipt["quality"]["observed_at"] != retained["quality"]["observed_at"]


def test_v1_receipt_production_remains_default(worker, monkeypatch):
    work = envelope(v2=False)
    result = silver_land.execute(work, worker)
    receipt = json.loads(worker.written[result["uri"]])
    assert receipt["version"] == 1
    assert "quality" not in receipt
    assert silver_land.verify(work, worker) == ({"silver.landed": True}, [])
