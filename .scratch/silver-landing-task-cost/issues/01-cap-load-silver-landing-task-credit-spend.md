# 01 — Cap LOAD_SILVER_LANDING_TASK's Snowflake credit spend at ≤1 credit/day

**What to build:** `EDGARTOOLS_PROD_REFRESH_WH` was burning ~9 credits/day, every day since
2026-08-18, entirely driven by `LOAD_SILVER_LANDING_TASK`'s 5-minute polling cadence. Bring it
under an explicit ≤1 credit/day ceiling and document the pattern so it doesn't silently recur on
the next scheduled task.

**Blocked by:** None — root cause was fully diagnosed live against
`SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`/`TASK_HISTORY`/`QUERY_HISTORY` before this
ticket was opened; no further investigation needed to act.

**Type:** `wayfinder:task` (AFK) — root cause and fix were already known going in; this is
execution, not a decision, so it's resolved in the same session it was opened rather than being
worked as a wayfinder map with a frontier.

**Status:** resolved

## Answer

**Diagnosis (5-whys, also recorded in `CLAUDE.md` under "LOAD_SILVER_LANDING_TASK credit-burn
5-whys"):** `LOAD_SILVER_LANDING_TASK` (`infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql`,
silver-snowflake-migration map's Ticket 07) was shipped with an explicitly-labeled "5-minute
cadence: a starting default... tune once real volume exists" comment and never actually tuned.
At 288 resumes/day against `EDGARTOOLS_PROD_REFRESH_WH` (X-Small, `auto_suspend=60`), the
warehouse almost never stayed suspended long enough between 5-minute ticks to avoid a per-resume
minimum charge — the identical shape this repo's own "ecs-cost-sizing" finding had already fixed
for the sibling `SNOWFLAKE_RUN_MANIFEST_TASK` (1 MIN → 15 MIN → 6 HOUR) three weeks earlier. That
fix was never ported to this task, which was created after it.

**Live measurements before the fix** (`WAREHOUSE_METERING_HISTORY`, `TASK_HISTORY`,
`QUERY_HISTORY` against `EDGARTOOLS_PROD_REFRESH_WH`):
- Warehouse created 2026-08-18 03:42; `LOAD_SILVER_LANDING_TASK` created 2026-08-18 14:17,
  `SCHEDULE = '5 MINUTE'`.
- Daily credits on this warehouse: 08-19: 9.22, 08-20: 9.13, 08-21: 9.09, 08-22: 9.24 (+5.84 on
  `COMPUTE_WH` that day from an unrelated manual backfill), 08-23: 9.02, 08-24: 9.11 — vs. $0 on
  every day before 08-18.
- 58,971 `COPY INTO` queries + 1,908 `CALL LOAD_SILVER_LANDING()` calls over 7 days, all
  `SYSTEM`/`EDGARTOOLS_PROD_LOADER`, i.e. all task-driven, not manual/interactive.
- 288 task firings/day × ~9 credits/day observed ⇒ ~0.03 credits/firing average, dominated by
  fixed per-resume overhead rather than data volume (COPY has essentially nothing to do on most
  ticks — the pipeline is not that high-frequency yet).

**Fix:** widened `LOAD_SILVER_LANDING_TASK`'s `SCHEDULE` from `5 MINUTE` to `60 MINUTE` in
`infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql` — 24 resumes/day instead of 288, a
12x reduction. Extrapolating linearly from the observed 5-minute-cadence cost (~9 credits/day ÷
288 firings × 24 firings ≈ 0.75 credits/day) lands comfortably under the ≤1 credit/day target,
though this is an extrapolation, not an independent measurement at the new cadence — flagged
explicitly below as needing a real check.

Applied live to prod:
```
ALTER TASK EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.LOAD_SILVER_LANDING_TASK SUSPEND;
ALTER TASK EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.LOAD_SILVER_LANDING_TASK SET SCHEDULE = '60 MINUTE';
ALTER TASK EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.LOAD_SILVER_LANDING_TASK RESUME;
```
`SHOW TASKS` confirms `schedule: 60 MINUTE`, `state: started`. `13_silver_landing_ingest.sql`
updated to match (so a future fresh-environment bootstrap gets the tuned cadence directly,
`CREATE TASK IF NOT EXISTS` doesn't touch an existing task's schedule, so the script also now
carries the same `SUSPEND` → `SET SCHEDULE` → (existing) `RESUME` sequence for idempotent re-runs
against an already-provisioned prod).

Live finding along the way: `ALTER TASK ... SET SCHEDULE` against a `STARTED` root task fails
closed — `"Unable to update graph with root task ... since that root task is not suspended"` — it
does not silently no-op or auto-suspend for you. The script's `SUSPEND`/`RESUME` bracketing is
required, not decorative, and both are idempotent no-ops if the task is already in that state
going in.

**Acceptance:**
- [x] Root cause identified via live Snowflake account-usage data (`WAREHOUSE_METERING_HISTORY`,
      `TASK_HISTORY`, `QUERY_HISTORY`), not assumed.
- [x] Fix applied live to prod; `SHOW TASKS` confirms the new schedule and `started` state.
- [x] Bootstrap SQL (`13_silver_landing_ingest.sql`) updated so a fresh environment gets the
      tuned cadence, and a re-run against an already-provisioned prod safely re-applies it.
- [x] Documented in `CLAUDE.md` as a 5-whys entry, including the general lesson for any future
      scheduled `TASK` (size the interval against a credit budget up front, or gate on data
      presence, rather than shipping a tight fixed poll as a placeholder).
- [x] Re-verified against a full day of `WAREHOUSE_METERING_HISTORY` at the 60-minute cadence,
      2026-08-26 — see [02 — Widen `LOAD_SILVER_LANDING_TASK` further, to a 0.3-0.5 credit/day
      target](02-widen-load-silver-landing-task-to-0.3-0.5-credit-day.md), which also supersedes
      the 60-minute schedule itself with a wider one per an explicit operator target.

## Not done here (deliberately out of scope for this ticket)

- A stream-gated conditional task (`WHEN SYSTEM$STREAM_HAS_DATA(...)`) that would skip the
  warehouse resume entirely on ticks with genuinely no new files, rather than paying a smaller
  but still-nonzero cost every hour. Noted in `CLAUDE.md` as the mechanism to reach for if
  freshness needs to go back down below 60 minutes without re-inflating cost — not built now
  since 60 MINUTE alone already meets the stated ≤1 credit/day target and building the
  stream-gate mechanism now would be solving a freshness problem nobody has asked for yet.
