"""How a run's records are cut into batches is stated once (`limits`) and the SQL
agrees; the Merge Stage refuses nothing by size (019)."""

import re
from pathlib import Path

from edgar_warehouse.mdm.clean import limits
from edgar_warehouse.workers import mdm_prepare


def _one(row):
    return mdm_prepare._lines([row])


MIGRATIONS = Path(limits.__file__).parents[1] / "migrations"


def function(name: str) -> str:
    """The latest body of an SQL function across the migrations."""
    body = None
    for path in sorted(MIGRATIONS.glob("*.sql")):
        source = path.read_text()
        for match in re.finditer(rf"CREATE (?:OR REPLACE )?FUNCTION mdm\.{name}\(", source):
            body = source[match.start():source.index("$$;\n", match.start())]
    assert body is not None, name
    return body


def test_the_save_request_bounds_equal_the_limits():
    body = function("write_batch")
    assert f"jsonb_array_length(r->'assertions'),0) > {limits.BATCH_RECORDS}" in body
    assert f"jsonb_array_length(r->'decisions'),0) > {limits.BATCH_RECORDS}" in body


def test_the_deferred_record_bounds_equal_the_limits():
    body = function("write_batch")
    assert f"coalesce(jsonb_array_length(r->'deferred'),0)>{limits.BATCH_RECORDS} OR" in body
    assert f"coalesce(jsonb_array_length(r->'assertions'),0)>{limits.BATCH_RECORDS} THEN" in body


def test_the_merge_stage_has_no_size_cap():
    """Operator, 2026-10-14: "merge stage should have no limit"."""
    for name in ("write_batch", "record_match_proposal", "match_proposal_snapshot"):
        body = function(name)
        assert "octet_length" not in body and "10001" not in body and "> 10000" not in body, name


def test_the_match_proposal_bounds_equal_the_limits():
    body = function("record_match_proposal")
    assert f"jsonb_array_length(caller) > {limits.BATCH_RECORDS}" in body
    assert f"jsonb_array_length(automatic) > {limits.BATCH_RECORDS}" in body


def test_prepare_cuts_a_batch_by_bytes_as_well_as_by_count():
    small = [{"n": i} for i in range(2500)]
    assert [len(b) for b in limits.batches(small, _one)] == [1000, 1000, 500]
    large = [{"n": i, "pad": "x" * 300_000} for i in range(10)]
    batches = limits.batches(large, _one)
    assert [len(b) for b in batches] == [3, 3, 3, 1]
    assert all(len(mdm_prepare._lines(b)) <= limits.BATCH_RECORD_BYTES for b in batches)
    # A record larger than the budget is a batch of its own.
    assert [len(b) for b in limits.batches([{"pad": "x" * 2 * 1024**2}, {"n": 1}], _one)] == [1, 1]
