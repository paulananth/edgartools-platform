# 02 — Bookkeeping Checkpoint Can Outrun Silver Publish on Any Mid-Run Crash

Type: task
Status: open
Severity: high — confirmed live data-integrity risk, not hypothetical

## Question

Found while investigating whether the Bookkeeping Postgres store (Ticket
04, duckdb-retirement-cutover) could safely drive skip-on-retry
resumability for [Ticket 01](01-stream-capture-submission-bronze-snapshots.md)'s
chunking fix. It cannot, as currently wired — and the same mechanism is a
real, standing data-integrity bug independent of Ticket 01 entirely.

## Finding (confirmed via direct code reading)

`_apply_submission_snapshot_to_silver`
(`edgar_warehouse/application/warehouse_orchestrator.py:5109`) has two
durability boundaries that do not line up:

1. `bookkeeping.upsert_source_checkpoint(...)` (line ~5157) commits
   **immediately, per CIK, durably to Postgres** — independent of
   everything else in the run.
2. The actual filing content lands in `db.stage_submission(...)` — the
   **local DuckDB silver candidate file**, which is only made durable
   **once, at the very end of the whole run**, via a single
   `_publish_silver_database_with_retry(context)` call
   (`warehouse_orchestrator.py:755`).

If the task crashes between (1) and the final publish for any CIK, that
CIK's checkpoint is now durably marked "content seen" in Postgres, but the
actual filing rows were only staged in the local candidate — discarded
along with the crash.

**Why this is silent data loss, not just wasted work:** the apply logic's
skip-if-unchanged optimization compares a freshly-fetched content hash
against the checkpoint's `last_sha256`:

```python
main_checkpoint = bookkeeping.get_source_checkpoint("submissions_main", f"cik:{cik}")
main_same = (
    (not force)
    and main_checkpoint is not None
    and main_checkpoint.get("last_sha256") == main_write_record["sha256"]
)
...
if all_same:
    rows_skipped = 1 + len(pagination_payloads)
    ...  # db.stage_submission(...) is NOT called
else:
    result = db.stage_submission(...)
```

On the *next* run (a retry of the same crashed execution, or tomorrow's
`daily_incremental`), the same CIK is fetched again. If SEC hasn't changed
that company's content, the fresh hash matches the checkpoint written by
the crashed run, `main_same` evaluates `True`, and `db.stage_submission`
is skipped entirely — the code believes Silver already has this content
because the checkpoint says so. It doesn't. No error, no log signal, no
distinguishable behavior from a genuine no-op skip.

## Live exposure, right now

Execution `daily-incremental-ticket15-postfix-1788270018` OOM'd twice
today. Attempt 2 (task `4f41b6e1...`) reached 92% of its apply phase
(11,140/12,068 CIKs, per live `silver_apply_progress` logs) before dying.
Every one of those ~11,140 CIKs' `sec_source_checkpoint` rows are durably
sitting in Postgres right now, claiming today's fetched content was
captured. **None of that content reached canonical Silver** — the local
candidate holding it was discarded on OOM, and `_publish_silver_database_with_retry`
was never reached. Attempt 1 (task `cd5606da...`) exposes an unknown,
unmeasured, smaller-or-equal-sized additional set from its own progress
before OOM-ing.

Unless SEC re-files or amends something for an affected company (forcing a
genuine hash mismatch), this gap does not self-heal. It is permanent until
someone notices and force-reprocesses those CIKs (`--force`, which bypasses
the checkpoint comparison entirely).

## Why this blocks using Bookkeeping for Ticket 01's resumability idea

The original ask this investigation started from: could the chunking fix
in Ticket 01 use Bookkeeping's per-CIK sync state to let a retry skip
CIKs already done, avoiding a full restart? **Not safely, as currently
wired** — "already done" per Bookkeeping's checkpoint does not mean
"durably in canonical Silver," for exactly the reason above. Building
skip-on-retry on top of the current checkpoint semantics would not add a
new bug; it would make an *existing* one fire on every single crash
instead of only sometimes, since it would deliberately trust the same
signal that's already proven unreliable across a crash boundary.

## Not yet decided

- **Scope of current exposure.** Not yet measured: exactly which CIKs
  across both of today's crashed attempts have a checkpoint/Silver
  divergence right now, and whether any of them contain filings that
  would otherwise have been caught by `daily_incremental`'s 7-day
  lookback window (i.e., real business impact, not just a redundant
  no-op).
- **Remediation for today's exposure.** Candidates, not yet chosen: a
  targeted `--force` reprocess of the affected CIK range; a scan comparing
  `sec_source_checkpoint.last_success_at` against the last known-good
  Silver publish timestamp to identify the exact affected set; something
  else.
- **Structural fix.** The real fix is making the two durability
  boundaries agree — either checkpoint writes need to move behind the
  same publish boundary as Silver (checkpoint only commits once its
  corresponding Silver content is durably published, not eagerly per-CIK
  before that), or Silver publish needs to become incremental enough to
  match checkpoint's per-CIK commit granularity. Both are bigger changes
  than this ticket's own scope — this ticket is confirming and recording
  the finding, not designing the fix. **This should very likely be scoped
  and prioritized as its own follow-on ticket**, separate from and likely
  higher-priority than Ticket 01's memory fix, since it's a correctness
  bug already causing real (if not yet measured) data loss, versus Ticket
  01's performance/reliability bug.
- **Whether this predates today** or was newly exposed by today's
  reactivation-scale run being the first workload ever large/long-running
  enough to make a mid-run OOM likely. The bug is structural, not
  reactivation-specific — any crash at any batch size hits it the same
  way — but small daily batches crash far less often, which may explain
  why this hasn't surfaced before.

## Deliverable

- [ ] Decide remediation approach for today's already-exposed CIKs
- [ ] Decide and scope the structural fix (checkpoint-behind-publish vs.
      incremental publish) as its own ticket
- [ ] Confirm whether this affects other callers of
      `_apply_submission_snapshot_to_silver` beyond `daily_incremental`
- [ ] Full 3-axis code review once a structural fix is designed
