Type: task
Status: open

## Question

`reduce_identity_refresh` (`edgar_warehouse/application/identity_refresh_publication.py:187-209`)
fetches every reference/delta object from S3 **twice** per reducer
attempt. Should it keep the bytes from the first fetch instead of
re-fetching?

## Root cause

Found via a fresh `/gof-refactor-reviewer` pass while resolving
[pipeline-throughput-architecture ticket 05](../../pipeline-throughput-architecture/issues/05-decide-silver-merge-storage-path.md).
Lines 187-189 call `_read_verified` on the reference snapshot and every
batch delta purely to checksum-verify them before the merge loop starts --
the returned bytes are discarded immediately (not stored). The merge loop
itself (line 209, `candidate.write_bytes(_read_verified(storage_root,
relative, expected_sha))`) then calls `_read_verified` **again** on the
exact same paths to get bytes for the actual write. Every reducer attempt
(up to `max_attempts=3` on a promotion conflict) re-downloads the full
reference + delta set twice.

This is the same finding an earlier session (before context compaction lost
its output) had already identified -- independently reconfirmed via a fresh
review this session.

## Scale

Observed live: reference + 3 batch deltas (~127MB combined for the deltas
alone, per the run this was found against). Not huge at current data
volume, but a clean, real, unforced cost -- doubling S3 fetch time for the
whole reference+delta set on every single reducer attempt.

## Fix

Capture and hold the verified bytes from the first `_read_verified` call
(lines 187-189) instead of discarding them; pass those bytes into the
merge loop instead of re-calling `_read_verified` at line 209. No change to
merge/conflict-detection logic at all -- purely removes a redundant read.

## Done when

Fixed, with a test asserting each reference/delta object is read from
storage exactly once per reducer attempt (not twice), following this
workstream's real-data/DB-backed test discipline (tickets 67-72).
