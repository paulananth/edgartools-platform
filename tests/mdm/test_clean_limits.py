"""The Merge Stage's bounds are stated once (`limits`) and the SQL agrees."""

import re
from pathlib import Path

from edgar_warehouse.mdm.clean import limits
from edgar_warehouse.workers import mdm_prepare

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
    assert f"octet_length(request_text) > {limits.REQUEST_BYTES}" in body
    assert f"jsonb_array_length(r->'assertions'),0) > {limits.BATCH_RECORDS}" in body
    assert f"jsonb_array_length(r->'decisions'),0) > {limits.BATCH_RECORDS}" in body


def test_the_deferred_record_bounds_equal_the_limits():
    body = function("write_batch")
    assert f"coalesce(jsonb_array_length(r->'deferred'),0)>{limits.BATCH_RECORDS} OR" in body
    assert f"coalesce(jsonb_array_length(r->'assertions'),0)>{limits.BATCH_RECORDS} THEN" in body


def test_the_match_proposal_bounds_equal_the_limits():
    body = function("record_match_proposal")
    assert f"octet_length(body_text)>{limits.PROPOSAL_INPUT_BYTES}" in body
    assert f"octet_length(b::text) > {limits.PROPOSAL_BYTES}" in body
    assert f"jsonb_array_length(caller) > {limits.BATCH_RECORDS}" in body
    assert f"jsonb_array_length(automatic) > {limits.BATCH_RECORDS}" in body


def test_prepare_cuts_a_batch_by_bytes_as_well_as_by_count():
    small = [{"n": i} for i in range(2500)]
    assert [len(b) for b in mdm_prepare._batches(small)] == [1000, 1000, 500]
    large = [{"n": i, "pad": "x" * 300_000} for i in range(10)]
    batches = mdm_prepare._batches(large)
    assert [len(b) for b in batches] == [3, 3, 3, 1]
    assert all(len(mdm_prepare._lines(b)) <= limits.BATCH_RECORD_BYTES for b in batches)
    # A record larger than the budget is a batch of its own.
    assert [len(b) for b in mdm_prepare._batches([{"pad": "x" * 2 * 1024**2}, {"n": 1}])] == [1, 1]
