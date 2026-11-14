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


def receipt(unit, attempt, failed, checked=10):
    return {"version": 2, "quality": {"run_id": "run-a", "step": "land",
            "work_unit_ref": quality.work_unit_reference("run-a", "land", unit),
            "table": "sample_table", "observed_at": "2026-11-06T12:00:00+00:00",
            "checks": {"valid_category": {"kind": "in_set", "failure_action": "flag",
                                             "rows_checked": checked, "rows_failed": failed}}}}


def mdm_receipt(unit, failed, checked=10):
    step = "merge"
    return {"version": 1, "quality": {"version": 1, "run_id": "run-a", "step": step,
            "work_unit_ref": quality.work_unit_reference("run-a", step, unit),
            "observed_at": "2026-11-06T12:00:00+00:00", "sources": [{"table": "sample_source.v1",
                "rule_version": "source-quality-v1", "checks": {"record_name_present": {
                    "kind": "present@1", "failure_action": "exception", "rows_checked": checked,
                    "rows_failed": failed, "rows_expected": checked, "rows_unknown": 0}}}]}}


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
        quality.work_unit_reference("run-a", "land", "unit-a"),
        quality.work_unit_reference("run-a", "land", "unit-b")}
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
        "run-a", "land", "unit-a")
    assert "unit-a" not in json.dumps(result)


def test_aggregation_rejects_receipt_for_another_unit(storage_work):
    rows = [row("unit-a", "attempt-a", "memory://a")]
    storage_work.rows = rows
    bookkeeping = Bookkeeping(rows, {"memory://a": receipt("unit-b", "attempt-b", 0)})

    with pytest.raises(Blocked, match="different run, step or unit"):
        quality.aggregate(bookkeeping, "run-a")


def test_mdm_units_project_to_one_stable_per_run_case_result(storage_work):
    rows = [row("unit-a", "attempt-a", "memory://a"), row("unit-b", "attempt-b", "memory://b")]
    storage_work.rows = [{**item, "step": "merge"} for item in rows]
    bookkeeping = Bookkeeping(rows, {"memory://a": mdm_receipt("unit-a", 0),
                                     "memory://b": mdm_receipt("unit-b", 1)})
    bookkeeping.config = {"steps": [{"name": "merge", "operation": "mastering.merge",
                                     "checks": ["mdm.quality.evidence.v1"]}]}
    bookkeeping.expected = [{"step": "merge", "key": "unit-a"}, {"step": "merge", "key": "unit-b"}]

    summary = quality.aggregate(bookkeeping, "run-a")
    entries = quality.catalog_results(summary)["sample_source.v1.record_name_present"]

    assert summary["status"] == "failed"
    assert len(summary["results"]) == len(entries) == 1
    assert entries[0]["rows_checked"] == 20
    assert entries[0]["rows_failed"] == 1
    assert entries[0]["rule_version"] == "source-quality-v1"
    assert entries[0]["at"] == "2026-11-06T12:00:00.000+00:00"


def test_duplicate_aggregated_case_result_is_rejected_instead_of_moving_timestamp():
    common = {"run_id": "run-a", "step": "merge", "attempt": "aggregate",
              "table": "sample_source.v1", "check": "record_name_present", "kind": "present@1",
              "failure_action": "exception", "observed_at": "2026-11-06T12:00:00+00:00",
              "rows_checked": 1, "rows_failed": 0, "status": "passed"}
    summary = {"status": "passed", "results": [
        {**common, "work_unit_ref": "aggregate-ref-a"}, {**common, "work_unit_ref": "aggregate-ref-b"}]}

    with pytest.raises(Blocked, match="collides with another result"):
        quality.catalog_results(summary)


