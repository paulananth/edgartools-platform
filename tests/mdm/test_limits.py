"""Configured input batching does not refuse an oversized record.

Retired SQL-body copies are replaced by the real selected-engine large-payload
and chunked-key storage tests, including a request over the former 16 MiB cap.
"""

from edgar_warehouse.mdm import limits
from edgar_warehouse.workers import mdm_prepare


def _one(row):
    return mdm_prepare._lines([row])


def test_prepare_cuts_a_batch_by_bytes_as_well_as_by_count():
    small = [{"n": i} for i in range(2500)]
    assert [len(b) for b in limits.batches(small, _one)] == [1000, 1000, 500]
    # 300 KB rows: 27 fit in the 8 MiB budget (8.1 MB) and a 28th would not (8.4 MB).
    large = [{"n": i, "pad": "x" * 300_000} for i in range(40)]
    batches = limits.batches(large, _one)
    assert [len(b) for b in batches] == [27, 13]
    assert all(len(mdm_prepare._lines(b)) <= limits.BATCH_RECORD_BYTES for b in batches)
    # A record larger than the budget is a batch of its own.
    assert [len(b) for b in limits.batches([{"pad": "x" * 9 * 1024**2}, {"n": 1}], _one)] == [1, 1]


def test_a_batch_always_fits_the_file_a_worker_reads_back():
    assert limits.BATCH_RECORD_BYTES < limits.RECORDS_FILE_BYTES


def test_a_bundle_of_records_the_size_of_a_persons_submission_is_two_batches_not_twenty():
    """Each merge batch costs a claim, a session and about 25 statements, so a hosted store pays for every one:
    512 records of about 31 KB (a person's whole submissions row) are 16 MB, cut at 8 MiB."""
    bundle = [{"n": i, "pad": "x" * 31_000} for i in range(512)]
    assert len(limits.batches(bundle, _one)) == 2
