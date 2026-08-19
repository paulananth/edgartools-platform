# Decide EDGARTOOLS_SILVER's Refresh Trigger

Type: grilling
Status: resolved
Blocked by: none

Claimed by Claude on 2026-08-18.

## Question

Surfaced while implementing [Ticket 12](12-cutover-mdm-sharded-silver-reader-to-snowflake.md)
(Cut Over MDM's ShardedSilverReader to Snowflake): `EDGARTOOLS_SILVER`'s
dynamic tables were built with `target_lag = 'DOWNSTREAM'` (per Ticket 01's
model-structure design). Snowflake's `DOWNSTREAM` lag mode means a dynamic
table only refreshes when a *downstream consumer* (another dynamic table
that reads it) demands fresh data — with no such consumer, the table never
auto-refreshes on any schedule at all.

[Ticket 11](11-reprovision-missing-bootstrap-sql-on-rebuilt-account.md)'s
own verification already hit this directly: the only reason its 1,506 rows
in `SEC_EMPLOYMENT_EVENT` were visible was a **manual**
`ALTER DYNAMIC TABLE ... REFRESH`, and that ticket explicitly punted the
real fix to "Ticket 09/10's cutover." Checking those two tickets' actual
answers: neither set a `target_lag` or a refresh mechanism — Ticket 09
decided *order* (MDM first), Ticket 10 decided *flip/gate/rollback
mechanics* for that consumer. This specific question fell through the gap
between all three tickets.

**Concretely, this blocks Ticket 12's actual prod flip**: `MDM_SILVER_READ_TARGET=snowflake`
only reads correct data if `EDGARTOOLS_SILVER`'s tables are actually
current. Today, with no downstream consumer and no schedule, they are not
— they reflect whatever they were at the last manual `REFRESH`, indefinitely
stale otherwise.

Two real options, genuinely different operational shapes:

1. **MDM itself becomes the thing that justifies a real consumer /
   schedule.** Either change `target_lag` from `DOWNSTREAM` to a fixed
   interval (mirroring `LOAD_SILVER_LANDING_TASK`'s existing 5-minute
   `COPY INTO` schedule, or Ticket 11's `SNOWFLAKE_RUN_MANIFEST_TASK`
   6-hour pattern), or add a genuine downstream dynamic table that reads
   `EDGARTOOLS_SILVER` (which would exist anyway once `gold_models.py`'s
   own cutover lands — but that's weeks away per Ticket 09's 2-week
   dual-write bound, not available now).
2. **A dedicated scheduled task**, mirroring `LOAD_SILVER_LANDING_TASK`'s
   shape exactly: a new Snowflake `TASK` that runs
   `ALTER DYNAMIC TABLE ... REFRESH` (or a wrapper procedure looping over
   all 31 tables, matching `04_refresh_wrapper.sql`'s existing precedent
   for `EDGARTOOLS_GOLD`) on its own schedule, independent of any consumer
   ever existing.

Resolve: which mechanism, what schedule/lag, and where it gets committed
(new bootstrap SQL file, following this map's own "every provisioning step
is committed and re-runnable" standing requirement). Consider Ticket 08's
cost-estimate range ($4/month at 6hr lag to $96/month at 15min lag,
excluding the unmeasured FULL-mode-table marginal cost it flagged) when
picking a schedule.

## Answer

**Mechanism: option 1's fixed-`target_lag` variant** (not option 2, a
dedicated `TASK`). Grounded in the actual code before asking: all 30
`EDGARTOOLS_SILVER` dynamic tables (31 model files, 1 — `sec_guidance_fact_reject`
— is a deliberate plain `VIEW` per Ticket 01's "quarantine log" exception, so
`target_lag` doesn't apply to it) already source their `target_lag` from a
single shared dbt macro, `silver_model_config` in
`infra/snowflake/dbt/edgartools_gold/macros/silver_model_config.sql`, called
once per generated model. Changing `target_lag='DOWNSTREAM'` to a fixed
interval there is a one-line, one-file change that reaches every table via
the next `dbt run` (a config-only diff — CLAUDE.md's own documented
dbt-snowflake behavior means this doesn't even need `--full-refresh`). A
dedicated `TASK` (option 2) would mean a new bootstrap SQL file, a wrapper
procedure looping 30 tables (`04_refresh_wrapper.sql`'s shape), and a second
scheduling surface to monitor — strictly more moving parts to solve a
problem Snowflake's native `target_lag` already solves directly. The
"MDM becomes a genuine downstream consumer" half of option 1 (a real
downstream dynamic table) isn't available yet either way — that only exists
once `gold_models.py`'s own cutover lands, weeks away per
[Ticket 09](09-decide-consumer-cutover-order.md)'s dual-write bound — so a
fixed interval is what's actually achievable today, with `DOWNSTREAM` worth
revisiting once that cutover exists.

**Schedule: 6 hours.** Per Ticket 08's cost estimate (`$4/month` at this
cadence for the 30 tables, vs. `$96/month` at 15 minutes, floor estimates).
This is the identical tradeoff CLAUDE.md already documents this repo making
once before, at the immediately adjacent layer of the same pipeline:
`SNOWFLAKE_RUN_MANIFEST_TASK` (refreshes `EDGARTOOLS_GOLD` from silver) was
deliberately widened `1min → 15min → 6hr` on 2026-08-14 after a 1-minute poll
never let its warehouse fully suspend, "per explicit operator decision
prioritizing credit economy over near-real-time freshness." Nothing
downstream of MDM's silver reads (entity resolution, relationship
derivation — both themselves batch jobs, not real-time) needs fresher than
6 hours.

**Committed where:** `infra/snowflake/dbt/edgartools_gold/macros/silver_model_config.sql`
(the single source of truth every silver model's config already flows
through) — not a new bootstrap SQL file. Live state was brought in sync
immediately, ahead of the next `dbt run`, via 30
`ALTER DYNAMIC TABLE ... SET TARGET_LAG = '6 hours'` statements run as
`EDGARTOOLS_PROD_DEPLOYER` (the tables' live owner role, confirmed via
`SHOW DYNAMIC TABLES` before touching anything — not `EDGARTOOLS_PROD_LOADER`,
which is what CLAUDE.md's "one runtime role" language might suggest; silver
was never migrated onto the loader role the way `EDGARTOOLS_GOLD` was).
Live-verified after: all 30 tables report `target_lag = '6 hours'`, zero
still on `DOWNSTREAM`.

This resolves Ticket 12's refresh-trigger blocker. Ticket 12's remaining
preconditions on the actual `MDM_SILVER_READ_TARGET=snowflake` flip are
unchanged by this ticket: `EDGARTOOLS_SILVER` holding real data at scale
(Stage 14), a clean `mdm verify-silver-parity` run against that volume, and
the CloudWatch alarm on post-flip divergence (still not built).
