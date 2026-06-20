# Phase 03: Failure Notifications — Research

**Researched:** 2026-05-16
**Domain:** AWS EventBridge, SNS, Terraform (AWS provider 6.39.0)
**Confidence:** HIGH (all findings verified against official AWS docs or live AWS CLI output)

---

## Summary

- **OBS-06 CONFLICT (planner action required):** The Step Functions "Execution Status Change" event schema contains no failed-stage field. Getting the failing stage name requires `GetExecutionHistory` — which requires Lambda. Lambda is forbidden by CONTEXT.md D-01. OBS-06 requires "failed stage name" in the body. The plan must either explicitly descope that field (accepting log-group link as sufficient, consistent with how D-01 already defers exact log-stream) or escalate to discuss-phase. Do not silently produce a plan that cannot meet OBS-06.

- **State machine names use HYPHENS, not underscores** (CONTEXT.md canonical_refs section is wrong). Verified by reading `deploy-aws-application.sh:1534` (`name="${NAME_PREFIX}-${workflow//_/-}"`) and confirmed with `aws stepfunctions list-state-machines`. The EventBridge prefix filter must be `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-`.

- **stopDate arithmetic is impossible in EventBridge input transformer.** CONTEXT.md D-04 calls for `startTime = stopDate − 30 min`. Input transformers can only substitute values verbatim — no arithmetic or string functions. `stopDate` in the event is an integer (epoch milliseconds). The plan must choose a URL strategy that does not depend on computing offsets.

- **SNS topic policy for EventBridge must NOT include a Condition block.** Official AWS docs explicitly state: "You can't use Condition blocks in Amazon SNS topic policies for EventBridge." The standard pattern is a plain `sns:Publish` with `Principal: events.amazonaws.com` and no condition.

- **Deployment target is `accounts/dev/`, not `accounts/prod/`.** CONTEXT.md D-03 says "called from `accounts/prod/main.tf` (dev deployment target)" but the repo has a real `accounts/dev/main.tf` with `environment = "dev"`. The module should be wired into `accounts/dev/main.tf`. Planner should confirm this with the user.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** No Lambda. The notification body includes a link to the CloudWatch log group (`/aws/ecs/edgartools-{env}-warehouse`) with a time filter centered on the failure timestamp. Operator finds the failing task log stream within ~30 seconds by scanning the group. Getting the exact log stream requires querying `GetExecutionHistory` — deferred as complexity not worth the benefit for a dev-environment alert.
- **D-02:** Single catch-all `aws_cloudwatch_event_rule` targeting all 5 state machines. Event pattern: `source: ["aws.states"]`, `detail-type: ["Step Functions Execution Status Change"]`, `detail.status: ["FAILED"]`, with `detail.stateMachineArn` prefix-matched on `arn:aws:states:{region}:{account_id}:stateMachine:edgartools-{env}`.
- **D-03:** New reusable Terraform module at `infra/terraform/modules/pipeline_notifications/`. Module inputs: `environment`, `name_prefix`, `aws_region`, `account_id`, `subscriber_email`. Called from `infra/terraform/accounts/prod/main.tf` (dev deployment target). Follow the existing `warehouse_runtime` module pattern.
- **D-04:** Human-readable plain-text email. Subject: `[EdgarTools] Pipeline FAILED: {pipeline_name}`. Body contains: Pipeline name, Execution ARN, Failed at (stopDate), Step Functions console link, CloudWatch log group link with startTime=(stopDate minus 30 min) and endTime=(stopDate plus 5 min).
- **D-05:** New dedicated SNS topic `edgartools-{env}-pipeline-failures`.

### Claude's Discretion

None specified in CONTEXT.md.

### Deferred Ideas (OUT OF SCOPE)

- Lambda transformer for exact ECS task log stream deep-link
- Per-machine EventBridge rules for granular muting
- Prod account wiring (follow-up after dev verification)
- PagerDuty or Slack integration
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OBS-05 | When any pipeline execution reaches FAILED state, an SNS email notification is sent to a configured subscriber | EventBridge rule on `aws.states` + SNS topic + email subscription — fully achievable without Lambda |
| OBS-06 | SNS notification body identifies: pipeline name, execution ARN, failed stage name, and a CloudWatch Logs deep-link for the failing ECS task | **CONFLICT:** failed-stage name is not in the EventBridge event schema; requires `GetExecutionHistory` + Lambda (forbidden by D-01). Pipeline name, execution ARN, and log group link are achievable. Planner must resolve. |
</phase_requirements>

