Type: task
Status: in_progress

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

## Progress (2026-08-03)

**Scope correction during implementation:** the literal target named in this
ticket, `_capture_submission_bronze_snapshot`'s "SEC-fetch call," is
per-CIK -- its own internal loop only exists when `include_pagination=True`
(bootstrap/`load_history`), and is empty for `daily_incremental`
(`include_pagination=False`). But ticket 01's actual measured cost --
48.3min / 10,491 CIKs at 1 SEC call/CIK -- is entirely at the **CIK level**
(the caller's loop, not this function's internal one), and ticket 06's own
stated purpose ("re-evaluate whether `BOOTSTRAP_BATCH_CONCURRENCY` > 1 still
buys anything... once cross-task fan-out is no longer needed for
throughput") only makes sense if the fix operates at CIK level too --
cross-task fan-out distributes CIKs, not pagination files. Both of this
ticket's own justifications point at CIK-level concurrency, not
intra-function pagination-level. Confirmed with a second opinion before
committing to this reading.

**Implemented**, on branch `claude/submissions-fetch-concurrency`:
`_capture_submission_bronze_snapshot` (singular, per-CIK, the function
literally named in this ticket) is replaced by
`_capture_submission_bronze_snapshots` (plural, batch) in
`warehouse_orchestrator.py` -- the sole caller,
`_run_submissions_bronze_then_silver`'s per-CIK loop (the shared function
behind all 5 commands, confirmed unchanged as the call boundary), now makes
one call for the whole CIK list instead of one call per CIK. Two-wave
design, since a CIK's pagination file names aren't known until its main
payload is in hand:
- **Wave 0** (main thread): cache-check every CIK's `submissions_main`
  (`db.get_source_checkpoint` reads -- kept off worker threads, same
  ticket 03 constraint ticket 77 established; confirmed via source reading
  that `SilverDatabase`'s single DuckDB connection has no lock or
  cursor-per-thread pattern anywhere in `silver_store.py`).
- **Wave 1** (pool, bound 5, `WAREHOUSE_SUBMISSIONS_FETCH_CONCURRENCY`):
  fetch the cache misses -- network + bronze write only, no db access.
- **Wave 2**, only if `include_pagination`: cache-check every CIK's
  pagination files (main thread), then fetch the misses through the same
  pool, flattened across all CIKs (not nested per-CIK), maximizing
  concurrency for heavy filers too.

`_capture_submissions_main`/`_capture_submissions_pagination` (the two
functions the old per-CIK function called) were decomposed into a
cache-check half and a fetch half, so the new batch function and the
existing single-CIK callers (`_capture_reconcile_snapshot`, and direct
tests in `test_loader_idempotency.py`) share the same underlying logic with
zero duplication -- both `test_loader_idempotency.py` and
`test_discovery_checkpoint.py` pass unmodified.

`test_submission_phase_order.py`'s 6 patch sites (mocking the old
per-CIK function to assert phase ordering) were updated to mock the new
batch function instead -- turned out not to need any assertion weakening:
since each test's mock is a single call over the whole CIK list, it can
trivially preserve `ciks`-order append semantics, so the exact
`[bronze:1001, bronze:1002, bronze:1003, silver:1001, ...]` ordering
assertion in `test_bulk_submission_flow_captures_all_bronze_before_silver`
holds unchanged.

**Test plan items 1-4**: done, all passing, stable across repeated runs.
New file `tests/unit/test_submissions_fetch_concurrency.py` (5 tests):
correctness equivalence (concurrent vs. env-var-forced-sequential, both
`include_pagination=False` and `=True` paths, including a two-wave CIK),
rate-limiter compliance (real, unmocked `pyrate_limiter.Limiter`), DB-access
serialization (thread-id-recording double, 100% of
`db.get_source_checkpoint` calls -- across both waves -- on the main
thread), partial-failure equivalence (one CIK's fetch fails among several
concurrent, batch raises the original exception, returns nothing), plus a
cache-hit test confirming `force=False` still skips the network entirely
and `on_progress` still fires. Full `tests/unit` + `tests/architecture`
suite green (932 passed; same pre-existing, unrelated `AWS_PROFILE`
wizard-test failure as ticket 77, confirmed present on `main`).

**`BOOTSTRAP_BATCH_CONCURRENCY` re-evaluation (point 2, documented, not
changed):** with this fix live, `bootstrap-batch`'s SEC-bound phase no
longer needs cross-task fan-out for throughput -- one task now drives up to
5 concurrent CIK fetches itself. The only work `BOOTSTRAP_BATCH_CONCURRENCY
> 1` could still buy is non-network overlap *across* tasks (DB writes,
hashing, orchestration) -- but `_apply_submission_snapshot_to_silver`'s
loop (the actual DB-write phase) is unaffected by this ticket and remains
per-task sequential regardless, so that overlap is real but almost
certainly small relative to the SEC-bound phase this fix already
parallelizes. **Recommendation: `BOOTSTRAP_BATCH_CONCURRENCY=1`** is very
likely the compliant, near-zero-throughput-cost setting once this ships --
consistent with ticket 06's own original point ("the only compliant
task-count-only fix would be `BOOTSTRAP_BATCH_CONCURRENCY=1`"). **Not
applied in this PR** -- `infra/scripts/deploy-aws-application.sh` is
untouched, per this ticket's own scope note 3 (not a `load_history` Stage 1
redesign) and to keep the decision measurable rather than assumed: this
needs the live aggregate-rate measurement below to confirm before the
deployed default changes.

**Test plan item 5 (live measurement, including the aggregate-rate
compliance proof): not done**, for the same reason as
[ticket 77](77-implement-artifact-fetch-concurrency.md) -- requires
deploying to prod, and prod's
`daily-incremental-ticket74-repair-verify-1785752569` was still running at
last check. Per
[pipeline-throughput-architecture ticket 09](../../pipeline-throughput-architecture/issues/09-decide-cross-command-sec-fetch-mutual-exclusion.md),
running two SEC-fetching commands concurrently is a real compliance risk,
not yet guarded by an actual lock ([ticket 80](80-implement-cross-command-sec-fetch-lease.md),
still open) -- so no new prod execution should be triggered until that run
finishes.
