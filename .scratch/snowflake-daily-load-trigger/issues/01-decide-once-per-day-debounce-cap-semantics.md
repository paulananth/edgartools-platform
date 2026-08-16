# Decide Once-Per-Day Debounce/Cap Semantics

Type: grilling
Status: resolved

## Question

The user's original ask was "run Snowflake load once a day after all
loads complete." The watched set (see map.md's Notes) is 7 independently
schedulable state machines: `daily_incremental` runs on a fixed cron
(Mon-Sat 12:00 UTC + Sunday backstop, `infra/scripts/
deploy-aws-application.sh:509`), but `load_history`, `bootstrap`,
`bootstrap_full`, `targeted_resync`, `full_reconcile`, and `silver_mdm_gold`
are all triggered ad hoc/manually and can run at any time, independently
of each other and of the daily cron.

Given that, "once a day" is ambiguous once more than one watched machine
can finish at different times on the same day:

1. **Exactly-once-per-UTC-day, at the point the watched set is idle**:
   if `daily_incremental` finishes at 12:30 UTC and nothing else is
   running, fire immediately and do not fire again that day even if
   someone kicks off `load_history` at 15:00 UTC and it finishes at
   18:00 UTC (that day's data would wait until the next fire).
2. **Fire on every busy→idle transition** (no daily cap at all): if
   `daily_incremental` finishes at 12:30 and `load_history` finishes at
   18:00 with a gap of true idle in between, fire twice that day. This is
   closer to "run after loads complete" read literally per-load rather
   than per-day, but contradicts the user's literal "once a day" framing.
3. **Debounce with a settle window**: wait N minutes of continuous idle
   after a busy→idle transition before firing, to absorb near-simultaneous
   finishes without needing a hard daily cap — but still allows multiple
   fires per day if gaps are long enough.

Decide which semantics this map builds, and if (1) or (3), how "already
fired today" is tracked (DynamoDB item, SSM parameter, or a Snowflake-side
check such as "was `PROCESS_RUN_MANIFEST_STREAM` already called after the
last pending manifest row appeared") — needed before
[Design the Idle-Detection Re-Check and Race Safety](02-design-idle-detection-recheck-and-race-safety.md)
can be finished, since the re-check step is where this cap would be
enforced.

## Answer

**Option 2 — fire on every genuine busy→idle transition, no daily cap.**

Read the actual procedure the trigger will call
(`infra/terraform/snowflake/modules/native_pull/sql/
stream_processor_procedure.sql`) before deciding, since it changes the
cost calculus the three options were weighed against:

- `PROCESS_RUN_MANIFEST_STREAM` reads the manifest **stream** via
  `INSERT ... SELECT` (the only way to advance a Snowflake stream's
  offset) into a session-temp table, then loops over whatever distinct
  `(workflow_name, run_id)` rows it found, calling the per-workflow load +
  refresh procedures for each. If the stream is empty, this is a cheap
  no-op: one temp-table create, one empty `INSERT...SELECT`, zero loop
  iterations, `processed_count: 0`.
- The original 6h-poll credit-burn incident (CLAUDE.md's "Gold-build
  memory" 5-whys, `.scratch/ecs-cost-sizing/issues/22-...md`) was caused
  by a **fixed timer** repeatedly waking `EDGARTOOLS_PROD_REFRESH_WH`
  during heavy `load_history` activity, not by the procedure's own
  execution cost. An event-driven trigger has no equivalent failure mode:
  it only wakes the warehouse on a genuine top-level pipeline completion,
  which is inherently rate-limited by how often pipelines actually run —
  there is no timer forcing extra wake-ups regardless of state.

Given that, a hard once-per-day cap buys nothing on the cost side and
costs real freshness: under option 1, an ad hoc `load_history` backfill
finishing at 6pm would sit unsynced until the next day's fire, for no
benefit. Option 2 fires exactly once a day in the steady-state case
(only `daily_incremental` runs) — "once a day" holds as an emergent
property of the pipeline schedule, not an enforced cap — and fires again
only when there's a second genuinely separate batch of completed work,
which is exactly when a sync is wanted sooner rather than later.

**Consequence for [ticket 02](02-design-idle-detection-recheck-and-race-safety.md):**
no "already fired today" state needs to be persisted or race-guarded at
all — removed that sub-question from its scope (updated there). Its
race-safety concern (two near-simultaneous terminal events both passing
the idle re-check) still stands and is unaffected by this answer.

Option 3 (settle-window debounce) was also rejected as redundant: the
near-simultaneous-finish case it was meant to absorb is already handled
by ticket 02's own re-check-who's-still-RUNNING design, so it would have
been a second mechanism solving an already-solved problem.
