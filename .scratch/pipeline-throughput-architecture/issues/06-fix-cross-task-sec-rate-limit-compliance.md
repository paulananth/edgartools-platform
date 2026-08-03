Type: task
Status: resolved

## Question

**Urgent, live in production, not hypothetical.** `bootstrap-batch`'s
existing cross-task fan-out (`load_history`'s Stage 1, driven by
`BOOTSTRAP_BATCH_CONCURRENCY`, default **3** per
`infra/scripts/deploy-aws-application.sh`) runs each concurrent ECS task
with its own independent, in-process `pyrate_limiter` at **9 req/sec**
(confirmed in [ticket 02](02-research-sec-rate-limit-headroom.md) --
hardcoded literal in `sec_client.py`, no cross-task coordination, no env
override). With 3 concurrent tasks that is up to **27 req/sec aggregate**
against SEC's own published ceiling of **10 req/sec per-operator,
"regardless of the number of machines used"** (also from ticket 02).

Nothing technically blocks this today -- ticket 02 also found prod has no
NAT gateway, so concurrent ECS tasks get distinct public IPs, and SEC's
per-IP enforcement wouldn't catch a multi-task overrun. But SEC's *stated*
policy is explicitly aggregate-per-operator, not per-IP, and separately
reserves the right to block "unclassified bots/automated tools regardless
of req/sec compliance." This is a real compliance gap against a
platform SEC's entire data pipeline depends on, not a technical
near-miss.

## Decision (made while grilling pipeline-throughput-architecture ticket
04, 2026-08-03)

**Fix via intra-task concurrency (the same pattern
[ticket 03](03-decide-intra-task-concurrency-model.md) already decided
for the artifact-fetch loop), not by tuning `BOOTSTRAP_BATCH_CONCURRENCY`.**

Why not `BOOTSTRAP_BATCH_CONCURRENCY`: the per-task limiter (9 req/sec) is
a hardcoded literal, not env-configurable -- so the only way to stay
compliant via task-count alone, without a code change, is
`BOOTSTRAP_BATCH_CONCURRENCY=1`. That does not tune anything; it
eliminates `load_history`'s entire cross-task fan-out advantage for the
SEC-fetch-bound phase of `bootstrap-batch`.

Why intra-task concurrency instead: a single task running a
`ThreadPoolExecutor` (bound 5, same as ticket 03) against the shared,
thread-safe `Limiter` can approach the same ~9-10 req/sec aggregate
ceiling that N "fair-share" tasks throttled to ~10/N req/sec each would
achieve -- SEC's limit is the real bottleneck regardless of how work is
organized across tasks, so this loses no throughput ceiling compared to a
compliant multi-task alternative, while adding zero new distributed
rate-limiting infrastructure (no DynamoDB token bucket, no cross-task
coordination to build and maintain).

## Scope (revised 2026-08-03 -- shared-function finding)

Confirmed via code reading: `bootstrap-batch`'s submissions-fetch call
routes through the **same shared function**,
`_capture_submission_bronze_snapshot` /
`_run_submissions_bronze_then_silver`
(`edgar_warehouse/application/warehouse_orchestrator.py`), as **four other
commands' own submissions-capture loops** -- `daily_incremental` (line
~1197, `load_mode="daily_incremental"`), `bootstrap` (~1260,
`load_mode="bootstrap"`), `bootstrap_full` (~1295/1335), and
`targeted_resync` (~1385/1500), in addition to `bootstrap_batch` itself
(~1793). This is also exactly the loop [ticket 04](04-decide-cross-task-fanout-model.md)
identified as `daily-incremental`'s own submissions-bronze-capture phase
(23.3%/48.3 min per [ticket 01](01-profile-pipeline-stage-bottleneck-breakdown.md)).

**One fix, five callers**: applying the ticket-03-style `ThreadPoolExecutor`
treatment to `_capture_submission_bronze_snapshot`'s SEC-fetch call resolves
both this ticket's original scope (bootstrap-batch's cross-task compliance
gap, by making single-task throughput good enough that
`BOOTSTRAP_BATCH_CONCURRENCY` > 1 stops being needed for the SEC-bound
phase) **and** ticket 04's deferred submissions-bronze-capture question for
`daily-incremental` (no separate fan-out needed there either), plus the same
benefit for free on `bootstrap`/`bootstrap_full`/`targeted_resync`.

1. **Immediate**: apply `ThreadPoolExecutor` (bound 5, same as ticket 03) to
   `_capture_submission_bronze_snapshot`'s SEC-fetch call -- one change,
   five callers benefit.
2. Once that lands, re-evaluate whether `BOOTSTRAP_BATCH_CONCURRENCY` > 1
   still buys anything for `bootstrap-batch` specifically (its SEC-bound
   phase would no longer need cross-task fan-out for throughput; any
   remaining benefit would have to come from non-network work -- DB
   writes, hashing, orchestration -- overlapping across tasks, which is a
   separate, smaller claim to verify, not assume).
3. Does **not** change `load_history`'s use of `bootstrap-batch` xN for
   reasons other than SEC throughput (if any exist) -- scope this
   narrowly to the rate-limit compliance question, not a full redesign of
   `load_history`'s Stage 1.

## Not yet specified / split off

Whether concurrently-running **different commands** (not just
`bootstrap-batch`'s own internal fan-out) can jointly exceed SEC's
aggregate ceiling -- e.g. an operator manually running `bootstrap-batch`
while a scheduled `daily-incremental` is also active, each internally
compliant on its own after this fix, but jointly not. Confirmed via code
reading: `pipeline_run_lease` (`silver_store.py`) is a generic
mutual-exclusion primitive, but only one lease name
(`daily_identity_refresh`) is registered anywhere in the codebase -- there
is **no** existing lock preventing two different SEC-fetching commands
from running at the same time. This is a genuine, separate architecture
decision (real throughput-vs-safety tradeoffs, not a mechanical fix like
this ticket) -- split off as
[ticket 09](09-decide-cross-command-sec-fetch-mutual-exclusion.md).

## Done when

`_capture_submission_bronze_snapshot`'s SEC-fetch call has the
ticket-03-style `ThreadPoolExecutor` treatment, `BOOTSTRAP_BATCH_CONCURRENCY`'s
role is re-evaluated per point 2 above, and a live measurement confirms
aggregate SEC request rate across all concurrently running tasks *of the
same command* stays at or under 10 req/sec. Cross-*command* concurrency is
explicitly out of this ticket's scope -- see ticket 09.

## Resolved as a decision (2026-08-03)

The direction above is the decision, and it's settled -- but this map is
decision-spec only (see map Notes: "resolving a ticket here means writing
down the decision, not shipping code"). This ticket's "Done when" as
originally written called for the actual code change and a live
measurement, which oversteps that mode -- the same mistake avoided for
`gold-refresh` by splitting profile (07) from decide (08). Correcting it
here: implementation (the `ThreadPoolExecutor` change itself, the
`BOOTSTRAP_BATCH_CONCURRENCY` re-evaluation, and the live compliance
measurement) moves to
[release-readiness ticket 78](../../release-readiness/issues/78-implement-shared-submissions-fetch-concurrency.md),
matching where every other implementation-shaped finding from this
workstream lives (tickets 65, 67-76). Ticket 03's own artifact-fetch-loop
implementation had the same gap (decided, never split into an
implementation ticket) -- filed alongside as
[release-readiness ticket 77](../../release-readiness/issues/77-implement-artifact-fetch-concurrency.md).
