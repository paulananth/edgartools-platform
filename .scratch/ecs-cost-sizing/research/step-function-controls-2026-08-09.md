# Step Functions Concurrency and Failure-Control Investigation

Date: 2026-08-09

This is a read-only production investigation supporting Ticket 07. It records
portable policy and evidence without embedding account IDs, ARNs, user paths,
secret identifiers, or environment-specific resource names in source
configuration.

## Decision summary

Use a versioned `infra/config/aws-step-function-controls.json` as the sole
repository authority for production Step Functions controls. Every Task and
Map state binds an explicit control class. Deployment resolves the class
together with the Workload Profile Contract and emits both contract revisions
and hashes in the generated manifest. Unknown states, generator-local control
blocks, or hash mismatches fail before any AWS mutation.

For parallel-safe, quota-bound fan-out, use an operational concurrency range of
8 through 20. This range is not a global minimum: correctness-bound serial
writers and strict release gates retain explicit limits below 8. No admitted
production work may reserve more than 32 vCPUs in aggregate, and the actual
limit is lower whenever the live Fargate quota minus its protected reserve is
lower.

## Live capacity finding

The production Fargate On-Demand quota was 30 vCPUs and adjustable during the
read-only recheck. A 20% protected reserve therefore limits controlled workload
admission to 24 vCPUs, not 32. One existing medium task was running and using
1 vCPU at the recheck, so a new reservation could use at most 23 vCPUs while
that task remained active.

The account would need a quota of at least 40 vCPUs before the 32-vCPU absolute
ceiling could become the operative limit while preserving the 20% reserve. No
quota change was requested or made.

Admission uses:

```text
admission_ceiling_vcpu = min(32, floor(0.80 * discovered_on_demand_vcpu_quota))

available_vcpu = admission_ceiling_vcpu
                 - outstanding_controlled_reservations_vcpu
                 - observed_unreserved_running_or_pending_vcpu

requested_vcpu = task_vcpu * requested_max_concurrency
```

An allocator must avoid double-counting tasks already covered by an outstanding
reservation. It grants the full request atomically, attaches an execution
identity and expiry, and releases the claim on success, failure, cancellation,
or stale recovery. If the request is unavailable, the workflow waits with
bounded jitter until its policy deadline and then fails with
`ConcurrencyAdmissionTimeout`; it does not partially launch or silently lower
concurrency.

For parallel-safe fan-out:

```text
candidate_max = min(
  20,
  correctness_cap,
  measured_throughput_cap,
  floor(available_vcpu / task_vcpu)
)
```

The fan-out starts only when `candidate_max >= 8`; otherwise it waits or fails
admission. Correctness-bound control classes explicitly opt out of the 8-task
floor and retain their lower fixed cap.

### Resource-tier implications at the current 24-vCPU budget

| Task size | 8 tasks | 20 tasks | Capacity consequence |
| --- | ---: | ---: | --- |
| 0.5 vCPU | 4 vCPUs | 10 vCPUs | Range is capacity-safe; throughput still caps it. |
| 1 vCPU | 8 vCPUs | 20 vCPUs | Full 8-20 range fits when no conflicting reservation consumes the budget. |
| 2 vCPU | 16 vCPUs | 40 vCPUs | Current quota-reserve limit caps the range at 12 tasks before other use; the 32-vCPU absolute ceiling caps it at 16 even after a quota increase. |

## Historical concurrency evidence

The task-bound comparison in
[`workload-class-utilization-2026-08-09.md`](workload-class-utilization-2026-08-09.md)
is decisive for the regular BatchSilver loop:

| Profile / concurrency | Result | Interpretation |
| --- | --- | --- |
| medium / 20 | 680/680 items succeeded in 52m06s | Retain: 20 vCPUs fit below the present admission limit and produced a complete result. |
| large / 16 | 216 succeeded, 1 failed, 15 aborted, 448 pending | Reject: the 32-vCPU request exceeded the live 30-vCPU quota. |
| large / 4 | 240 succeeded before operator abort after 1h32m observed | Safe but materially slower than the validated medium/20 run. |

This evidence establishes 20 for the regular sharded BatchSilver loop. It does
not establish 8 as a safe minimum for every Map. Production conflict and
correctness history still supports strict BatchSilver at 2 and shared canonical
writers at 1.

## Initial concurrency controls

