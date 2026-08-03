Type: task
Status: open

## Question

Implement [pipeline-throughput-architecture ticket 06](../../pipeline-throughput-architecture/issues/06-fix-cross-task-sec-rate-limit-compliance.md)'s
decision: add the same `ThreadPoolExecutor` treatment as
[ticket 77](77-implement-artifact-fetch-concurrency.md) to
`_capture_submission_bronze_snapshot`'s SEC-fetch call
(`edgar_warehouse/application/warehouse_orchestrator.py`), then re-evaluate
`BOOTSTRAP_BATCH_CONCURRENCY`.

## Why this is urgent, not just a speed win

`bootstrap-batch`'s existing cross-task fan-out
(`BOOTSTRAP_BATCH_CONCURRENCY=3` in prod, `infra/scripts/deploy-aws-application.sh`)
runs each concurrent ECS task with its own independent, in-process
`pyrate_limiter` at 9 req/sec -- up to **27 req/sec aggregate** against
SEC's published **10 req/sec per-operator** ceiling ("regardless of the
number of machines used"). Live in production today. See ticket 06 for
the full compliance writeup.

## Decision already made (ticket 06)

- `_capture_submission_bronze_snapshot` is a **shared function** --
  confirmed via code reading to be called by `daily_incremental`,
  `bootstrap`, `bootstrap_full`, `targeted_resync`, **and**
  `bootstrap_batch` (5 call sites in `warehouse_orchestrator.py`). One fix
  here benefits all five commands, including
  [pipeline-throughput-architecture ticket 04](../../pipeline-throughput-architecture/issues/04-decide-cross-task-fanout-model.md)'s
  `daily-incremental` submissions-bronze-capture question (resolved as "no
  separate fan-out needed" specifically because this fix covers it).
- **Not fixed via `BOOTSTRAP_BATCH_CONCURRENCY`**: the per-task limiter (9
  req/sec) is a hardcoded literal in `sec_client.py`, not env-configurable
  -- so the only compliant task-count-only fix would be
  `BOOTSTRAP_BATCH_CONCURRENCY=1`, eliminating `load_history`'s entire
  cross-task fan-out advantage for the SEC-bound phase. Same
  `ThreadPoolExecutor`/bound-5/serialized-DB-writes shape as ticket 77
  instead -- see that ticket for the primitive/bound/DB-write reasoning
  (identical here).

## Scope

1. Apply `ThreadPoolExecutor` (bound 5) to
   `_capture_submission_bronze_snapshot`'s SEC-fetch call.
2. Re-evaluate whether `BOOTSTRAP_BATCH_CONCURRENCY` > 1 still buys
   anything for `bootstrap-batch` once its SEC-bound phase no longer needs
   cross-task fan-out for throughput -- any remaining benefit would have to
   come from non-network work (DB writes, hashing, orchestration)
   overlapping across tasks, a separate, smaller claim to verify, not
   assume.
3. Does **not** change `load_history`'s use of `bootstrap-batch` xN for
   reasons other than SEC throughput -- narrow scope, not a `load_history`
   Stage 1 redesign.
4. Does **not** cover cross-*command* concurrent execution (two different
   commands running at once) -- that's
   [pipeline-throughput-architecture ticket 09](../../pipeline-throughput-architecture/issues/09-decide-cross-command-sec-fetch-mutual-exclusion.md),
   a separate, still-open architecture decision.

## Test plan

Same 5-category plan as [ticket 77](77-implement-artifact-fetch-concurrency.md),
applied to this loop instead. Additionally: a live measurement across
concurrent `bootstrap-batch` tasks (at whatever `BOOTSTRAP_BATCH_CONCURRENCY`
value point 2 lands on) confirming **aggregate** SEC request rate across
all tasks of the same command stays at or under 10 req/sec -- the actual
compliance proof this ticket exists for.

## Done when

Implemented, tests passing, `BOOTSTRAP_BATCH_CONCURRENCY`'s role
re-evaluated and documented, live measurement confirms aggregate
same-command SEC request rate is compliant.
