"""The bounds a Merge Stage batch is held to, in one place.

The SQL functions in `../migrations/` state the same numbers (`save_batch`'s
request, `record_match_proposal`'s stored body); `tests/mdm/test_clean_limits.py`
holds them equal. A batch grows on its way through the Stage: a SEC batch's
1.4 MB records file became a 6.1 MB save request (2026-10-10), so the records
of one batch are cut well below the request bound.
"""

# Assertions (with deferred records), decisions and identities in one batch.
BATCH_RECORDS = 1000
# One save request (`save_batch`, `preview_batch`).
REQUEST_BYTES = 16 * 1024**2
# One match proposal as stored.
PROPOSAL_BYTES = 16 * 1024**2
# A match proposal as sent: its `effects` are stored as their hash.
PROPOSAL_INPUT_BYTES = 64 * 1024**2
# One batch's records file, as read back by the Stage and the workers.
RECORDS_FILE_BYTES = 16 * 1024**2
# One batch manifest, as read back by the Stage and its verifier.
MANIFEST_BYTES = 32 * 1024**2
# Where mdm.prepare cuts a batch's records, as well as at BATCH_RECORDS.
BATCH_RECORD_BYTES = 1024**2


def batches(rows: list, encode) -> list[list]:
    """Rows cut into batches of at most `BATCH_RECORDS` records and, past the first record,
    `BATCH_RECORD_BYTES` (`encode(row)` is one row's bytes): a batch grows several times over
    on its way through the Merge Stage, whose request and match proposal are bounded."""
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
