Type: task
Status: open

## Question

Implement [pipeline-throughput-architecture ticket 10](../../pipeline-throughput-architecture/issues/10-decide-gold-refresh-unconditional-silver-republish.md)'s
decision: skip `_publish_silver_database_if_remote`'s expensive
`shutil.copy2` + merge + promote cycle whenever no
`PROTECTED_TABLE_REGISTRY` table in the local candidate actually differs
from what was hydrated at task start.

## Why this matters

Measured live ([ticket 07](../../pipeline-throughput-architecture/issues/07-profile-gold-refresh-stage-breakdown.md)):
this step is 35.9% of `gold-refresh`'s total wall-clock (60.65s of
169.12s) for a **structurally guaranteed no-op** -- `gold-refresh` never
writes protected tables, and its only local writes
(`pipeline_run`/`sec_sync_run`) are `EXCLUDED_OPERATIONAL_TABLES`, which
the merge loop never pulls from the candidate at all. Zero bytes of real
content move, on every single run. `gold-refresh` isn't the only command
that could hit this -- any run where nothing new arrived since the last
publish (e.g. a `daily-incremental` re-run with no new filings in its
window) pays the same unnecessary cost.

## Decision already made (ticket 10)

- **General rule, not a `gold-refresh`-specific special case.**
- **Dynamic detection, not a static command allowlist.** A hardcoded
  "commands known to be read-only" list was explicitly rejected -- it
  carries a real silent-data-loss risk if a command later gains real
  writes and its list entry isn't removed. Instead: a cheap runtime check
  of whether any `PROTECTED_TABLE_REGISTRY` table's content actually
  changed, computed fresh on every run.
- **Must check only protected tables, not the whole local file.**
  `complete_pipeline_run`/`complete_sync_run` write
  `EXCLUDED_OPERATIONAL_TABLES` bookkeeping rows on every command's local
  copy -- a naive "is the local file byte-identical to what was hydrated"
  check would never trigger and defeat the whole point.

## Implementation approach (needs design during implementation, not fully specified here)

Two workable shapes, either acceptable, pick during implementation:

1. **Row-count comparison**: cheap `SELECT COUNT(*)` per
   `PROTECTED_TABLE_REGISTRY` table, taken once right after hydration and
   again right before publish. Cheapest, but a table with the same row
   count post-hydration could theoretically have had a row replaced
   (delete+insert with different content, same count) -- verify this
   can't happen given how silver writes work (append/upsert-only, per
   CLAUDE.md's "SEC data idempotency" -- likely fine, confirm during
   implementation) before relying on count alone.
2. **Lightweight hash per protected table** (e.g. a fast aggregate
   checksum over each table's rows): slightly more expensive than a
   count, closes the gap above if it turns out to matter.

Whichever is chosen, this pre-check must be **cheap relative to the full
merge it's replacing** -- if the check itself scans full table contents
at the same cost as the merge would have, it defeats the purpose. Look at
whether `SilverDatabase` already tracks anything usable (e.g. a
last-modified/dirty marker per table from existing write paths) before
adding new bookkeeping.

## Test plan

Real DB-backed tests (per this workstream's established discipline,
tickets 67-78):
1. **No-op case**: candidate identical to canonical on all protected
   tables -- assert publish is skipped (no `copy2`, no S3 staged write,
   no promote call) and the function still returns a valid result
   consistent with "nothing changed."
2. **Real-change case**: candidate differs on at least one protected
   table -- assert the full merge/publish path still runs exactly as
   today, unchanged behavior.
3. **Excluded-table-only-change case**: candidate's only diff is in
   `pipeline_run`/`sec_sync_run` (the every-run bookkeeping write) --
   assert this alone does **not** trigger the full merge (this is the
   specific case that would have defeated a naive whole-file check).
4. **Live measurement**: run `gold-refresh` post-fix, confirm the
   35.9%/60.65s cost drops to roughly the cheap-check's own cost.

## Done when

Implemented, all test cases passing, full suite green, live measurement
confirms the no-op publish cost is eliminated for `gold-refresh` without
changing behavior for any command that genuinely writes silver data.