| Workload/state class | Initial limit | Policy |
| --- | ---: | --- |
| Regular sharded BatchSilver | 20 | Required, zero tolerated failure, weighted admission. |
| Strict release BatchSilver | 2 | Correctness-bound exception; required and zero tolerated failure. |
| Shared-DuckDB/canonical writers | 1 | Correctness-bound exception; required and zero tolerated failure. |
| Silver-MDM-Gold BatchSilver | 3 provisional | Keep until representative canaries justify entry into the 8-20 range. |
| Bootstrap-batched | 3 provisional | Change tolerated failure from 10% to zero; evaluate 8 only after correctness and throughput evidence. |
| Generation partitions | 8 provisional | Entry point of the fan-out range; collector semantics may record item outcomes, but unresolved required work must fail the final gate. |
| Optional load-history Stage 1B | 1 | Record-and-gate exception; no forced uplift. |

No current limit below 8 is raised merely to satisfy the target range. A change
from 3 to 8 is a concurrency promotion and must pass the canary, correctness,
speed, cost, quota, and rollback gates.

## Common execution-control contract

The contract has reusable tables for `retry_policies`, `timeout_policies`,
`failure_policies`, `concurrency_policies`, and `state_bindings`, plus a
monotonic `control_revision`. Every binding declares Stage Criticality and
references one policy from each applicable table. The resolved deployment
manifest records the complete class and hash.

### Retry ownership

- Step Functions owns only transient ECS launch or observation failures: two
  retries after the original attempt, 30-second initial delay, exponential
  backoff of 2, 120-second maximum delay, and full jitter.
- Workload-level transient recovery remains command-owned. The same operation
  never has stacked command and workflow retries.
- Timeout, OOM/exit 137, parser, validation, permission, configuration, and
  correctness failures are not retried by Step Functions.
- Remove blanket `States.TaskFailed` retry blocks unless whole-task idempotency
  and an exact transient classification are demonstrated.
- Distributed Maps have no Map-level Retry because retrying a failed Map state
  starts a new Map Run and repeats all child workflows.

### Time bounds

- Evidence-rich states use at least `1.5 * p99` plus 15 minutes of headroom.
- Sparse states use twice the longest representative successful run.
- Workflow timeouts cover the critical path, declared retries, Map waves, and
  20% orchestration headroom, and must remain inside the freshness deadline.
- Timeout is terminal and receives no automatic retry.
- Current ECS `.sync` integrations do not use heartbeat timeouts. A heartbeat
  policy is required only if a callback integration is introduced.

### Failure and completeness

- Required ingestion, reconciliation, MDM verification, generation, and
  release-gate failures cannot lead to a `SUCCEEDED` workflow.
- Catch may clean up and re-fail, record an optional failure then gate,
  reconcile durable item outcomes then gate, or warn for cleanup with an
  independent stale-recovery path. Silent catch-and-continue is noncompliant.
- Default Map tolerated failure is zero.
- Nonzero tolerance is allowed only for a Reconciling Collector Map with an
  immutable per-item outcome ledger and a final Workflow Completeness Gate.
  `100%` collection means collect every outcome, not declare required work
  successful.
- Remove MDM verification fallthrough to gold refresh. Source-ingestion catches
  may proceed only through freshness/completeness checks and a final gate.

## Promotion, rollback, and drift controls

- Normal changes require two representative canaries; high-risk changes
  require three.
- A concurrency increase must improve p95 completion by at least 10%, produce
  no correctness, conflict, quota, or completeness regression, and increase
  cost per validated output by no more than 10%.
- A concurrency decrease must reduce cost by at least 10% and slow p95
  completion by no more than 5%.
- Failure injection proves transient retry, permanent failure, timeout, stuck
  task termination, and every required-failure path.
- Protect the prior control revision until the later of seven days and two
  representative runs, or three for high-risk work.
- An emergency override expires within 24 hours and may only lower concurrency,
  disable retries, increase a timeout, or tighten failure handling. It cannot
  increase concurrency, weaken a completeness gate, or tolerate additional
  failures.
- Before deployment, recursively inventory Task, Map, Parallel, Retry, Catch,
  Fail, and timeout fields and reject unmapped controls or hash drift.
- After deployment, block new starts on unexpected definition/control drift;
  preserve and observe already-running executions under their frozen
  definition.
- Critical signals include required failure reported as success, failed final
  gate, timeout, reservation leak, unexpected contract hash, and unclassified
  retry. Warnings include admission wait, retry-rate increase, use above 80% of
  a time budget, and materially unused reserved capacity.

The evidence record for every execution includes resolved policy identities,
retry ordinal and class, time budget, Map item funnel, reservation lifecycle,
failure disposition, and final completeness result.
