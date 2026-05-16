---
plan: 03-01
phase: 03-failure-notifications
status: partial
completed: 2026-05-16
commit: 5b0254c
---

# Plan 03-01 Summary: Pipeline Failure Notifications — Terraform Module

## What Was Built

**Task 1 — New Terraform module `infra/terraform/modules/pipeline_notifications/`**
Three files created:
- `variables.tf` — 6 inputs: `environment`, `name_prefix`, `aws_region`, `account_id`, `subscriber_email` (no default — required), `tags`
- `main.tf` — 5 AWS resources:
  - `aws_sns_topic.pipeline_failures` — `{name_prefix}-pipeline-failures`
  - `data.aws_iam_policy_document` + `aws_sns_topic_policy.pipeline_failures` — AllowEventBridgePublish (NO Condition block per AWS restriction) + account-owner `__default_statement_ID`
  - `aws_sns_topic_subscription.pipeline_failures` — `protocol = "email"`, enters PendingConfirmation on apply
  - `aws_cloudwatch_event_rule.pipeline_failures` — single catch-all rule matching `aws.states` FAILED events for ARN prefix `arn:aws:states:{region}:{account_id}:stateMachine:{name_prefix}-`
  - `aws_cloudwatch_event_target.pipeline_failure_sns` — SNS target with `input_transformer` formatting human-readable body (no `role_arn` — uses resource policy, not IAM role)
- `outputs.tf` — `sns_topic_arn`, `event_rule_arn`

**Task 2 — Wired into `infra/terraform/accounts/prod/`**
- `main.tf`: `module "pipeline_notifications"` with `count = var.pipeline_notifications_enabled ? 1 : 0`, `environment = "dev"` (hardcoded literal — NOT `local.environment`), `account_id = "077127448006"` (hardcoded)
- `variables.tf`: `pipeline_notifications_enabled` (bool, default false) + `pipeline_failure_subscriber_email` (string, default null)
- `terraform validate` passes

## Task 3 Status — Deployment Blocked (Backend Not Initialized)

`terraform apply` requires the S3 backend to be initialized. `backend.hcl` is gitignored and was not present locally. The state bucket `edgartools-prod-tfstate` does not exist in the dev AWS account.

**To complete Task 3, run these commands:**

```bash
cd infra/terraform/accounts/prod

# Option A — if you have a backend.hcl configured:
terraform init -backend-config=backend.hcl
terraform apply \
  -var="pipeline_notifications_enabled=true" \
  -var="pipeline_failure_subscriber_email=thepaulananth@gmail.com"

# Option B — use local state (no S3 backend, dev only):
terraform init -backend=false
terraform apply -state=terraform.tfstate \
  -var="pipeline_notifications_enabled=true" \
  -var="pipeline_failure_subscriber_email=thepaulananth@gmail.com"
```

**After `terraform apply` completes:**
1. Check inbox for `thepaulananth@gmail.com` — confirm the "AWS Notification - Subscription Confirmation" email
2. Click "Confirm subscription" in that email
3. Trigger a test failure:
```bash
aws stepfunctions start-execution \
  --region us-east-1 \
  --state-machine-arn "arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-gold-refresh" \
  --name "notification-test-$(date +%s)" \
  --input '{}'
```
4. Confirm email arrives within 2 minutes with all 6 body fields

## Acceptance Criteria Status

| Criterion | Status |
|---|---|
| `pipeline_notifications` module exists with 5 resource types | PASS |
| AllowEventBridgePublish has no Condition block | PASS (verified via HCL structure check) |
| `environment = "dev"` hardcoded in accounts/prod module invocation | PASS |
| `account_id = "077127448006"` hardcoded | PASS |
| `terraform validate` exits 0 | PASS |
| `pipeline_notifications_enabled` variable, default false | PASS |
| `pipeline_failure_subscriber_email` variable, default null | PASS |
| `terraform apply` deploys 6 resources | PENDING — backend not initialized |
| EventBridge rule ENABLED in AWS | PENDING |
| SNS email subscription confirmed | PENDING |
| Live FAILED execution triggers email within 2 min | PENDING |

## Key Design Points

- Email subject will be "AWS Notification Message" (SNS default) — the formatted `[EdgarTools] Pipeline FAILED: <name>` line appears as the **first line of the body** (EventBridge input_transformer cannot set SNS subject)
- "Failed stage name" is descoped (D-06) — requires Lambda + GetExecutionHistory, forbidden by D-01
- CloudWatch link is a static log group URL (no time filter — input_transformer has no arithmetic)
- State machine ARNs use hyphens: `edgartools-dev-bootstrap-phased` (not underscores)
