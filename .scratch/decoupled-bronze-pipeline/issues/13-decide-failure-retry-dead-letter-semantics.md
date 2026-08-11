# Decide failure/retry/dead-letter semantics for the new async consumers

Type: grilling
Status: resolved
Blocked by: (none)

## Question

[Research AWS messaging substrate options](02-research-messaging-substrate-options.md)
locked the substrate (S3→SNS→two SQS queues per consumer family: a
near-1-batch parallel-worker queue and a larger-batch/timer reducer queue,
optionally via EventBridge Pipes) but didn't design failure handling on
top of it. Decide:

1. **Retry policy per queue**: how many redelivery attempts before a
   message is considered failed, and does the parallel-worker queue and
   the reducer queue need different policies (a failed single-accession
   parse vs. a failed merge across many accumulated deltas have very
   different blast radii)?
2. **Dead-letter handling**: SQS's native DLQ support — where do
   dead-lettered messages go, who/what monitors that queue, and what's
   the operator recovery path (this repo already has an alerting
   precedent: `pipeline_notifications` module, EventBridge→SNS→email on
   Step Functions `FAILED` executions — does DLQ alerting reuse that same
   SNS topic, or does it need its own)?
3. **Poison-message handling**: this repo's existing idempotency/conflict
   machinery (`PromotionConflictError`, immutable bronze writes) already
   distinguishes retryable races from genuine data problems — does a
   message that keeps failing for a *data* reason (e.g. a malformed
   filing) get treated differently from one failing for a *transient*
   reason (e.g. a brief DuckDB lock contention)?
4. **Ordering and duplicate delivery**: SQS standard queues (not FIFO) —
   confirmed by ticket 02's research as the natural fit — don't guarantee
   ordering or exactly-once delivery. Does anything in this pipeline
   (silver's reducer, MDM's export, graph's generation-activate) assume
   ordering or exactly-once semantics that would need to change, or is
   everything already idempotent/order-independent by construction (per
   this repo's "SEC data idempotency" convention)?

## Answer

Decided 2026-08-11, with one finding (Q4) implemented and tested during
this same session rather than left as a design note.

**1. Retry policy per queue — different, and one mechanism already exists.**
Parallel-worker queue: moderate `maxReceiveCount` (3-5) before DLQ — most
failures here are either Fargate Spot interruptions ([ticket
14](14-assess-cost-infrastructure-footprint.md) locked Spot for this
queue; SQS redelivery already self-heals interruptions, that's not a
"failure") or transient errors worth retrying. Reducer queue:
`PromotionConflictError` retries are **already handled inside application
logic** (`_publish_silver_database_with_retry`, existing code) — a
self-contained loop for the *expected* lost-promotion-race case. The
queue's own retry count should be smaller, reserved for genuinely
unexpected errors (the reducer crashing), not re-litigating promotion
races SQS doesn't need visibility into.

**2. Dead-letter handling.** SQS native redrive policy → DLQ. Reuse the
existing `pipeline_notifications` SNS topic for alerting rather than
provisioning a new one — a CloudWatch alarm on each DLQ's message-count
metric would be this repo's first `aws_cloudwatch_metric_alarm` (ticket 14
confirmed zero exist today), but it's a monitoring primitive, not compute,
so it doesn't violate the locked on-demand-only cost stance. Recovery:
operator reviews the DLQ message, redrives via SQS's built-in
redrive-to-source once root cause is fixed, or discards for genuinely bad
input.

**3. Poison-message handling.** No new mechanism — reuses this repo's
existing "fail closed, preserve for retry/review" philosophy
(`PromotionConflictError`, immutable-bronze-conflict handling) at the
queue layer instead of inventing a data-vs-transient classifier. Bounded
retries + DLQ overflow already *is* that distinction: transient failures
usually clear within the retry budget, genuine data problems don't and
land in the DLQ for the same human review this repo's other
conflict-handling paths already expect.

**4. Ordering and duplicate delivery — real gap found and fixed, not just
noted.** Checked all three mechanisms directly. Silver's reducer and
MDM's export are both confirmed order-safe already (ETag-guarded
promotion is inherently order-safe; `MERGE`-based upsert is idempotent by
final-state semantics). **Graph's `activate_graph_generation` was not**:
`_flip_active_pointer` (`edgar_warehouse/mdm/snowflake_graph.py`) validated
only the target generation's *status*, never whether it was newer than the
currently-active one — a real correctness gap once [ticket
10](10-decide-graph-sync-role-in-new-architecture.md) makes graph sync an
automatic per-event consumer over SQS standard queues (no ordering
guarantee, confirmed by ticket 02's research). An out-of-order-delivered
activation could have silently regressed the active graph generation,
degrading all 3 of graph sync's live consumers (ticket 03's finding) with
no error surfaced.

Reviewed via `/gof-refactor-reviewer` (not a pattern problem — a missing
guard clause, same shape as the existing status check, fixable with data
already in the schema) and implemented on branch
`claude/graph-generation-activation-monotonicity`:
- `_flip_active_pointer` gained an `enforce_monotonic` parameter and a new
  `_generation_created_at` helper, comparing the target generation's
  `GRAPH_GENERATION.CREATED_AT` against the currently-active generation's
  before flipping the pointer — using the column already in the schema,
  no new schema change.
- `activate_graph_generation` passes `enforce_monotonic=True`;
  `rollback_graph_generation` passes `enforce_monotonic=False` (rollback
  deliberately targets an older, retained generation — its own
  status-based guard, unchanged, is sufficient).
- The check is skipped (fails open) when no generation is active yet, or
  when `CREATED_AT` data is unavailable (schema guarantees `NOT NULL` in
  production; only relevant to test fakes).
- 4 new tests added to `tests/mdm/test_snowflake_graph_migration.py`:
  reject-older-than-active, accept-newer-than-active, no-guard-on-first-
  activation, rollback-unaffected-by-the-guard. Full existing suite (40
  tests in this file) plus the 4 new ones pass; full repo suite run
  pending confirmation as of this entry.

**Constraint carried from the locked cost stance:** none of this
introduces always-on compute — DLQ alerting is a CloudWatch alarm
(monitoring primitive, not a running process), and the monotonicity check
is inline logic in an already-existing on-demand function call, not a new
service.