def test_missing_mdm_unit_projects_verified_counts_as_unknown(storage_work):
    item = {**row("unit-a", "attempt-a", "memory://a"), "step": "merge"}
    storage_work.rows = [item]
    bookkeeping = Bookkeeping(storage_work.rows, {"memory://a": mdm_receipt("unit-a", 0)}, state="running",
                              expected=[{"step": "merge", "key": "unit-a"},
                                        {"step": "merge", "key": "unit-b"}])
    bookkeeping.config = {"steps": [{"name": "merge", "operation": "mastering.merge",
                                     "checks": ["mdm.quality.evidence.v1"]}]}

    summary = quality.aggregate(bookkeeping, "run-a")
    entry = quality.catalog_results(summary)["sample_source.v1.record_name_present"][0]

    assert summary["status"] == "unknown"
    assert entry["status"] == "unknown"
    assert entry["rows_checked"] == 10
    assert entry["units_unknown"] == 1


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


def test_catalog_results_publish_verified_counts_as_aborted_when_evidence_is_unknown():
    result = {"run_id": "run-a", "step": "land", "work_unit_ref": "ref", "attempt": "try",
              "table": "sample_table", "check": "valid_category", "observed_at": "2026-11-06T12:00:00Z",
              "failure_action": "flag", "rows_checked": 10, "rows_failed": 1, "status": "unknown",
              "rows_unknown": 2, "units_unknown": 1}
    entry = quality.catalog_results({"status": "unknown", "units_unknown": 1,
                                     "results": [result]})["sample_table.valid_category"][0]
    assert entry["status"] == "unknown"
    assert entry["rows_checked"] == 10
    assert entry["rows_failed"] == 1
    assert entry["rows_unknown"] == 2
    common = {"run_id": "run-a", "step": "land", "work_unit_ref": "ref", "attempt": "try",
              "table": "sample_table", "check": "valid_category", "observed_at": "2026-11-06T12:00:00Z",
              "failure_action": "flag", "rows_checked": 2**63, "rows_failed": 0}
    with pytest.raises(Blocked, match="invalid counts"):
        quality.catalog_results({"status": "passed", "units_unknown": 0, "results": [common]})


@pytest.mark.parametrize("checked, failed", [(10.0, 0), (10.5, 1), (True, False)],
                         ids=["whole float", "fraction", "bool"])
def test_catalog_results_refuse_a_count_that_is_not_an_exact_integer(checked, failed):
    """A count that arrived as a float or a bool is refused, not rounded into an integer."""
    result = {"run_id": "run-a", "step": "land", "work_unit_ref": "ref", "attempt": "try",
              "table": "sample_table", "check": "valid_category", "observed_at": "2026-11-06T12:00:00Z",
              "failure_action": "flag", "rows_checked": checked, "rows_failed": failed}

    with pytest.raises(Blocked, match="invalid counts"):
        quality.catalog_results({"status": "passed", "units_unknown": 0, "results": [result]})


def test_catalog_results_keep_the_largest_signed_64_bit_count_exact():
    """The widest count a signed 64-bit column holds survives whole, not rounded."""
    result = {"run_id": "run-a", "step": "land", "work_unit_ref": "ref", "attempt": "try",
              "table": "sample_table", "check": "valid_category", "observed_at": "2026-11-06T12:00:00Z",
              "failure_action": "flag", "rows_checked": 2**63 - 1, "rows_failed": 0}

    entry = quality.catalog_results(
        {"status": "passed", "units_unknown": 0, "results": [result]})["sample_table.valid_category"][0]

    assert entry["rows_checked"] == 2**63 - 1
    assert type(entry["rows_checked"]) is int


def test_aggregation_refuses_a_sum_that_would_overflow_signed_64_bit_storage(storage_work):
    """Two units whose counts together exceed a signed 64-bit column are refused."""
    widest = 2**63 - 1
    rows = [row("unit-a", "attempt-a", "memory://a"), row("unit-b", "attempt-b", "memory://b")]
    storage_work.rows = rows
    bookkeeping = Bookkeeping(rows, {"memory://a": receipt("unit-a", "attempt-a", 0, checked=widest),
                                     "memory://b": receipt("unit-b", "attempt-b", 0, checked=1)})

    with pytest.raises(Blocked, match="exceed signed 64-bit"):
        quality.aggregate(bookkeeping, "run-a")