---

## Requirement Conflicts

### OBS-06 vs D-01: Failed Stage Name Requires Lambda

**What OBS-06 requires:** The notification body must include the "failed stage name" (the name of the Step Functions state that failed, e.g., `BatchBootstrap` or `GoldRefresh`).

**What the EventBridge event provides:** The Step Functions "Execution Status Change" event schema [VERIFIED: docs.aws.amazon.com/step-functions/latest/dg/eventbridge-integration.html] contains only these `detail` fields:
- `executionArn` (string)
- `stateMachineArn` (string)
- `name` (string — execution name, not stage name)
- `status` (string)
- `startDate` (integer epoch ms)
- `stopDate` (integer epoch ms)
- `input`, `inputDetails`, `output`, `outputDetails`

There is **no field for the failed stage name.** Getting it requires calling `GetExecutionHistory` on the execution ARN and finding the last failed state — which is only possible from Lambda.

**D-01 forbids Lambda.**

**Recommended resolution (planner must choose one):**
- **Option A (recommended):** Descope "failed stage name" from OBS-06 in the plan. Document that the log group link (which D-01 already accepts as sufficient for operator use) is the substitute. Update the ROADMAP.md Phase 3 success criterion 2 accordingly. This keeps the no-Lambda constraint intact.
- **Option B:** Escalate to discuss-phase to reopen D-01 specifically for this one use case.

---

## 1. EventBridge Input Transformer (Terraform HCL)

[VERIFIED: github.com/hashicorp/terraform-provider-aws — Context7 docs for aws_cloudwatch_event_target]

The `input_transformer` block uses:
- `input_paths` (Terraform map) — equivalent to AWS API `InputPathsMap`. Keys are variable names; values are JSONPath expressions into the event.
- `input_template` — string template where `<variable_name>` tokens are substituted.

**JSONPath for Step Functions Execution Status Change event fields:**

| Variable name | JSONPath | Field description |
|---|---|---|
| `execution_arn` | `$.detail.executionArn` | Full execution ARN |
| `state_machine_arn` | `$.detail.stateMachineArn` | Full state machine ARN |
| `execution_name` | `$.detail.name` | Execution name (human-friendly, e.g. `bootstrap-phased-1778839299`) |
| `stop_date` | `$.detail.stopDate` | Failure timestamp — **INTEGER (epoch ms), not ISO string** |
| `status` | `$.detail.status` | Will be "FAILED" |

**CRITICAL:** `stopDate` is an integer (epoch milliseconds). [VERIFIED: official event schema example in docs.aws.amazon.com/step-functions/latest/dg/eventbridge-integration.html shows `"stopDate": 1551225151881`]. The input transformer cannot convert this to ISO or compute arithmetic offsets from it. See Section 6 for implications.

**Terraform HCL — complete aws_cloudwatch_event_target with input_transformer for SNS:**

```hcl
resource "aws_cloudwatch_event_target" "pipeline_failure_sns" {
  rule      = aws_cloudwatch_event_rule.pipeline_failures.name
  target_id = "pipeline-failure-sns"
  arn       = aws_sns_topic.pipeline_failures.arn

  input_transformer {
    input_paths = {
      execution_arn     = "$.detail.executionArn"
      state_machine_arn = "$.detail.stateMachineArn"
      execution_name    = "$.detail.name"
      stop_date         = "$.detail.stopDate"
    }
    input_template = <<-EOT
      "[EdgarTools] Pipeline FAILED: <execution_name>"
      "Pipeline: <state_machine_arn>"
      "Execution: <execution_arn>"
      "Failed at (epoch ms): <stop_date>"
      "Step Functions console: https://console.aws.amazon.com/states/home?region=us-east-1#/executions/details/<execution_arn>"
      "CloudWatch logs: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Faws$252Fecs$252Fedgartools-dev-warehouse"
    EOT
  }
}
```

