# 02 — Widen `LOAD_SILVER_LANDING_TASK` further, to a 0.3-0.5 credit/day target

**What to build:** Ticket 01's 60 MINUTE fix left one item open — re-verify the real post-fix
cost against `WAREHOUSE_METERING_HISTORY`, since the 60-minute number was extrapolated, not
independently measured. Separately, the operator asked to bring the cost down further, into an
explicit 0.3-0.5 credit/day band.

**Blocked by:** None — [01](01-cap-load-silver-landing-task-credit-spend.md)'s fix was already
live; this ticket verifies it, then widens further.

**Type:** `wayfinder:task` (AFK) — measurement plus a schedule change, not a decision requiring
grilling; options were presented to the operator once (see Answer) and the choice was made
directly, not worked as a wayfinder map with a frontier.

**Status:** resolved

## Answer

**Re-verification of the 60-minute cadence (closes Ticket 01's open item):** live against
`SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY` on `EDGARTOOLS_PROD_REFRESH_WH`:

- Raw daily totals looked inconsistent at first glance — 2026-08-25 showed 2.78 credits, well
  above the ≤1/day target. Root cause: the 60-minute fix only actually went live at 05:29 that
  morning (`last_committed_on` on the task), so 08-25's calendar-day total still included ~5.5
  hours of leftover 5-minute-cadence resumes from before the fix landed. Not a regression.
- Isolating a genuinely clean post-fix window (05:30 on 08-25 through 07:14 on 08-26, 25
  consecutive hourly buckets): a steady **0.031-0.042 credits/hour**, no outliers. Extrapolated to
  a full day: **~0.80 credits/day** — comfortably under Ticket 01's ≤1 credit/day ceiling.
  Independently corroborated by 08-26's own partial-day total (0.23 credits over ~7.2 hours ⇒
  ~0.76/day annualized) landing within the same range. Ticket 01's extrapolation (~0.75/day) is
  confirmed accurate to within measurement noise.
- Confirmed via `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` that the 84 `CALL` statements seen on
  08-25's raw daily figure exactly matches the transition-day math (≈66 five-minute-cadence calls
  before 05:29 + ≈18 hourly calls after) — not a sign of the task firing more often than
  scheduled.
- Also confirmed the warehouse's only other tenant, `SNOWFLAKE_RUN_MANIFEST_TASK` (360 MINUTE,
  gated behind `WHEN SYSTEM$STREAM_HAS_DATA(...)`), contributes negligibly to this total — it
  already uses the stream-gate mechanism Ticket 01 noted as "not built now" for this sibling task.

**Further widening to hit the 0.3-0.5 credit/day target:** presented the operator four concrete
options (120 MINUTE ≈0.40/day; 180 MINUTE ≈0.27/day; a stream-gated conditional task mirroring
`SNOWFLAKE_RUN_MANIFEST_TASK`'s own pattern, keeping 60 MINUTE freshness but skipping resumes on
genuinely idle ticks; or a custom interval). Operator chose **180 MINUTE** — undershoots the
target band deliberately, trading the extra freshness margin (max staleness ~1hr → ~3hr) for
simplicity and headroom over the stream-gate alternative, which would need new Snowflake
infrastructure (a real `STREAM` object over the landing source; no such object exists for this
task today, unlike its sibling) to build and verify.

**Fix applied:**
```sql
ALTER TASK EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.LOAD_SILVER_LANDING_TASK SUSPEND;
ALTER TASK EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.LOAD_SILVER_LANDING_TASK
    SET SCHEDULE = '180 MINUTE', COMMENT = '...';
ALTER TASK EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.LOAD_SILVER_LANDING_TASK RESUME;
```
`SHOW TASKS` confirms `schedule: 180 MINUTE`, `state: started`, committed 2026-08-26 08:29 PDT.
`infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql` updated to match (`CREATE TASK` +
schedule comment + the existing idempotent `SUSPEND`/`SET SCHEDULE`/`RESUME` re-run sequence),
so a fresh-environment bootstrap and a re-run against an already-provisioned prod both land on
180 MINUTE directly.

Extrapolating from the same ~0.033 credits/resume measured at 60 MINUTE (8 resumes/day instead of
24) gives an expected **~0.27 credits/day** — this is an extrapolation, not yet an independent
measurement at 180 MINUTE, flagged the same way Ticket 01 flagged its own 60-minute extrapolation.
The assumption that per-resume cost stays flat as batches get less frequent (and each batch has
marginally more accumulated data to scan/copy) was not independently verified before this rollout.

**Acceptance:**
- [x] 60-minute cadence's real cost independently verified against a full clean day of
      `WAREHOUSE_METERING_HISTORY` (~0.80 credits/day) — closes Ticket 01's open item.
- [x] Options for reaching a 0.3-0.5 credit/day target presented to the operator with concrete
      numbers; operator's choice (180 MINUTE) applied.
- [x] Fix applied live to prod; `SHOW TASKS` confirms the new schedule and `started` state.
- [x] Bootstrap SQL updated so a fresh environment gets the new cadence and a re-run against an
      already-provisioned prod safely re-applies it.
- [ ] **Not yet done — re-verify against a full day of `WAREHOUSE_METERING_HISTORY` at the new
      180-minute cadence** to confirm the ~0.27 credit/day extrapolation actually holds. Check on
      2026-08-27 or later once a full clean day (post 08-26 08:29 PDT) has metered.

## Not done here (deliberately out of scope for this ticket)

- The stream-gated conditional task (`WHEN SYSTEM$STREAM_HAS_DATA(...)`) — offered as an option,
  not chosen. Still the mechanism to reach for if freshness needs to come back down toward
  hourly without re-inflating cost; would need a new Snowflake `STREAM` object over the landing
  source built and verified first.
