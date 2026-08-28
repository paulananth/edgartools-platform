# Standardize Step Functions Concurrency and Failure Controls

Type: grilling
Status: resolved
Blocked by: 05, 06

## Question

What common contract should production state machines use for Map
`MaxConcurrency`, ECS retry intervals/attempts, timeouts, tolerated failure,
and validation-failure handling? Compare the live workflow families, including
the `bronze-seed-silver-gold` Map concurrency of 20, strict candidate
concurrency of 2, and the residual-holds retry profile. Preserve workload-
specific exceptions only when backed by measured throughput, quota, conflict,
or correctness evidence.

## Answer

Adopt one versioned, fail-closed **Execution Control Contract** at the
repository-relative path `infra/config/aws-step-function-controls.json`. It is
the sole repository authority for production Task and Map concurrency, retry,
timeout, failure-disposition, and completeness controls. Every state binds an
explicit Execution Control Class; deployment resolves the complete class and
records its revision and hash alongside the Workload Profile Contract in the
generated manifest. Unknown states, generator-local controls, and hash drift
fail before AWS mutation.

The accepted concurrency policy is:

- Parallel-safe, quota-bound fan-out targets 8 through 20 concurrent tasks.
- Correctness-bound controls are explicit exceptions: regular sharded
  BatchSilver remains 20, strict release BatchSilver remains 2, shared
  DuckDB/canonical writers remain 1, generation partitions remain 8
  provisionally, and the current 3-task bootstrap and Silver-MDM-Gold Maps move
  toward 8 only after representative promotion evidence.
- Aggregate admitted production work never reserves more than 32 vCPUs. The
  actual ceiling is `min(32, floor(0.80 * live Fargate On-Demand quota))`, less
  outstanding reservations and unreserved running/pending task vCPU.
- The live quota recheck found 30 vCPUs, so today's admission ceiling is 24
  vCPUs. One running 1-vCPU task left 23 vCPUs available at the observation.
  A quota of at least 40 is required before 32 can become usable while
  retaining the 20% reserve. No quota change was made.
- Admission reserves `task_vcpu * MaxConcurrency` atomically. If the complete
  request is unavailable, wait with bounded jitter until the policy deadline,
  then fail `ConcurrencyAdmissionTimeout`; never partially launch or silently
  reduce below the selected policy.

The contract contains `retry_policies`, `timeout_policies`,
`failure_policies`, `concurrency_policies`, `state_bindings`, and a monotonic
`control_revision`. Each state binding declares Stage Criticality and explicit
policy references.

Step Functions is the Retry Owner only for transient ECS launch/observation
failures: two retries after the original attempt, 30-second initial delay,
backoff 2, 120-second maximum delay, and full jitter. Workload recovery remains
command-owned. Do not stack retries or retry timeout, OOM/137, parser,
validation, permission, configuration, or correctness failures. Remove blanket
`States.TaskFailed` and Map-level Retry unless an exact transient class and
whole-operation idempotency are proven.

Every ECS Task and workflow receives an evidence-derived Execution Time
Budget. Evidence-rich tasks use at least `1.5 * p99` plus 15 minutes; sparse
tasks use twice the longest representative success. Workflow bounds include
critical path, retries, Map waves, and 20% orchestration headroom while staying
inside the freshness deadline. Timeout is terminal. Current ECS `.sync` tasks
do not require heartbeat controls.

Default tolerated Map failure is zero. A nonzero value is valid only for a
Reconciling Collector Map with an immutable per-item outcome ledger and a final
Workflow Completeness Gate. Required ingestion, reconciliation, MDM
verification, generation, and release-gate failures cannot lead to
`SUCCEEDED`. Remove MDM verification fallthrough to gold refresh, change the
bootstrap-batched 10% tolerance to zero, and treat generation's 100% as outcome
collection only: unresolved required work must explicitly fail the final gate.

Promotion requires two representative canaries, or three for high-risk work.
A concurrency increase must improve p95 completion by at least 10%, preserve
correctness/conflict/quota/completeness behavior, and add no more than 10% cost
per validated output. A decrease must save at least 10% with no more than 5%
p95 slowdown. Protect the prior revision until the later of seven days and the
required representative runs. Emergency controls expire within 24 hours and
may only lower concurrency, disable retries, increase timeout, or tighten
failure handling.

Pre-deploy drift validation recursively inventories Task, Map, Parallel, Retry,
Catch, Fail, tolerance, and timeout fields. Post-deploy drift blocks new starts
while allowing frozen in-flight executions to remain observable. Required
failure reported as success, failed completeness gates, timeout, reservation
leak, unexpected contract hash, and unclassified retry are critical signals.

The full audit, formulas, initial control matrix, and migration evidence are in
[`step-function-controls-2026-08-09.md`](../research/step-function-controls-2026-08-09.md).
