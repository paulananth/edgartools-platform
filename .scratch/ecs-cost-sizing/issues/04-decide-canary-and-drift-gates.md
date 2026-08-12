# Decide ECS Sizing Canary, Rollback, and Drift Gates

Type: grilling
Status: resolved
Blocked by: 03

## Question

What evidence is required before changing a workload's task profile? Define
canary scope, success/failure thresholds, OOM handling, runtime tolerance,
cost comparison, rollback target, and Container Insights drift alerts. Gates
must fail closed when utilization evidence is missing.

## Answer

Task-profile changes use an isolated, stage-scoped canary and promotion
contract. Missing identity, metrics, output evidence, or reference visibility
fails closed.

### Canary isolation and scope

- Generate a temporary, unscheduled Standard **Sizing Canary Definition** from
  the current production definition. Change only the candidate task-profile
  references; bind immutable candidate revisions and a Representative Input
  Envelope. Do not attach schedules, aliases, or live triggers.
- A canary must exercise the same orchestration, Catch behavior, output gates,
  and downstream validation as the covered production stage. A direct
  `RunTask` smoke test is supplementary, not promotion evidence.
- Use the two normal or three high-risk representative executions required by
  **Decide Sizing Safety Floors and Utilization Bands**. Every attempt receives
  a fresh execution identity; never redrive a failed execution whose definition
  is frozen at start.
- Sizing Promotion changes only the workload stages covered by the accepted
  evidence. Sharing an ECS family does not authorize changing its other
  consumers.
- Generate and validate every intended definition before changing live
  references. Record the update set as one transaction, then recursively audit
  all 26 production definitions against the expected exact task-definition
  ARNs and ASL hashes. The current sequential all-workflow deploy path is not a
  valid canary mechanism and needs staged-transaction support before it can
  implement this policy.

### Canary acceptance and rejection

Every required canary must satisfy all of these gates:

- complete Sizing Evidence Identity and task-bound telemetry;
- correctness, output identity, record-funnel, recovery, completeness, and
  idempotency parity with the control;
- zero workload-attributable task failures or retries;
- memory peak below 85% and memory p95 below 75%;
- p95 end-to-end completion no more than 5% slower than the matched baseline;
  and
- at least 10% lower Fargate cost per successful validated output, including
  candidate retries and task billing time.

CPU p95 at or above 90% marks the candidate constrained but does not reject it
when correctness and the completion-time guardrail pass. CPU-only saturation
can be an efficient profile choice; memory exhaustion cannot.

One OOM/exit 137, incorrect or incomplete output, workload-attributable retry,
correctness failure, missing required telemetry, memory-band breach,
completion-time breach, or insufficient cost improvement rejects the
candidate immediately. Do not average a Hard Sizing Failure away. An unrelated
AWS infrastructure interruption neither proves nor rejects workload sizing;
preserve it and run a fresh attempt that does not count the interrupted run
toward the required cohort.

### Rollback identities and response

Configuration Rollback and Code Rollback are distinct:

- **Configuration Rollback** restores the exact pre-change state-machine
  definitions, task-definition ARNs, profile resources, image digests, and ASL
  hashes while preserving the application code/image identity.
- **Code Rollback** restores a separately attested prior image cohort and its
  compatible definitions. The exact cohort is owned by **Decide and Capture the
  Protected Rollback Cohort**; this ticket does not designate it.
- Neither target may come from `latest`, mutable tags, family-only references,
  revision adjacency, or a reconstructed approximation.

A failed pre-promotion canary never changes live references. After promotion,
a Hard Sizing Failure automatically freezes new starts for the affected
workflow and pages the operator. The operator-confirmed Configuration Rollback
must restore the exact pre-change definition within 15 minutes, recursively
audit all 26 workflow hashes and references, preserve failed evidence,
quarantine invalid output, and pass a fresh bounded smoke execution before
reopening. Do not redrive the failed execution. Utilization alarms never
initiate an autonomous Code Rollback.

### Evidence invalidation and drift gates

Any change to the image digest, command, task resources, relevant ASL path,
dependency/runtime configuration, or input beyond the Representative Input
Envelope creates **Sizing Evidence Drift**. Production may continue on its
Operational Profile, but stale evidence cannot authorize another promotion,
retirement, or cleanup action until new canaries pass.

Task-bound drift evaluation produces:

- **Critical:** any OOM/exit 137, incorrect or incomplete output, unexpected
  task-definition reference, or required telemetry still missing 15 minutes
  after task stop.
- **Constrained warning:** memory peak at least 85%, memory p95 at least 75%,
  CPU p95 at least 90%, completion regression above 5%, workload retry
  regression, or realized savings below 10%.

Family-level Container Insights metrics remain advisory and cannot trigger a
promotion or rollback. Missing task-bound evidence is not healthy data.

The **Sizing Bake Window** lasts until the later of seven calendar days and two
representative production executions, or three for a workload with prior OOM,
transient-memory risk, or incomplete source coverage. Protect the exact
Configuration Rollback and retain heightened monitoring throughout that
window.

One constrained warning does not roll back. Two consecutive memory,
completion-time, retry, or cost violations freeze affected starts and invoke
the operator-confirmed Configuration Rollback. CPU-only constraint does not
roll back while correctness and completion speed pass. Hard Sizing Failures
always take the immediate critical path above.

This ticket defines policy only. Telemetry implementation remains with the
execution/loop telemetry decision; staged deployment and reference-drift
implementation remain with the profile-contract, rollout, and stale-revision
decisions.
