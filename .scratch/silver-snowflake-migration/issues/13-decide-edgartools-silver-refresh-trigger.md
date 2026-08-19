# Decide EDGARTOOLS_SILVER's Refresh Trigger

Type: grilling
Status: open
Blocked by: none

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
