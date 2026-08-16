# Resolve the Invocation Path and Secret Plumbing

Type: grilling
Status: resolved

## Question

Surfaced by the Opus design-review pass (see
[DESIGN-SUMMARY.md](../DESIGN-SUMMARY.md), findings G4 and G5) — both
block writing code, not just design polish.

**G5 — the invocation path was left as an unresolved "or."**
[Ticket 02](02-design-idle-detection-recheck-and-race-safety.md)'s answer
says the new command is invoked "as an ECS task from a Step Functions
state **or** directly from the EventBridge rule's target," and never
chooses. This decides:
- **Retry semantics** — does a failed invocation get retried at all (see
  the related question in [ticket 07](07-decide-lost-fire-retry-and-snowpipe-timing.md)
  about whether retries are wanted in the first place)?
- **IAM** — an EventBridge rule targeting ECS directly needs `ecs:RunTask`
  + `iam:PassRole` on the EventBridge rule's execution role; a Step
  Functions intermediary needs its own state-machine role instead.
- **How `detail.executionArn` reaches the command** — an EventBridge input
  transformer (if targeting ECS directly) vs. Step Functions' native
  `$.detail` passthrough (if going through an SFN state) are different
  plumbing.
- **Network/subnet configuration** for the ECS task launch.

**G4 — ticket 03's "reuse `MDM_SNOWFLAKE_SECRET_JSON`, zero new grants" is
true for Snowflake, false for AWS.** `MDM_SNOWFLAKE_SECRET_JSON` is
injected only into the **MDM** container definition
(`infra/scripts/deploy-aws-application.sh:1125-1134` — that block uses
`$MDM_IMAGE_REF`, `command: ["mdm", "--help"]`, awslogs prefix
`mdm-{profile}`). The **warehouse** task definitions — where
[ticket 02](02-design-idle-detection-recheck-and-race-safety.md) put the
new command — do not carry it. `mdm export`/`mdm sync-graph`/
`mdm verify-graph` (the precedent ticket 03 cited) all run on the MDM
task-definition family, not the warehouse one — so "same pattern as those"
doesn't compose with "new command on the warehouse image" as currently
written.

The image itself is not the obstacle: `Dockerfile.warehouse-deps` installs
`--extra s3 --extra mdm-runtime`, and `mdm-runtime` includes
`snowflake-connector-python>=3.7` (`pyproject.toml:59-66`) — the warehouse
image can already make the connector call. The gap is purely task-definition
wiring.

Decide one of:
1. **Add `MDM_SNOWFLAKE_SECRET_JSON` to the warehouse container's
   `secrets` block**, plus `secretsmanager:GetSecretValue` on that ARN for
   the warehouse execution role — keeps the new command on the warehouse
   image (ticket 02's choice) at the cost of a new IAM/secrets wiring
   change to that task-definition family.
2. **Run the new command on the MDM task-definition family instead**,
   which already has both the secret and the role — no new AWS wiring,
   but revisits ticket 02's "warehouse image" choice (was that choice
   actually about the image, or just about "not Lambda"? If the latter,
   MDM task-def still satisfies it).

## Answer

Both G4 and G5 turned out smaller than framed, once two facts were
checked directly against the Terraform/deploy source rather than assumed.

**G4 resolution: there is no IAM gap. Stay on the warehouse image; add one
line to its container definition.**

`register_mdm_task_definition` (`deploy-aws-application.sh:1149-1166`)
registers MDM task definitions with the exact same
`--execution-role-arn "$EXECUTION_ROLE_ARN"` / `--task-role-arn
"$TASK_ROLE_ARN"` as `register_task_definition` (the warehouse one) — the
two task-definition families share **one** IAM execution role, not two.
That shared role's secret policy
(`aws_iam_role_policy.ecs_task_execution_warehouse_secret`,
`infra/terraform/access/aws/modules/runtime_access/main.tf:179-198`)
already grants `secretsmanager:GetSecretValue` on
`concat([var.edgar_identity_secret_arn], var.mdm_secret_arns)`, and
`mdm_secret_arns` (`infra/terraform/access/aws/accounts/prod/main.tf:38-43`)
already includes `mdm_snowflake_secret_arn` — the exact secret ARN behind
`MDM_SNOWFLAKE_SECRET_JSON`. So the warehouse execution role can already
fetch this secret today; nothing in Terraform needs to change. The only
actual gap is that no warehouse container-definition-writer function
currently lists it in its `secrets` array — the fix is adding that one
entry (referencing the already-granted ARN) wherever the new command's
container definition gets built, not new IAM/Terraform. Confirmed via
`pyproject.toml:59-66` that the warehouse deps image (which installs
`--extra s3 --extra mdm-runtime` per `Dockerfile.warehouse-deps`) already
has `snowflake-connector-python` through the `mdm-runtime` extra — the
image was never the obstacle either.

**Decision: stay on the warehouse image** (ticket 02's original choice),
not the MDM task-definition family — both are now equally cheap
IAM/dependency-wise, so the tiebreaker is naming/semantic fit: this
command is operational glue (polls Step Functions, calls one Snowflake
procedure), the same shape as `release-sec-fetch-lease` and this map's own
sibling effort's `backfill-mdm-entity-ids` — not an entity-resolution
operation, so it doesn't belong under the `mdm` CLI subcommand namespace
alongside `mdm run`/`mdm export`/`mdm sync-graph`.

**G5 resolution: invoke through a minimal single-state Step Functions
machine, not EventBridge→ECS directly.**

This repo has zero precedent for an EventBridge rule targeting ECS
`RunTask` directly — building that would need a brand-new IAM role
(`ecs:RunTask` + `iam:PassRole` for `events.amazonaws.com`) from scratch.
It has two *existing*, already-battle-tested patterns that compose
directly into what's needed instead:

1. **`write_single_workflow_definition`** (already used for `gold_refresh`
   itself, among others) — a state machine wrapping exactly one ECS task,
   giving `Retry: [{"ErrorEquals": ["States.TaskFailed"], ...}]` for free
   via the shared `ecs_state()` helper every other workflow in this script
   already relies on. This directly answers [ticket 07](07-decide-lost-fire-retry-and-snowpipe-timing.md)'s
   G1 concern about the ECS task itself failing to start — it's already
   retried by the same mechanism as every other task in this repo,
   without inventing anything new.
2. **`configure_daily_incremental_schedule`**'s EventBridge rule (already
   targets a state machine via `StartExecution`, with a dedicated small
   IAM role for the rule) — the same shape works here with a per-event
   dynamic `InputPath: "$.detail"` instead of a fixed cron payload, so
   `detail.executionArn`/`detail.status`/etc. from the triggering
   `Step Functions Execution Status Change` event become the new SFN
   execution's Input, passed through to the ECS command expression like
   every other parameterized task in this script (e.g. `$$.Execution.Name`
   passthrough already used throughout `gold-refresh` calls). This
   directly gives [ticket 07](07-decide-lost-fire-retry-and-snowpipe-timing.md)'s
   G1 mitigation ("explicitly exclude the triggering execution from the
   RUNNING set") the data it needs, with no new transformer logic.

Network/subnet configuration for the ECS task launch is also settled by
this choice — it's identical to every other `ecs_state()`-driven task in
this script (`PUBLIC_SUBNET_IDS_JSON`/`SECURITY_GROUP_IDS_JSON`), not a
new decision.
