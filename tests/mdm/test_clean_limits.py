"""Configured input batching does not refuse an oversized record.

Retired SQL-body copies are replaced by the real selected-engine large-payload
and chunked-key storage tests, including a request over the former 16 MiB cap.
"""

from edgar_warehouse.mdm.clean import limits
from edgar_warehouse.workers import mdm_prepare


def _one(row):
    return mdm_prepare._lines([row])


def test_prepare_cuts_a_batch_by_bytes_as_well_as_by_count():
    small = [{"n": i} for i in range(2500)]
    assert [len(b) for b in limits.batches(small, _one)] == [1000, 1000, 500]
    large = [{"n": i, "pad": "x" * 300_000} for i in range(10)]
    batches = limits.batches(large, _one)
    assert [len(b) for b in batches] == [3, 3, 3, 1]
    assert all(len(mdm_prepare._lines(b)) <= limits.BATCH_RECORD_BYTES for b in batches)
    # A record larger than the budget is a batch of its own.
    assert [len(b) for b in limits.batches([{"pad": "x" * 2 * 1024**2}, {"n": 1}], _one)] == [1, 1]
