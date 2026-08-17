# Decide Failure/Retry Semantics for the Two-Phase Backfill

Type: grilling
Status: resolved
Blocked by: 02

## Question

[Decide the Coupling Mechanism](02-decide-coupling-mechanism.md) settled
on two-phase/decoupled: parse writes a row with `mdm_entity_id = NULL`
immediately, then MDM resolves that window's batch shortly after and
backfills the real value (a second landing-zone `INSERT` for Snowflake,
an `UPDATE` for DuckDB). That decision deliberately avoided coupling
silver's write availability to MDM Postgres's uptime — but it didn't
specify what happens when the *backfill* itself fails, times out, or
never runs. This ticket decides that.

Concretely:

- Is the backfill attempted **synchronously within the same window's
  execution** (a second step in the same command invocation, just
  isolated so its failure doesn't block the first step's already-
  succeeded write), or a **fully separate, independently-scheduled sweep
  process** that finds and backfills `mdm_entity_id IS NULL` rows at its
  own cadence, decoupled in time from any specific window's run?
- If a backfill attempt fails, what retries it, and how often? Does the
  whole window's command need to fail/retry (re-touching bronze/parse
  work that already succeeded), or can just the backfill step retry in
  isolation?
- Should there be alerting/escalation for rows that stay `mdm_entity_id =
  NULL` past some threshold — mirroring this repo's existing alarm-
  coverage precedent (CLAUDE.md, ticket 81's daily_incremental alarm
  gap) — or is an indefinitely-NULL row an acceptable permanent state
  that downstream consumers (gold, dbt) must simply handle gracefully?

**Relevant precedent already in this exact codebase**, worth weighing
before inventing a new mechanism: `mdm_change_log.exported_at` (nullable,
with a partial index `idx_change_log_pending ON (exported_at) WHERE
exported_at IS NULL`) and `mdm_relationship_instance.graph_synced_at`
(same nullable-column-plus-partial-index shape, `idx_rel_instance_
pending_sync`) both already implement a "NULL = pending, an
independent sweep finds and processes NULLs, sets the timestamp when
done" pattern for exactly this class of problem (a value that's
computed asynchronously after the row's initial commit). A new
`mdm_entity_id IS NULL` backfill mechanism could plausibly reuse this
exact shape rather than designing something new.

## Deliverable

A decision: synchronous-same-window vs. independent-sweep backfill
attempt, the retry mechanism/cadence, and whether/how stuck-NULL rows
get alerted on.

## Answer

**Independent sweep, reusing this codebase's existing NULL-pending
pattern.** A window's command invocation only ever does the first phase
(parse → write rows with `mdm_entity_id = NULL` → exit); it never
attempts resolution itself and never blocks or retries on MDM's
availability. `mdm_entity_id IS NULL` becomes the same kind of
pending-work marker `mdm_change_log.exported_at IS NULL` (`idx_change_
log_pending`) and `mdm_relationship_instance.graph_synced_at IS NULL`
(`idx_rel_instance_pending_sync`) already are in this exact schema — a
partial index on the NULL condition, scanned by a separate,
independently-scheduled sweep that resolves and backfills on its own
cadence. Rejected the same-window/second-isolated-step shape: it would
leave failed backfill attempts with no built-in retry unless something
else re-triggers that specific window, whereas a sweep naturally retries
every unresolved row on every pass with no per-window bookkeeping needed.

**Retry mechanism**: the sweep itself *is* the retry — each pass re-scans
for `mdm_entity_id IS NULL` and attempts resolution again; a row that
fails to resolve on one pass is automatically retried on the next, with
no separate retry-counter/backoff mechanism needed beyond the sweep's own
schedule. The whole window's original command never re-runs for this
reason — bronze/parse work that already succeeded is never re-touched.

**Alerting**: yes, past a threshold (exact threshold, e.g. 24–48h, left
to implementation) — matching this repo's stated philosophy of not
letting failures go silently unnoticed (the daily_incremental
alarm-coverage-gap fix and the `ToleratedFailurePercentage` fix earlier
this session were both root-caused specifically because something failed
silently). A stuck NULL past the threshold signals something wrong with
either the sweep process itself or MDM's availability, and should page
the same way other pipeline gaps in this repo do.
