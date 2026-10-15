"""How a run's records are cut into Merge Stage batches, in one place.

The Merge Stage refuses nothing by size (operator, 2026-10-14: "merge stage
should have no limit"; migration 019): its closure, save request and match
proposal have no cap. These numbers only divide the input: `mdm.prepare` cuts
a run's records into batches, and `write_batch` states the same record count
(`tests/mdm/test_clean_limits.py` holds them equal). The file bounds are what
the workers read back of one batch's records and manifest.
"""

# Assertions (with deferred records), decisions and identities in one batch.
BATCH_RECORDS = 1000
# One batch's records file, as read back by the Stage and the workers.
RECORDS_FILE_BYTES = 16 * 1024**2
# One batch manifest, as read back by the Stage and its verifier.
MANIFEST_BYTES = 32 * 1024**2
# Where mdm.prepare cuts a batch's records, as well as at BATCH_RECORDS.
BATCH_RECORD_BYTES = 1024**2


def batches(rows: list, encode) -> list[list]:
    """Rows cut into batches of at most `BATCH_RECORDS` records and, past the first record,
    `BATCH_RECORD_BYTES` (`encode(row)` is one row's bytes), so each batch stays small."""
    found, current, size = [], [], 0
    for row in rows:
        length = len(encode(row))
        if current and (len(current) == BATCH_RECORDS or size + length > BATCH_RECORD_BYTES):
            found.append(current)
            current, size = [], 0
        current.append(row)
        size += length
    if current:
        found.append(current)
    return found