**Notes on `input_template` for multi-line plain-text SNS email:**
- For non-JSON plain-text output (SNS email body), each line is wrapped in double quotes on its own line. [VERIFIED: docs.aws.amazon.com/eventbridge/latest/userguide/eb-transform-target-input.html — "For (non-JSON) text output as multi-line strings, wrap each separate line in your input template in double quotes."]
- The final SNS message will be a quoted string per line. **UNVERIFIED:** AWS docs show the multi-line quoted format but do not show the rendered email output. The email body MAY contain surrounding literal quote characters per line (e.g., the body starts with `"[EdgarTools] Pipeline FAILED: ..."`). The planner should test in dev after `terraform apply` and adjust the `input_template` if quote characters appear unwanted.
- Variables that are strings (like `execution_arn`) are auto-quoted by EventBridge; do not add extra quotes around them inside the template or they will be double-quoted.
- The `stop_date` variable will render as an integer (e.g. `1551225151881`) with no formatting.

**SNS message format requirement:** When EventBridge sends to an SNS topic, the `Message` field in the SNS publish call receives the output of the input transformer. For email subscribers, SNS delivers the `Message` field as the email body.

---

## 2. SNS Topic Policy for EventBridge

[VERIFIED: docs.aws.amazon.com/eventbridge/latest/userguide/eb-use-resource-based.html]

**CRITICAL FINDING:** The official AWS documentation explicitly states: **"You can't use Condition blocks in Amazon SNS topic policies for EventBridge."** The required statement is a plain `sns:Publish` with no condition.

Community Terraform examples sometimes show an `ArnLike` condition on `aws:SourceArn`, but this contradicts the official guidance. Use the official form.

```hcl
resource "aws_sns_topic" "pipeline_failures" {
  name = "${var.name_prefix}-pipeline-failures"
  tags = merge(local.tags, { Name = "${var.name_prefix}-pipeline-failures" })
}

data "aws_iam_policy_document" "pipeline_failures_sns_policy" {
  policy_id = "__default_policy_ID"

  # Required statement: allows EventBridge to publish to this topic.
  # NOTE: AWS docs explicitly state Condition blocks are NOT supported
  # for EventBridge in SNS topic policies. Do not add ArnLike/ArnEquals.
  statement {
    sid     = "AllowEventBridgePublish"
    effect  = "Allow"
    actions = ["SNS:Publish"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    resources = [aws_sns_topic.pipeline_failures.arn]
  }

  # Default account-owner statement (preserves SNS management permissions).
  statement {
    sid     = "__default_statement_ID"
    effect  = "Allow"
    actions = [
      "SNS:GetTopicAttributes",
      "SNS:SetTopicAttributes",
      "SNS:AddPermission",
      "SNS:RemovePermission",
      "SNS:DeleteTopic",
      "SNS:Subscribe",
      "SNS:ListSubscriptionsByTopic",
      "SNS:Publish",
    ]
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceOwner"
      values   = [var.account_id]
    }
    resources = [aws_sns_topic.pipeline_failures.arn]
  }
}

resource "aws_sns_topic_policy" "pipeline_failures" {
  arn    = aws_sns_topic.pipeline_failures.arn
  policy = data.aws_iam_policy_document.pipeline_failures_sns_policy.json
}
```

**No IAM execution role needed on the target:** For SNS targets, EventBridge uses resource-based policies (the topic policy above). Do not specify `role_arn` on `aws_cloudwatch_event_target` for SNS — setting a role ARN on SNS targets can cause delivery failures. [VERIFIED: docs.aws.amazon.com/eventbridge/latest/userguide/eb-use-resource-based.html — "For targets that use resource-based policies (Lambda, Amazon SNS, Amazon SQS, and Amazon CloudWatch Logs), do not specify a RoleArn in the target configuration."]

---

## 3. EventBridge Rule Event Pattern

[VERIFIED: docs.aws.amazon.com/step-functions/latest/dg/eventbridge-integration.html + docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns-content-based-filtering.html]

The prefix match syntax is `{ "prefix": "..." }` applied to the value array inside `detail.stateMachineArn`. [VERIFIED: official EventBridge content-based filtering docs — "Begins with" row uses `{"prefix": "..."}` syntax.]

```hcl
resource "aws_cloudwatch_event_rule" "pipeline_failures" {
  name        = "${var.name_prefix}-pipeline-failures"
  description = "Catch all Step Functions FAILED executions for edgartools-${var.environment} state machines"

  event_pattern = jsonencode({
    source      = ["aws.states"]
    "detail-type" = ["Step Functions Execution Status Change"]
    detail = {
      status = ["FAILED"]
      stateMachineArn = [
        { prefix = "arn:aws:states:${var.aws_region}:${var.account_id}:stateMachine:edgartools-${var.environment}-" }
      ]
    }
  })

  tags = merge(local.tags, { Name = "${var.name_prefix}-pipeline-failures" })
}
```

