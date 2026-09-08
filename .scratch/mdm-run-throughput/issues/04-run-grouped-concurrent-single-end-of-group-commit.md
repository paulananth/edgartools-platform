Type: task
Status: claimed

**Spawned by:** live production evidence during the mdm-skip-if-unchanged-batch
Ticket 03 verification run (`mdm-mastering-batchfix-verify-1788823225`, 2026-09-07).
That run's own goal (measuring the batching fix's wall-clock win on `run_companies`)
succeeded decisively -- company resolution: 77s for 50,735 rows, ~23x faster than the
37.7min pre-fix baseline. This ticket is a second, independent, unrelated finding
surfaced while investigating why the same run's security domain appeared to stall.

## Question

Should `MDMPipeline._run_grouped_concurrent`'s per-group worker (`_process_group`,
`edgar_warehouse/mdm/pipeline.py`) commit periodically within a group's row loop,
instead of only once at the very end of the whole group?

## Context

Live evidence, gathered via direct queries against prod MDM Postgres (not assumed):

- The verification run wrote 2,404 rows across 226 distinct entities to
  `mdm_entity_attribute_stage` in a healthy 4-minute burst (23:21-23:25 UTC) --
  genuine, broad progress, not stuck.
- At 23:25 UTC, **all writes stopped completely** for the remaining ~23 minutes
  until the run was manually stopped (23:48 UTC).
- CloudWatch showed `SELECT`/`UPDATE` SQL activity (matching
  `run_survivorship_for_entity`'s shape: select all candidates for one
  `(entity_id, field_name)`, pick a winner, update `was_selected`) continuing the
  entire time, unchanged in shape, until the moment the task was stopped.
- `run_survivorship_for_entity` is called only from `resolve_one` in
  `company.py`/`security.py`/`person.py` -- no other caller exists. Company had
  already fully completed (confirmed via its own `mdm_company_resolution_completed`
  event). This left `security` as the only domain that could be generating this
  traffic.
- `_process_group` (`_run_grouped_concurrent`'s per-group worker) calls
  `worker_session.commit()` exactly once, after its entire `for row in
  group_rows:` loop finishes -- mirroring `run_companies`' `_resolve_row`, which
  also commits once per unit of work. But `run_companies`' unit of work is always
  exactly one row; `_run_grouped_concurrent`'s unit of work is an entire GROUP
  (all rows sharing a `canonical_title`/`owner_cik`), which can be unboundedly
  large. The same "commit once per unit of work" pattern that's correct for
  company becomes a real gap here: one oversized group (one hyper-popular
  security's canonical_title, with a large number of genuinely distinct
  ownership-transaction rows) can run for tens of minutes on one worker thread,
  entirely invisible to any external observer (nothing it does is committed,
  hence nothing is visible to another session's query) and, if interrupted
  (deploy, timeout, or an operator stopping the execution -- as happened live
  here), 100% of that group's progress is lost.

**A prior, disproven hypothesis, kept here for the record:** the first theory
was that Ticket 03's batch-snapshot `_skip_if_unchanged` prefetch had broken a
"self-healing" skip for literal duplicate rows within one batch. Directly querying
MDM Postgres disproved this: the specific entity first suspected
(`a31e1bdf-523e-4911-bc5b-413e8103376c`, showing a frozen candidate count of 2753)
received **zero writes during the entire verification run** -- its data was stale,
from an earlier, unrelated run. The real mechanism is the one described above:
whichever group was still running remained fully invisible until it either
finished or was interrupted, which is why a live query couldn't distinguish "still
correctly working" from "stuck" without first correcting for this commit-visibility
gap.

**This is the same recurring shape already fixed twice in this exact file**
(`git log` evidence): `869003da` (batch `MANAGES_FUND` priming by adviser CRD
instead of the whole type) and `1e56a106`/`fa8eb4b6` (the same fix mirrored for
`INSTITUTIONAL_HOLDS`) -- "one outlier entity overwhelms an unbounded unit of
work." Distinguished from those two, though: those fixed a *memory* problem (an
unscoped read materializing too much at once); this is a *durability/visibility*
problem on the write side (an unboundedly long uncommitted transaction) --
`/gof-refactor-reviewer` confirmed these are different costs and the fix should
not be conflated with the read-batching pattern those two commits used.

## Answer

**Fix (implemented, corrected after a second review pass -- see below):**
`_process_group` now tracks a local, per-group row counter (separate from the
existing shared/locked `processed` counter used only for progress-log cadence)
and calls `worker_session.commit()` every `commit_interval` rows within the
loop, in addition to the existing final commit after the loop completes.

**A first version of this fix reused `log_interval` for the commit checkpoint
and was itself a real bug, caught by a `/gof-refactor-reviewer` pass on the
diff before commit (not just the pre-code design consult):** `log_interval`
is `_progress_log_interval(len(rows))`, scaled from the ENTIRE domain's row
count (confirmed live: `run_securities`' security domain was still processing
71,253+ rows and counting when this was checked), not any single group's
size. A single group would need to exceed 1/8 of the whole domain's rows
before ever triggering a periodic commit under that design -- observed live
group sizes top out around 5,000 rows, so the original fix would very likely
never have engaged for the exact incident it was built to fix. Corrected:
introduced a genuinely separate module constant, `_GROUP_COMMIT_INTERVAL`
(env: `MDM_GROUP_COMMIT_INTERVAL`, default 1000 -- the same numeric default
as `_PROGRESS_LOG_MIN_INTERVAL`, but NOT derived from or scaled by domain
size), threaded through as `_run_grouped_concurrent`'s new `commit_interval`
parameter (default `_GROUP_COMMIT_INTERVAL`, so existing callers need no
changes). `log_interval` now governs progress-log cadence only, exactly as
before this ticket.

Reviewed before writing any code (`/gof-refactor-reviewer`, CLAUDE.md hard rule):
- Confirmed periodic commit-within-the-same-sequential-loop is the right shape,
  not sub-chunking a group into separately-submitted concurrent pieces -- that
  would violate `_run_grouped_concurrent`'s own safety invariant (rows sharing a
  group key must stay strictly sequential on one worker to avoid racing on the
  same underlying entity).
