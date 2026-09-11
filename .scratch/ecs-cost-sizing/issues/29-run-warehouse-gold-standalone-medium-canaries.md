# Run `warehouse.gold_standalone` Medium Canaries

Type: task
Status: blocked
Blocked by: matched Snowflake input-envelope identity and exercised recovery evidence

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

## Restarted (2026-09-10) — measurement only after DuckDB retirement

The branch was rebased onto current `origin/main` and the canary contract was
reconciled with the completed DuckDB retirement. `gold-refresh` no longer
hydrates or publishes `warehouse/silver/sec/silver.duckdb`; its remaining five
orphan evidence exports read Snowflake `EDGARTOOLS_SILVER` directly. The old S3
ETag/size input-identity gate was therefore removed rather than allowed to
validate a stale object.

The repaired evaluator can measure task-bound CPU/memory, duration, estimated
Fargate compute cost, exact Gold manifest/Snowflake-export output parity, and
cross-run idempotency. It now enforces the complete large-control -> medium-1 ->
medium-2 order and scans for ECS overlap across the whole cohort window,
including the gaps. Output hashes are labeled only as output identity.

This rerun cannot resolve Ticket 29 or promote `medium`: the current production
image does not emit a real Snowflake input-envelope identity/count contract, and
the success-path runs do not exercise recovery. The evaluator deliberately
reports performance results separately while keeping both `sizing_gates_passed`
and overall `passed` false until those two evidence seams exist.

### Rerun outcome (2026-09-10)

After the concurrently running MDM generation finished, a fresh isolated cohort
completed on source `large:289`, candidate `medium:294`, image digest
`sha256:239612ad...a05542a`, and source ASL hash `5d92be2d...d6cc`:

- control `ticket29-gold-control-4-20260910T231743Z`: 103.823s end to end,
  83.078s billed, $0.002719 estimated compute, 13.77% CPU p95, 0.89% memory
  peak/p95;
- medium `ticket29-gold-3-20260910T232130Z`: 104.216s end to end, 86.638s
  billed, $0.001408 estimated compute, 46.80% CPU p95, 5.32% memory peak/p95;
- medium `ticket29-gold-4-20260910T232632Z`: 87.109s end to end, 70.397s
  billed, $0.001149 estimated compute, 54.89% CPU p95, 5.91% memory peak/p95.

Every execution exited zero without retry. The combined control-start through
candidate-2-stop overlap scan found no other ECS task. All three runs produced
the same exact five-table output identity (`bb81b054...963a3`) and 470,101-row
funnel, so output correctness and cross-run idempotency passed. Candidate p95
duration was 103.361s, 0.45% faster than control, and candidate p95 estimated
compute cost was $0.001395, 48.69% lower than control. These performance gates
passed.

Overall and sizing qualification remain fail-closed: matched Snowflake input
envelope was not captured, and recovery was not exercised. No production task
definition or profile reference was changed. The earlier control-3/candidate-2
pair is diagnostic only because its reporting window expired before the cohort
could be completed.

## Input-envelope seam implemented (2026-09-11) — deployment and evidence pending

The missing input-envelope capability is implemented on
`codex/ticket29-snowflake-input-envelope`, but this statement is code/test
readiness only: no image has been published, no canary definition has been
applied, and no new production evidence has been collected.

The Ticket 29 canary clone now appends
`--input-snapshot-at $.input_snapshot_at` to the otherwise unchanged
`gold-refresh` command. The runtime normalizes that timezone-aware value to UTC,
uses the same Snowflake Time Travel timestamp for all five direct
`EDGARTOOLS_SILVER` reads, and captures an envelope containing the Snowflake
account/database/schema, exact source-table and selected-column allowlist,
per-table row counts, query IDs, and a deterministic SHA-256 identity. The
envelope is repeated in the three Gold lifecycle events and stored in durable
pipeline-run metrics.

The offline evaluator independently validates the envelope schema, allowlist,
counts, selected columns, query-ID presence, and claimed digest; binds the
runtime snapshot back to the launch manifest; and requires the control plus
both candidates to have identical envelope identities. Query IDs remain audit
provenance and are deliberately excluded from cross-run equality because each
Snowflake statement receives a distinct ID.

Before the next cohort, publish/deploy one immutable image containing this
change, prepare both current-image canary definitions, choose one timestamp a
few seconds in the past but within all five tables' Time Travel retention, and
pass that exact value to the Large control and both Medium candidates. Gate 1
closes only when `evaluate-gold` reports
`input_envelope_evidence.passed=true`; exercised recovery remains the final
independent blocker.

Local verification on 2026-09-11: `1597 passed, 6 skipped`, plus 29 passing
subtests, for `tests/unit tests/architecture`.

## Parked (2026-09-01)

Per operator direction, stop this cohort and restart it only after all Step
Functions fixes are complete and deployed. No Ticket 29 execution is currently
running. Do not reuse the existing control/candidate runs as promotion evidence:
they remain diagnostic history because image/definition drift and production
writer overlap prevented a qualifying current-image cohort.

Restart procedure after the blocker clears:

1. fetch/rebase onto current `origin/main` and re-run the dry-run GoF/design and
   code-review gates;
2. re-query the live `gold_refresh` definition, current warehouse profiles,
   image digest, and running/pending ECS tasks;
3. prepare fresh immutable unscheduled control/candidate definitions from that
   exact live source;
4. require a writer-free window for the complete control plus two sequential
   medium executions, with full-window overlap evidence;
5. evaluate correctness, funnel, structural recovery, idempotency, telemetry,
   p95 duration, and validated-output cost; and
6. keep sizing/promotion unqualified until a matched Snowflake input-envelope
   contract and exercised recovery evidence are captured.
