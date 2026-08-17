# Design the Dead-Man's-Switch Alarm

Type: grilling
Status: resolved

## Question

Round 2 of this map's grilling decided this map should cover an
alert-only CloudWatch alarm as the replacement safety net for the removed
6-hour poll — no fallback execution, purely observability so a broken
trigger surfaces to an operator instead of gold silently going stale.
Mirror the pattern already established for `daily_incremental`'s own
alarm-coverage fix (CLAUDE.md's ticket 81 reference / release-readiness
workstream) rather than inventing a new alerting shape for this repo.

Open questions this ticket needs to settle:

1. **What signal does the alarm watch?** [Ticket 03](03-decide-invocation-plumbing-and-task-object-fate.md)
   resolved: `snowflake_task.manifest_processor` is removed entirely, and
   the trigger is a new single-purpose ECS command on the warehouse image
   (same shape as `release-sec-fetch-lease`) — so there's no task-scheduler
   log path to depend on at all; the new command logs via this repo's
   standard CloudWatch conventions like every other warehouse command.
   Candidates: a CloudWatch metric filter on that command's own
   success/no-op log lines, vs. a scheduled Snowflake-side check (e.g. a
   lightweight query comparing the manifest stream's pending-row age
   against a threshold) exported to CloudWatch, vs. an AWS-side check on
   "has any of the 7 watched state machines succeeded in the last 24-36h
   without a corresponding downstream Snowflake call."
2. **Threshold**: what age counts as "stuck" — 24h given the daily cron
   cadence, or wider to tolerate a legitimately quiet day (no watched
   pipeline ran at all, so no manifest rows and no alarm should fire)?
   Confirm the alarm can distinguish "nothing to load today" (fine, no
   alert) from "something was ready to load and the trigger never fired"
   (the actual failure mode). **Narrowed by [ticket 07](07-decide-lost-fire-retry-and-snowpipe-timing.md):**
   the command now excludes its own triggering ARN from the RUNNING check
   (closes the stale-view false-busy case) and bounded-polls
   `SYSTEM$STREAM_HAS_DATA` for ~2 minutes before giving up (closes the
   common Snowpipe-lag case), and genuine task/connector failures already
   get 2 SFN-level retries. This alarm's threshold no longer has to
   compensate for those routine cases — it's answering "how long is too
   long once the cheap mitigations have already had their shot" (a
   Snowpipe delay outlasting the 2-minute bound *and* no other watched
   pipeline completing for a while, a persistent failure surviving 2
   retries, or a misconfigured EventBridge rule), not "how long is too
   long given zero mitigation." Should tighten the threshold this ticket
   picks, not widen it.
3. **Where does the alert land?** Reuse the existing operator alert SNS
   topic (`require_confirmed_operator_alert_topic` /
   `--operator-alert-topic-arn`, already used elsewhere in
   `infra/scripts/deploy-aws-application.sh`) rather than a new channel.

## Answer

Grounded the threshold decision in live data pulled from
`EDGARTOOLS_PROD_REFRESH_WH`'s real `TASK_HISTORY`/`WAREHOUSE_METERING_HISTORY`
rather than assumption — see the parent conversation for the full pull;
summary below.

**Signal: a scheduled Snowflake-side check on the manifest stream's
oldest-pending-row age**, not a CloudWatch metric filter on the new
command's logs and not an AWS-side "has any watched machine succeeded
without a downstream call" check. Reasoning:
- A `SELECT MIN(RECEIVED_AT) FROM EDGARTOOLS_SOURCE.SNOWFLAKE_RUN_MANIFEST_STREAM
  WHERE METADATA$ACTION = 'INSERT'` reads the stream without consuming it
  (only `INSERT ... SELECT` advances the offset, confirmed in
  [ticket 03](03-decide-invocation-plumbing-and-task-object-fate.md)'s
  research) — so this check is safe to run independently of the trigger
  path, and directly measures the thing that actually matters (how long
  has real pending data been waiting), not a proxy for it.
- A CloudWatch log-based signal only tells you the command *ran*, not
  whether it's been long enough since real data arrived — it can't
  distinguish "nothing pending, correctly quiet" from "something's been
  pending for hours" without re-deriving this same stream-age check
  anyway, so build it once, in Snowflake, where the state actually lives.
- The AWS-side "watched machine succeeded without a downstream call"
  check would need its own definition of the 11-machine watched set —
  exactly the kind of second hand-maintained collection
  [ticket 05](05-derive-correct-watched-state-machine-set.md) already
  ruled out.

**Threshold: 4 hours**, tighter than the originally-floated 24h. Live
verification of the actual post-fix task cadence
(`TASK_HISTORY(TASK_NAME => 'SNOWFLAKE_RUN_MANIFEST_TASK', ...)`) shows
the old poll settled into a clean exact 6-hour cadence from 2026-08-14
12:53 onward (12:53 → 18:53 → 00:53 → 06:53 ...) — meaning the *old*
design's own worst-case freshness lag was 6 hours by construction. The
new event-driven design should **always** beat that in normal operation
(it fires on real completions, not a timer), so if the oldest pending row
is older than 6 hours despite [ticket 07](07-decide-lost-fire-retry-and-snowpipe-timing.md)'s
inline mitigations (exclude-self-ARN, bounded Snowpipe poll, 2 SFN
retries) already having had their shot, something is genuinely broken —
not just "slower than usual." 4 hours leaves margin below that 6-hour
worst-case-of-the-system-being-replaced, so the alarm fires *before* the
new design would even match the old one's worst case, rather than only
after matching it.

**Distinguishing "nothing to load" from "stuck":** the query only
evaluates when the stream is non-empty (`WHERE METADATA$ACTION = 'INSERT'`
naturally returns zero rows on a quiet day) — `MIN(RECEIVED_AT)` over zero
rows is `NULL`, and the alarm condition is `age > 4h AND MIN(RECEIVED_AT)
IS NOT NULL` (or equivalently, skip evaluation entirely when the row count
is zero). A day with no watched-pipeline activity produces no pending rows
at all, so it never enters the threshold check — no special-casing needed
beyond the natural shape of the query.

**Alert destination: the existing operator alert SNS topic**
(`require_confirmed_operator_alert_topic`/`--operator-alert-topic-arn`),
per the ticket's own default — no new channel. Mechanically, the
Snowflake-side check runs on its own lightweight schedule (independent of
the trigger path, so it can't be silenced by the same failure it's meant
to catch), exports its result to CloudWatch (matching the pattern
CLAUDE.md's ticket 81 alarm-coverage fix already established for
`daily_incremental`), and a CloudWatch alarm on that metric publishes to
the SNS topic.

**Note for the implementer, not part of this decision:** while pulling
this data, found that `REFRESH_AFTER_LOAD` unconditionally refreshes all
~24 gold tables on *every* manifest row it processes (confirmed live: 30
days of `QUERY_HISTORY` show 6,435 `REFRESH_AFTER_LOAD` calls against
1,009 `PROCESS_RUN_MANIFEST_STREAM` calls — averaging ~6.4 full-table-refresh
passes per invocation), rather than scoping the refresh to whatever the
triggering workflow actually touched. This is a real, likely significant
inefficiency, but it's orthogonal to this map — it costs the same under
the old poll and the new trigger alike, since both call
`REFRESH_AFTER_LOAD` once per pending manifest row regardless of what
wakes them up. Worth its own investigation separately; not something this
map's tickets should absorb.