**Note on prefix value:** The prefix ends with a hyphen (`edgartools-dev-`), not a colon or underscore. All 5 matching state machine ARNs start with this prefix:
- `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-bootstrap-phased`
- `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-silver-mdm-gold`
- `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-gold-refresh`
- `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-mdm-gold`
- `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-ownership-mdm-gold`

This prefix also matches other `edgartools-dev-*` state machines (e.g. `daily_incremental`, `targeted_resync`). If notifications for those are unwanted, the planner can switch to an explicit list instead of a prefix. For now the catch-all is consistent with D-02.

---

## 4. State Machine ARN Format

[VERIFIED: infra/scripts/deploy-aws-application.sh line 1534 + `aws stepfunctions list-state-machines` live output]

**CORRECTION TO CONTEXT.md:** The canonical_refs section of CONTEXT.md states "Names use underscores: `bootstrap_phased`, `silver_mdm_gold`, ..." This is **wrong**. The deploy script converts underscores to hyphens:

```bash
# deploy-aws-application.sh line 1534
name="${NAME_PREFIX}-${workflow//_/-}"
# ${workflow//_/-} replaces ALL underscores in workflow name with hyphens
```

`NAME_PREFIX` defaults to `edgartools-${ENVIRONMENT}` (line 231).

**Actual AWS state machine names (live output from `aws stepfunctions list-state-machines`):**

| Workflow variable | Actual AWS name | Actual ARN |
|---|---|---|
| `bootstrap_phased` | `edgartools-dev-bootstrap-phased` | `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-bootstrap-phased` |
| `silver_mdm_gold` | `edgartools-dev-silver-mdm-gold` | `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-silver-mdm-gold` |
| `gold_refresh` | `edgartools-dev-gold-refresh` | `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-gold-refresh` |
| `mdm_gold` | `edgartools-dev-mdm-gold` | `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-mdm-gold` |
| `ownership_mdm_gold` | `edgartools-dev-ownership-mdm-gold` | `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-ownership-mdm-gold` |

**EventBridge prefix filter value (Terraform variable substitution):**
```
arn:aws:states:${var.aws_region}:${var.account_id}:stateMachine:edgartools-${var.environment}-
```

For dev: `arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-`

---

## 5. Existing Terraform Patterns

[VERIFIED: reading infra/terraform/modules/warehouse_runtime/main.tf and infra/terraform/accounts/dev/main.tf and infra/terraform/accounts/prod/main.tf]

### locals pattern (from warehouse_runtime module)

```hcl
locals {
  name_prefix = "edgartools-${var.environment}"
  tags = merge(
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = "edgartools"
    },
    var.tags,
  )
}
```

The `pipeline_notifications` module must follow this pattern exactly.

### Module invocation pattern (from accounts/dev/main.tf)

```hcl
module "pipeline_notifications" {
  source = "../../modules/pipeline_notifications"

  environment      = local.environment
  name_prefix      = "edgartools-${local.environment}"
  aws_region       = var.aws_region
  account_id       = "<account_id>"        # can be a local or data source
  subscriber_email = var.subscriber_email
  tags             = var.tags
}
```

Source path convention: `"../../modules/<module_name>"` from an account root.

### Variable declaration pattern (from accounts/dev/variables.tf)

```hcl
variable "subscriber_email" {
  description = "Email address to receive pipeline failure notifications."
  type        = string
  # No default — operator must supply explicitly (per D-03)
}
```

### Existing SNS topic in warehouse_runtime (reference, not to reuse)

```hcl
resource "aws_sns_topic" "snowflake_manifest_events" {
  name = "${local.name_prefix}-snowflake-manifest-events"
  tags = merge(local.tags, { Name = "${local.name_prefix}-snowflake-manifest-events" })
}
```

The new topic follows the same name/tag structure but is in the `pipeline_notifications` module with name `${local.name_prefix}-pipeline-failures`.

### Target deployment account

