# Phase 3: Failure Notifications - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Add automated SNS email notification when any of the 5 edgartools Step Functions state
machines reaches FAILED state. Implement using EventBridge (single catch-all rule) → SNS
topic → email subscription, all Terraform-managed in a new `pipeline_notifications` module.

**In scope:**
- New Terraform module `infra/terraform/modules/pipeline_notifications/`
- SNS topic (`edgartools-{env}-pipeline-failures`) and email subscription
- SNS topic policy allowing EventBridge to publish
- EventBridge rule (catch-all for all 5 state machines reaching FAILED)
- EventBridge target wiring the rule to the SNS topic
- `subscriber_email` Terraform variable in the new module and in `accounts/dev/` invocation
- Human-readable SNS message with subject, pipeline name, execution ARN, timestamp,
  Step Functions console link, and CloudWatch log group link with time filter
- Dev environment deployment and verification (trigger a FAILED execution, confirm email arrives)

**Out of scope:**
- Lambda transformer for exact task-level log stream deep-link (deferred — log group link is sufficient)
- Per-state-machine granularity (one rule covers all 5 machines)
- Prod account application (wire prod in a follow-up; dev is the target environment)
- Dashboard or status.sh changes (Phase 2)

</domain>

<decisions>
## Implementation Decisions

### CloudWatch link depth
- **D-01:** No Lambda. The notification body includes a link to the CloudWatch log group
  (`/aws/ecs/edgartools-{env}-warehouse`) with a time filter centered on the failure
  timestamp. Operator finds the failing task log stream within ~30 seconds by scanning the
  group. Getting the exact log stream requires querying `GetExecutionHistory` — deferred as
  complexity not worth the benefit for a dev-environment alert.

### EventBridge rule scope
- **D-02:** Single catch-all `aws_cloudwatch_event_rule` targeting all 5 state machines.
  Event pattern: `source: ["aws.states"]`, `detail-type: ["Step Functions Execution Status Change"]`,
  `detail.status: ["FAILED"]`, with `detail.stateMachineArn` prefix-matched on
  `arn:aws:states:{region}:{account_id}:stateMachine:edgartools-{env}`. No per-machine
  rules — one rule, one target, one SNS topic.

### Terraform structure
- **D-03:** New reusable Terraform module at `infra/terraform/modules/pipeline_notifications/`.
  Module inputs: `environment`, `name_prefix`, `aws_region`, `account_id`,
  `subscriber_email`. Called from `infra/terraform/accounts/prod/main.tf` (dev deployment target).
  Follow the existing `warehouse_runtime` module pattern (locals for name_prefix + tags,
  resources, outputs). The `subscriber_email` variable has no default — operators must
  supply it explicitly.

### Email format
- **D-04:** Human-readable plain-text email. Subject line:
  `[EdgarTools] Pipeline FAILED: {pipeline_name}`.
  Body contains labeled fields:
  - Pipeline: `{pipeline_name}` (extracted from `stateMachineArn` suffix)
  - Execution ARN: `{executionArn}`
  - Failed at: `{stopDate}` (UTC)
  - Step Functions console: `https://console.aws.amazon.com/states/home?...`
  - CloudWatch logs: link to log group `/aws/ecs/edgartools-{env}-warehouse` with
    startTime= (stopDate minus 30 min) and endTime= (stopDate plus 5 min) encoded in URL
  The SNS message is formatted using an EventBridge input transformer (no Lambda) —
  `inputPathsMap` extracts fields from the event; `inputTemplate` formats the body.

### SNS topic naming
- **D-05:** New dedicated SNS topic `edgartools-{env}-pipeline-failures` — separate from the
  existing `snowflake_manifest_events` topic (different concern, different subscriber).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Terraform patterns (follow these conventions)
- `infra/terraform/modules/warehouse_runtime/main.tf` — module structure, locals pattern,
  SNS topic resource pattern, tag merging convention
- `infra/terraform/accounts/prod/main.tf` — module invocation pattern (how modules are
  called from the account root; note this is the dev deployment target despite "prod" path)
- `infra/terraform/accounts/prod/variables.tf` — variable declaration pattern

### State machine names (EventBridge filter values)
- `infra/scripts/deploy-aws-application.sh` lines 1579–1751 — `upsert_state_machine` calls
  establish the actual state machine names. Names use underscores:
  `bootstrap_phased`, `silver_mdm_gold`, `gold_refresh`, `mdm_gold`, `ownership_mdm_gold`.
  Account ID is `077127448006` (dev). Region is `us-east-1`.

### CloudWatch log group (link target)
- `infra/terraform/modules/warehouse_runtime/main.tf` line 28–33 — `aws_cloudwatch_log_group.ecs`
  defines the log group name: `/aws/ecs/${local.name_prefix}-warehouse`

### Phase requirements
- `.planning/workstreams/fix-pipelines/REQUIREMENTS.md` — OBS-05, OBS-06
- `.planning/workstreams/fix-pipelines/ROADMAP.md` Phase 3 — success criteria

### Project constraints
- `.planning/PROJECT.md` DEC-011 — Terraform is for passive infra only; state machine
  changes go in deploy-aws-application.sh. Notification infra (SNS, EventBridge) is passive
  and belongs in Terraform.

</canonical_refs>

<specifics>
## Specific Ideas

- EventBridge input transformer can format the message body without a Lambda. Use
  `aws_cloudwatch_event_target` with an `input_transformer` block (Terraform resource). The
  `inputPathsMap` extracts `$.detail.stateMachineArn`, `$.detail.executionArn`,
  `$.detail.stopDate`. The `inputTemplate` builds the plain-text body string.
- Parsing the pipeline name from `stateMachineArn`: the ARN suffix after the last `:` gives
  the name (e.g., `bootstrap_phased`). Use a string replacement in the `inputTemplate`:
  `<stateMachineArn>` → strip prefix via SNS message body convention.
- EventBridge → SNS requires an SNS topic policy granting `events.amazonaws.com` the
  `sns:Publish` action scoped to the topic ARN.
- Dev environment state machine ARN prefix:
  `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-`
  (Note: upsert_state_machine uses underscores in the name but they map to the name string
  passed — verify with the deploy script output.)

</specifics>

<deferred>
## Deferred Ideas

- Lambda transformer for exact ECS task log stream deep-link (would require `GetExecutionHistory`
  call; too complex for the current phase — log group link is sufficient)
- Per-machine EventBridge rules for granular muting
- Prod account wiring (follow-up after dev verification)
- PagerDuty or Slack integration (beyond email scope)

</deferred>

---

*Phase: 03-failure-notifications*
*Context gathered: 2026-05-16 via discuss-phase*
