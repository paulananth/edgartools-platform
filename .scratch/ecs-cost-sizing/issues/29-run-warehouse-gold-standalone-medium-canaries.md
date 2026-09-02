# Run `warehouse.gold_standalone` Medium Canaries

Type: task
Status: open
Blocked by: none

## Question

Run and record the outcome of two representative `medium`-profile canaries
for `gold_refresh` (the `warehouse.gold_standalone` workload class),
required by Ticket 03's standard two-canary downgrade gate before `large`
can be reconsidered as the operational tier.

Zero canaries have run as of this ticket — the only executions on record
(Ticket 02, reused by Ticket 13) are both the existing `large`-profile
baseline, not a `medium` trial. Given `gold_refresh`'s own measured shape
(Ticket 13: a flat ~$0.005/invocation, ~151s billed, cost and duration
essentially independent of the ~20.87M-row snapshot size it re-exports),
this looks like a low-risk, cheap canary to run relative to the other
pending cohorts in this map — worth scheduling promptly.

Record execution ARNs, task-bound CPU/memory peaks, duration, and pass/fail
against Ticket 03's gate (memory peak ≤85%, memory p95 ≤75%, p95 end-to-end
time regression ≤5%, no correctness/completeness/idempotency regression) on
resolution.

## In progress (2026-09-01) — current-image cohort waiting for a clear writer window

`scripts/ops/ecs_sizing_canary.py` now supports a Ticket 29-only dry-run,
immutable unscheduled `gold-control`/`gold` state-machine preparation, globally
unique execution attempts, fail-closed cluster-concurrency checks, automatic
versioned canonical-silver identity capture, task-bound reports, and an offline
cohort evaluator. The evaluator requires one large control and exactly two
medium candidates to share the source-definition hash, image digest, silver
content identity (ETag plus size), normalized gold manifest (row counts, byte
sizes, and Parquet SHA-256 values), and canonical Snowflake export mapping. It
then applies the local execution gates, the 5% candidate-p95 duration guardrail,
and the 10% minimum candidate-p95 cost reduction.

An initial matched pair completed on the then-current digest
`sha256:87b4690b...f87f07` (`large:233` control, `medium:238` candidate). Both
exited zero with no retry and produced byte-identical normalized 28-table gold
manifests (20,824,093 rows). The medium run stayed well inside memory gates
(29.71% max, 29.13% p95) and cost 37.45% less ($0.004758 vs. $0.007606), but
was 22.89% slower end to end (308.340s vs. 250.917s), failing the 5% speed
guardrail. A subsequent production rollout changed the live task definitions
and digest, so this pair is retained as diagnostic evidence only and cannot
qualify the current-image cohort.

Fresh immutable canaries were prepared from the live production definition:

- source `edgartools-prod-large:236`, candidate `edgartools-prod-medium:241`;
- shared image digest `sha256:b3a16183...fcc247fe`;
- source ASL hash `0b5921fc...240e1e7`; and
- exactly one task-definition reference changed in the medium clone, with no
  schedules, aliases, or production reference updates.

Current-image large control attempt 2 succeeded as
`ticket29-gold-control-2-20260902T001736Z` (execution ARN and full evidence in
`evidence/ticket29/`). It exited zero without retry, ran 282.664s, cost
$0.008642, used 17.85% maximum / 16.76% p95 memory and 42.40% p95 CPU, and
produced 28 tables / 21,248,534 rows. Its launch captured silver ETag
`0032cf8c442576bbf21aeea6a8e8ae53`, 1,800,417,280 bytes, version
`fCDQ9WRaUM1qNT1CvNT2ckLQ920csIvO`.

The candidate launch is currently blocked by new production writer tasks: a
`daily-incremental` rerun and `load-daily-form-index-for-date` began after the
control launched. They can republish canonical silver, so no candidate will be
started until the cluster is writer-free and the captured content identity can
be matched. If their publish changes the ETag or size, the control is
non-qualifying and a fresh control must precede both medium candidates. Ticket
29 remains open; no profile promotion or production reference change has been
made.