**AMBIGUITY (planner must confirm):** CONTEXT.md D-03 says "Called from `infra/terraform/accounts/prod/main.tf` (dev deployment target)" but the dev environment lives at `infra/terraform/accounts/dev/main.tf` (environment = "dev"). The module should most naturally be wired into `accounts/dev/main.tf`. The CONTEXT.md note about "prod" is likely a naming artifact — the `prod/` directory is the production account root, not a dev surrogate. **Confirm with user which account root to wire.**

---

## 6. CloudWatch Console URL Format

[VERIFIED: cross-referenced GitHub aws-sdk-js issue #3818 + community sources. Confirmed $252F encoding is the standard CWL console URL scheme for log group names in the fragment.]

### Standard log group URL (no time filter)

The CloudWatch Logs console uses a custom percent-encoding in the URL fragment where `%` is replaced with `$`. So `/` (normally `%2F`) becomes `$2F`, and the double-encoded form `%252F` (which would be `$252F`) is what the console uses for log group name segments.

```
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Faws$252Fecs$252Fedgartools-dev-warehouse
```

This opens `/aws/ecs/edgartools-dev-warehouse` in the CWL console.

### Time-filter URL (with startTime / endTime)

The log group view supports query parameters appended to the fragment with the same custom encoding (`?` = `$3F`, `&` = `$26`, `=` = `$3D`):

```
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Faws$252Fecs$252Fedgartools-dev-warehouse$3FstartTime$3D<START_EPOCH_MS>$26endTime$3D<END_EPOCH_MS>
```

Where `<START_EPOCH_MS>` and `<END_EPOCH_MS>` are integer epoch milliseconds.

### Problem: stopDate arithmetic in input transformer

**CONTEXT.md D-04 requires** `startTime = stopDate − 30 min` and `endTime = stopDate + 5 min`. This is not achievable with EventBridge input transformer alone. The transformer can only substitute the raw value of `stopDate` (an integer epoch ms) — it cannot perform arithmetic. [VERIFIED: docs.aws.amazon.com/eventbridge/latest/userguide/eb-transform-target-input.html — no arithmetic functions described; only value substitution.]

**Options for the planner (choose one):**

| Option | URL | Tradeoff |
|---|---|---|
| **A — No time filter (simplest)** | `.../$252Faws$252Fecs$252Fedgartools-dev-warehouse` | Operator scans the group manually; consistent with D-01's "~30 seconds" acceptance |
| **B — Use stopDate as endTime, fixed window backwards** | `...$3FstartTime$3D<hardcoded_or_omit>$26endTime$3D<stop_date>` | Can embed `stop_date` as endTime; omit startTime to let CWL default to 1 hour before |
| **C — Embed stopDate as label only** | Include stopDate in email body as a readable timestamp; provide static log group URL | Operator uses the timestamp to manually adjust the CWL time filter |

**Recommendation:** Option A (no time filter) or Option C (stopDate as label, static URL). Both are consistent with D-01 which accepts log-group scanning rather than exact log-stream deep-link.

---

## 7. Step Functions Console Link

[ASSUMED: URL format not officially documented; derived from standard AWS console URL pattern and community usage]

The direct link to a specific Step Functions execution uses the execution ARN in the fragment hash:

```
https://console.aws.amazon.com/states/home?region=us-east-1#/executions/details/<executionArn>
```

Example with a real execution ARN:
```
https://console.aws.amazon.com/states/home?region=us-east-1#/executions/details/arn:aws:states:us-east-1:077127448006:execution:edgartools-dev-gold-refresh:gold-1778839299
```

The execution ARN is embedded verbatim (not URL-encoded) in the hash fragment. This pattern works in the current AWS console.

**In the input_template**, reference it as:
```
"Step Functions console: https://console.aws.amazon.com/states/home?region=us-east-1#/executions/details/<execution_arn>"
```

where `execution_arn` is mapped to `$.detail.executionArn`.

**Confidence:** MEDIUM — the URL format is consistent with the AWS console behavior and community usage but is not formally documented by AWS. If the console URL format changes, the link breaks (non-critical — the ARN itself is in the email body).

---

## 8. SNS Email Subscription Behavior

[VERIFIED: github.com/hashicorp/terraform-provider-aws sns_topic_subscription docs + HashiCorp Discuss]

`terraform apply` **completes immediately** when `protocol = "email"` is used. The subscription is created in AWS but enters **PendingConfirmation** state. No apply blocking occurs.

**What the operator must do after `terraform apply`:**
1. Check the inbox for the email address specified in `subscriber_email`.
2. AWS sends a "AWS Notification - Subscription Confirmation" email from `no-reply@sns.amazonaws.com`.
3. Click the "Confirm subscription" link in that email.
4. Only after confirmation will SNS deliver failure notifications to that address.

**Verification implication:** Phase verification ("trigger a FAILED execution, confirm email arrives") must happen *after* the operator has clicked the confirmation link. The plan must include a step reminding the operator to confirm the subscription before running the live failure test.

**Additional constraint:** Until confirmed, Terraform cannot delete the subscription resource (`aws_sns_topic_subscription`). If `terraform destroy` is run before confirmation, it will fail. The subscription must be confirmed (or manually deleted via the AWS console) first.

**Terraform attribute:** The `pending_confirmation` attribute on `aws_sns_topic_subscription` returns `true` until the operator confirms. This can be checked post-apply with `terraform state show`.

---

## 9. Terraform Version Constraints

[VERIFIED: infra/terraform/accounts/dev/versions.tf and infra/terraform/accounts/prod/versions.tf]

Both account roots specify:
```hcl
terraform {
  required_version = "~> 1.14.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.39.0"
    }
  }
}
```

**Resource availability for this phase:**

| Resource | Status in AWS provider 6.39.0 |
|---|---|
| `aws_cloudwatch_event_rule` | Available and stable [ASSUMED: resource predates provider 6.x by years; `aws_cloudwatch_event_rule` = EventBridge rule, available since AWS provider 2.x] |
| `aws_cloudwatch_event_target` with `input_transformer` | Available and stable [ASSUMED: same; input_transformer block verified in current Context7 docs] |
| `aws_sns_topic` | Available and stable |
| `aws_sns_topic_policy` | Available and stable |
| `aws_sns_topic_subscription` | Available and stable |

**Note on newer alternatives:** `aws_scheduler_*` resources (EventBridge Scheduler) and `aws_pipes_*` (EventBridge Pipes) serve different use cases. They are NOT replacements for `aws_cloudwatch_event_rule` + `aws_cloudwatch_event_target`. The correct resources for catching Step Functions state change events and routing to SNS are `aws_cloudwatch_event_rule` + `aws_cloudwatch_event_target`.

---

## Risks / Gotchas

### RISK-01: OBS-06 "Failed Stage Name" Cannot Be Satisfied Without Lambda

**BLOCKER.** See "Requirement Conflicts" section above. The planner must explicitly resolve this before writing the plan. Recommended: descope "failed stage name" from OBS-06; the log group link satisfies the intent of D-01.

### RISK-02: State Machine Names — Hyphens Not Underscores

The EventBridge prefix filter must use `edgartools-dev-` (hyphens throughout). Using `edgartools_dev_` or any underscore form will silently match zero state machines and notifications will never fire. [VERIFIED by reading deploy script + live AWS output.]

### RISK-03: SNS Condition Block Prohibition

Adding a `Condition` block (e.g., `ArnLike` on `aws:SourceArn`) to the SNS topic policy will cause EventBridge delivery to fail silently. Official docs are explicit: conditions are not supported for EventBridge SNS targets. Use the no-condition form.

### RISK-04: D-04 stopDate Arithmetic Is Impossible in Input Transformer

The input transformer cannot compute `stopDate − 30 minutes`. The plan must use one of the three workaround options in Section 6. Do not plan to implement the exact D-04 time-filter URL without acknowledging this constraint.

### RISK-05: Email Subscription Confirmation Before Verification Test

The phase success criterion requires "trigger a FAILED execution, confirm email arrives." This test will produce no email if the subscription is still PendingConfirmation. The plan must include "confirm subscription" as a step before the verification test.

### RISK-06: Deployment Target Ambiguity (accounts/dev vs accounts/prod)

CONTEXT.md D-03 says wire into `accounts/prod/main.tf` but the dev environment has its own `accounts/dev/main.tf`. Wiring into `accounts/prod` while using `environment = "dev"` variables is unusual and likely a CONTEXT.md authoring error. Planner should confirm with user.

### RISK-07: Catch-All Prefix Matches More Than 5 State Machines

The prefix `edgartools-dev-` matches all edgartools state machines in the account (~22 exist: `daily-incremental`, `targeted-resync`, `full-reconcile`, etc.). D-02 specifies a catch-all, but if noise from other machines is undesirable in future, the plan should note this as a known scope: the catch-all is intentional per D-02 and covers all current and future edgartools state machines.

### RISK-08: stopDate Is Epoch Milliseconds, Not ISO String

The `$.detail.stopDate` field is an integer like `1551225151881` (epoch ms). It renders unformatted in the email body. Operators may find this less readable than an ISO timestamp. The plan can document this; fixing it requires Lambda.

---

## Verified Architecture

```
Step Functions (5 state machines)
  |-- FAILED status change event
  v
EventBridge default event bus
  |-- aws_cloudwatch_event_rule (prefix match on stateMachineArn, status=FAILED)
  v
aws_cloudwatch_event_target (input_transformer: extract executionArn, stateMachineArn, name, stopDate)
  v
aws_sns_topic: edgartools-dev-pipeline-failures
  |-- aws_sns_topic_policy: allows events.amazonaws.com to Publish (no Condition block)
  v
aws_sns_topic_subscription (protocol=email, endpoint=var.subscriber_email)
  v
Operator inbox
```

---

## Module Interface (pipeline_notifications)

**Inputs:**

```hcl
variable "environment"      { type = string }
variable "name_prefix"      { type = string }   # "edgartools-dev"
variable "aws_region"       { type = string }   # "us-east-1"
variable "account_id"       { type = string }   # "077127448006"
variable "subscriber_email" { type = string }   # no default
variable "tags"             { type = map(string); default = {} }
```

**Resources to create:**
1. `aws_sns_topic.pipeline_failures`
2. `aws_sns_topic_policy.pipeline_failures` (with `aws_iam_policy_document`)
3. `aws_sns_topic_subscription.pipeline_failures` (email)
4. `aws_cloudwatch_event_rule.pipeline_failures`
5. `aws_cloudwatch_event_target.pipeline_failure_sns`

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Step Functions console URL format: `#/executions/details/<executionArn>` works in current AWS console | Section 7 | Link in email is broken; low impact — ARN is also in the body |
| A2 | `aws_cloudwatch_event_rule` and `aws_cloudwatch_event_target` are available in AWS provider 6.39.0 | Section 9 | Terraform plan fails; low risk — these resources predate provider 6.x |

---

## Sources

### Primary (HIGH confidence)
- [docs.aws.amazon.com/step-functions/latest/dg/eventbridge-integration.html](https://docs.aws.amazon.com/step-functions/latest/dg/eventbridge-integration.html) — Step Functions EventBridge event schema, FAILED event example, field types
- [docs.aws.amazon.com/eventbridge/latest/userguide/eb-use-resource-based.html](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-use-resource-based.html) — SNS topic policy for EventBridge, explicit "no Condition blocks" statement
- [docs.aws.amazon.com/eventbridge/latest/userguide/eb-transform-target-input.html](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-transform-target-input.html) — Input transformer syntax, multi-line string format, limitations
- [docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns-content-based-filtering.html](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns-content-based-filtering.html) — Prefix match syntax `{"prefix": "..."}`
- `infra/scripts/deploy-aws-application.sh` line 1534 — state machine name construction (underscore→hyphen)
- `aws stepfunctions list-state-machines` live output — confirmed actual AWS names
- Context7 `/hashicorp/terraform-provider-aws` — `aws_cloudwatch_event_target` input_transformer HCL syntax

### Secondary (MEDIUM confidence)
- [github.com/hashicorp/terraform-provider-aws docs](https://github.com/hashicorp/terraform-provider-aws/blob/main/website/docs/r/sns_topic_subscription.html.markdown) — email subscription pending_confirmation behavior
- Community sources on CWL console URL `$252F` encoding

### Tertiary (LOW / ASSUMED)
- Step Functions console URL `#/executions/details/<arn>` format (not officially documented)

---

## Metadata

**Confidence breakdown:**
- State machine names and ARNs: HIGH — verified from deploy script + live AWS CLI
- EventBridge event schema: HIGH — official AWS docs
- SNS policy (no Condition): HIGH — official AWS docs explicit statement
- Input transformer HCL: HIGH — Context7 + official AWS docs
- CloudWatch URL encoding: MEDIUM — community-verified, not officially documented
- Step Functions console URL: LOW — not officially documented

**Research date:** 2026-05-16
**Valid until:** 2026-06-16 (stable AWS services; URL formats may change)
