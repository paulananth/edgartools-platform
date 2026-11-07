"""Synthetic checks that only admitted version-2 work contributes to quality."""

from __future__ import annotations

import json

import pytest

from edgar_warehouse.bookkeeping.clean import quality
from edgar_warehouse.control_contract import Blocked


class Artifacts:
    def __init__(self, receipts):
        self.receipts = receipts

    def verified(self, ref):
        return json.dumps(self.receipts[ref["uri"]]).encode()


class Bookkeeping:
    def __init__(self, rows, receipts, *, state="complete", expected=None):
        self.engine = object()
        self.rows = rows
        self.artifacts = Artifacts(receipts)
        self.run = {"state": state}
        self.config = {"steps": [{"name": "land", "operation": "silver.land",
                                  "checks": [quality.QUALITY_CHECK]}]}
        self.expected = expected or [{"step": "land", "key": row["unit_key"]} for row in rows]

    def _frozen(self, _run_id):
        return self.run, self.config, {}, self.expected

    def _verify_completed(self, _run_id, _config):
        raise AssertionError("quality reporting must not mutate the Bookkeeping run")


def row(unit, attempt, uri):
    return {"step": "land", "unit_key": unit, "attempt": attempt, "state": "verified",
            "receipt": {"uri": uri, "sha256": "a" * 64}}


def receipt(unit, attempt, failed):
    return {"version": 2, "quality": {"run_id": "run-a", "step": "land",
            "work_unit_ref": quality.work_unit_reference("run-a", "land", unit, attempt),
            "attempt": attempt, "table": "sample_table", "observed_at": "2026-11-06T12:00:00+00:00",
            "checks": {"valid_category": {"kind": "in_set", "failure_action": "flag",
                                             "rows_checked": 10, "rows_failed": failed}}}}


@pytest.fixture
def storage_work(monkeypatch):
    # This indirection keeps the fixture useful with different Bookkeeping doubles.
    class Holder:
        rows = []
    monkeypatch.setattr(quality.storage, "work", lambda *_args, **_kwargs: Holder.rows)
    return Holder


def test_aggregation_sums_verified_units_and_preserves_failure_action(storage_work):
    rows = [row("unit-a", "attempt-a", "memory://a"), row("unit-b", "attempt-b", "memory://b")]
    storage_work.rows = rows
    bookkeeping = Bookkeeping(rows, {"memory://a": receipt("unit-a", "attempt-a", 0),
                                     "memory://b": receipt("unit-b", "attempt-b", 2)})

    result = quality.aggregate(bookkeeping, "run-a")

    assert result["status"] == "failed"
    assert result["units_expected"] == result["units_verified"] == 2
    assert result["checks"] == [{"step": "land", "table": "sample_table", "check": "valid_category",
                                  "kind": "in_set", "failure_action": "flag", "units": 2,
                                  "rows_checked": 20, "rows_failed": 2, "status": "failed"}]
    assert {entry["work_unit_ref"] for entry in result["results"]} == {
        quality.work_unit_reference("run-a", "land", "unit-a", "attempt-a"),
        quality.work_unit_reference("run-a", "land", "unit-b", "attempt-b")}
    assert "unit-a" not in json.dumps(result)


def test_incomplete_run_keeps_all_expected_units_unknown(storage_work):
    rows = [row("unit-a", "attempt-a", "memory://a")]
    storage_work.rows = rows
    bookkeeping = Bookkeeping(rows, {"memory://a": receipt("unit-a", "attempt-a", 0)}, state="running",
                              expected=[{"step": "land", "key": "unit-a"},
                                        {"step": "land", "key": "unit-b"}])

    result = quality.aggregate(bookkeeping, "run-a")

    assert result["status"] == "unknown"
    assert result["units_expected"] == 2
    assert result["run_complete"] is False
    assert result["units_verified"] == 1
    assert result["units_unknown"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["work_unit_ref"] == quality.work_unit_reference(
        "run-a", "land", "unit-a", "attempt-a")
    assert "unit-a" not in json.dumps(result)


def test_aggregation_rejects_receipt_for_another_attempt(storage_work):
    rows = [row("unit-a", "attempt-a", "memory://a")]
    storage_work.rows = rows
    bookkeeping = Bookkeeping(rows, {"memory://a": receipt("unit-a", "stale-attempt", 0)})

    with pytest.raises(Blocked, match="different run, step, unit or attempt"):
        quality.aggregate(bookkeeping, "run-a")


def test_catalog_results_keep_historical_unit_correlation_and_unique_timestamps():
    common = {"run_id": "run-a", "step": "land", "table": "sample_table", "check": "valid_category",
              "kind": "in_set", "failure_action": "flag", "observed_at": "2026-11-06T12:00:00+00:00",
              "rows_checked": 10, "rows_failed": 1, "status": "failed", "attempt": "attempt-a"}
    summary = {"status": "failed", "units_unknown": 0, "results": [
        {**common, "work_unit_ref": "unit-ref-a"}, {**common, "work_unit_ref": "unit-ref-b"}]}

    results = quality.catalog_results(summary)["sample_table.valid_category"]

    assert len(results) == 2
    assert results[0]["at"] != results[1]["at"]
    assert "run-a" in results[0]["correlation"]
    assert "unit-ref-a" in results[0]["correlation"]
    assert "unit-ref-b" in results[1]["correlation"]
    assert "observed at 2026-11-06T12:00:00+00:00" in results[0]["correlation"]


def test_catalog_results_refuse_unknown_or_unsafe_counts():
    with pytest.raises(Blocked, match="complete, admitted"):
        quality.catalog_results({"status": "unknown", "units_unknown": 1})
    common = {"run_id": "run-a", "step": "land", "work_unit_ref": "ref", "attempt": "try",
              "table": "sample_table", "check": "valid_category", "observed_at": "2026-11-06T12:00:00Z",
              "failure_action": "flag", "rows_checked": 2**63, "rows_failed": 0}
    with pytest.raises(Blocked, match="invalid counts"):
        quality.catalog_results({"status": "passed", "units_unknown": 0, "results": [common]})
