# Write each SEC submissions document to bronze once

Type: task
Status: open
Blocked by: none
Blocks: ticket 10, slice 4 (the bronze re-read is only as reliable as the object it names)

Opened at the operator's direction, 2026-09-25 21:10 ET. Opening it changes
no code and activates no rule.

## Problem

A Stage row names its SEC bronze object by path and sha256 (ticket 10, slice
1c). But the warehouse writes SEC submissions documents with the plain,
overwriting writer:

- `_fetch_submissions_main_snapshot` (`edgar_warehouse/application/warehouse_orchestrator.py`)
  calls `_write_bronze_object`, which calls `context.bronze_root.write_bytes`,
  not `write_immutable_bytes`.
- The key is `submissions.main.path`: CIK, the fetch **date**, and the
  document name (`dataset_path_catalog.py`, `submissions_main_path`).

So a second fetch of one CIK on the same day writes to the same key and
replaces the object an earlier receipt names. The recorded sha256 still
detects it: slice 4 treats a mismatched re-read as a blocking error. But the
older version, the only history the Stage has, is gone.

This contradicts two rules in `CLAUDE.md`: bronze is "never mutated", and
`write_immutable_bytes` is "the only writer to a canonical bronze key".

## What to decide first

Changing only the writer is not enough. SEC updates a submissions document
during the day, so a same-day re-fetch can return different bytes.
`write_immutable_bytes` would then refuse the write as a content conflict. The
choice is:

- **A. A content-addressed key** (for example the sha256 in the path or file
  name). Each version gets its own object, and nothing is overwritten or
  refused. The globs that find "any captured snapshot of this CIK" must still
  work.
- **B. Keep the date key, and refuse a different same-day version.** This
  loses the newer version, or needs a separate conflict path.
- **C. A time-stamped key** (fetch time, not date). This is like A but not
  keyed by content, so identical copies multiply.

Recommendation: A. It matches "bronze is the only history", and slice 1c's
receipts already choose one path per identical copy.

The other callers of `_write_bronze_object` (pagination documents, daily
index, and so on) need the same review. They are listed at their call sites
in `warehouse_orchestrator.py`.

## Checklist

- [x] Operator decision: **A, the content hash in the key** (operator,
  2026-09-25 21:17 ET). Each version of a document gets its own object;
  nothing is overwritten or refused.
- [ ] Change the submissions writer, and every other `_write_bronze_object`
  caller the decision covers, to write once.
- [ ] Keep the cached-snapshot lookups (`submissions_main_glob`, checkpoints)
  finding existing objects under the old and new layouts. Existing bronze is
  never rewritten.
- [ ] Tests: a same-day re-fetch with the same bytes, and one with different
  bytes, each leave every earlier receipt's object readable with its hash.
- [ ] Zero SEC requests in tests.
