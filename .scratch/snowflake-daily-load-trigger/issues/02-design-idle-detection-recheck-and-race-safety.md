# Design the Idle-Detection Re-Check and Race Safety

Type: grilling
Status: resolved

## Question

Round 2 of this map's grilling settled the shape (EventBridge rule on
Step Functions execution-status-change events for the 7 gold-affecting
state machines, feeding a re-check of whether anything else in the
watched set is still `RUNNING`) but not the mechanics:

1. **What runs the re-check?** A Lambda (cheapest, fastest cold start,
   but a new runtime/deploy surface this repo doesn't currently have —
   everything else here is ECS/Step Functions) vs. a small one-off ECS
   task on the existing warehouse task-definition family (reuses existing
   image/IAM/networking patterns, slower cold start, costs a Fargate
   task-start rather than a Lambda invocation).
2. **Exact EventBridge event pattern**: match on `source:
   aws.states`, `detail-type: "Step Functions Execution Status Change"`,
   filtered to the 7 watched state machine ARNs and terminal
   `detail.status` values (`SUCCEEDED`, `FAILED`, `ABORTED`,
   `TIMED_OUT`) — confirm this is sufficient or whether additional
   filtering is needed (e.g. excluding child/Map-run executions so the
   rule only reacts to top-level workflow completions, not every
   `WindowedBootstrap`/`BatchSilver` iteration).
3. **Race safety**: between an event firing and the re-check completing,
   could a new execution start in one of the other 6 watched machines and
   get missed (i.e. the load fires while something is still genuinely in
   flight)? `list-executions --status-filter RUNNING` at re-check time is
   the obvious guard, but confirm there's no gap where a machine has
   already transitioned out of `RUNNING` internally (e.g. is about to
   call `AcquireSecFetchLease` on a fresh execution) without yet
   registering as `RUNNING` in the API's eventual consistency window.
4. [Decide Once-Per-Day Debounce/Cap Semantics](01-decide-once-per-day-debounce-cap-semantics.md)
   resolved to "no cap, fire on every genuine busy→idle transition" — no
   "already fired today" flag needs to be read/written here. What still
   needs designing is the ordering within a single re-check: two
   near-simultaneous terminal events for different watched machines must
   not both independently conclude "idle" and double-fire for the same
   transition (e.g. via a short-lived lock/marker for the duration of one
   re-check, not a daily-scoped one).

## Answer

1. **Compute: a small one-off ECS task on the existing warehouse image**,
   not Lambda. `grep -r aws_lambda_function` across all of
   `infra/terraform/` returns nothing — this repo has zero Lambda
   functions anywhere; every workload is ECS/Fargate + Step Functions.
   The new re-check/fire step is a new single-purpose CLI command (same
   shape as `release-sec-fetch-lease` and every other warehouse command:
   `COMMAND_REGISTRY` entry, `planned_manifest_paths`/`_resolve_scope`
   cases, invoked as an ECS task from a Step Functions state — **resolved
   by [ticket 06](06-resolve-invocation-path-and-secret-plumbing.md) as a
   minimal single-state SFN wrapping the task, not directly from the
   EventBridge rule's target** — reusing the existing image, IAM
   role, deploy pipeline, and logging conventions rather than introducing
   a new runtime paradigm for one narrow use case. EventBridge itself is
   not new (the `daily_incremental` cron rule already uses it,
   `infra/scripts/deploy-aws-application.sh:509`) — only giving it a
   compute target is.

2. **Don't filter Distributed Map child/window executions out of the
   EventBridge pattern.** Confirmed live: `Mode: DISTRIBUTED,
   ExecutionType: STANDARD` appears at 10 call sites in
   `deploy-aws-application.sh` (`load_history`'s windowed bootstrap,
   `silver_mdm_gold`'s `BatchSilver` map, etc.) — each iteration is a
   real, separately-ARN'd execution of the same state machine, and each
   one emits its own `ExecutionStatusChange` event and appears in
   `list-executions`. React to every terminal event for the 7 watched
   ARNs, including child/window completions, rather than trying to match
   only top-level executions. Cost: a heavily-windowed run (e.g. 53
   windows) triggers ~53 re-checks instead of 1 — each one cheap (a
   `list-executions --status-filter RUNNING` call), and every premature
   one correctly no-ops because the parent execution and sibling windows
   still show `RUNNING`. The alternative (filtering by Map-run child
   execution ARN shape) would depend on internal AWS ARN structure this
   repo has no contract with, and a filtering bug there fails silently —
   it would suppress the *one* event that should have fired, not just
   produce an extra no-op.

3. **Race safety: no new distributed lock.** `stream_processor_procedure.sql`
   consumes the manifest stream via a single `INSERT ... SELECT`, the
   mechanism that atomically advances a Snowflake stream's offset —
   concurrent calls can't both process the same manifest rows twice by
   construction. Combined with a fresh `list-executions
   --status-filter RUNNING` re-check immediately before the fire step
   (mirroring `_publish_shard_if_remote`'s existing re-read-baseline-
   right-before-promote pattern, `edgar_warehouse/application/
   warehouse_orchestrator.py`), this closes the practical race window
   without new infrastructure. This repo has zero DynamoDB usage
   anywhere (`grep -r dynamodb` across `infra/` and `edgar_warehouse/`
   returns only Terraform's own state-locking backend) — a dedicated
   lock table would be new infra solving a race that Snowflake's own
   stream semantics already close.

**Consequence for [ticket 03](03-decide-invocation-plumbing-and-task-object-fate.md):**
its "Lambda-vs-ECS" framing (in the credential-plumbing sub-question) is
now settled as ECS. **Correction (Opus design-review pass, finding G4 —
see [DESIGN-SUMMARY.md](../DESIGN-SUMMARY.md)):** "whatever an ECS task on
the warehouse image can already reach" turned out to be wrong —
`MDM_SNOWFLAKE_SECRET_JSON` is only wired into the MDM task-definition
family, not the warehouse one, so this consequence doesn't hold as stated.
Resolved in [ticket 06](06-resolve-invocation-path-and-secret-plumbing.md).

**Addendum (same review pass, finding G7):** point 2 above ("react to
every terminal event... every premature one no-ops because the parent
execution and sibling windows still show RUNNING") assumes
`list-executions --state-machine-arn` enumerates Distributed Map child
executions. Worth a live check before implementing — the API takes
*either* `stateMachineArn` *or* `mapRunArn`, which suggests children may
only be listable under the latter. The conclusion (premature fires no-op)
survives either way, because the **parent** execution is itself a
top-level execution and stays `RUNNING` for the whole Map state — but
don't build logic that depends on child executions specifically being
listable via the state-machine-scoped call.