- Confirmed no SQLAlchemy post-commit object-expiration risk: nothing in
  `resolve_one`/`run_survivorship_for_entity`/`_stage_attrs` holds an ORM object
  reference across row iterations in the loop being modified.
- Confirmed this is scoped to the actual problem (write-side durability/
  visibility), not the read-side memory problem `MANAGES_FUND`/
  `INSTITUTIONAL_HOLDS`'s fixes solved -- deliberately not reusing their
  batch-the-read pattern here, since memory was never the bottleneck for this
  gap (`group_rows` for even a 5,000-row group is trivially small in memory).

**Verification against real production data (in progress):** per explicit
instruction, this fix will be verified by re-running against the actual security
title/entity that was live-observed still running past the healthy burst window,
not just unit tests -- confirming periodic commits now make partial progress
durable and visible mid-group, and that the specific run this ticket was spawned
from can now complete (or at minimum show continuing external visibility) instead
of appearing stalled.

Tests: 6 in `tests/mdm/test_run_securities_persons_concurrency.py`'s
`TestGroupedConcurrentPeriodicCommit` -- periodic-commit-within-an-oversized-group
(3 commits for 25 rows at commit_interval=10), trailing-partial-batch-still-commits
(23 rows), small-group-unchanged-single-commit regression guard (5 rows),
per-group-counter-resets-independently across two groups (2 commits each, not a
shared running total), the second review's own regression guard
(commit_interval=10 still fires 3 commits for a 30-row group even when
log_interval=62500, proving the two are genuinely decoupled), and a sanity check
that `_GROUP_COMMIT_INTERVAL`'s default is small enough to ever fire for a
realistic group size. Full `tests/mdm/` suite (687 tests) and full repo suite
green.

**Not yet specified / open follow-up:** per-group progress logging (naming which
specific title/entity is large) would materially help future diagnosis of this
exact failure mode -- noted by `/gof-refactor-reviewer` as worth a future ticket,
not blocking this fix.
