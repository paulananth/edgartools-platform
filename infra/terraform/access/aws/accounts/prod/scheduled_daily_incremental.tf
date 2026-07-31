# Least-privilege IAM identity for the EventBridge rules that trigger
# edgartools-prod-daily-incremental on a schedule (release-readiness ticket
# 45/49: Daily Identity Refresh Mon-Sat, Identity Backstop Sweep Sunday, both
# 12:00 UTC). Per ticket 45's explicit decision, the rules/targets themselves
# are NOT Terraform-managed here -- a Terraform apply must never be able to
# silently enable a recurring autonomous prod trigger. They're created by
# infra/scripts/deploy-aws-application.sh's off-by-default schedule controls
# instead (this repo's Step Functions are already managed imperatively that
# way -- see CLAUDE.md), run explicitly as sec_platform_deployer.
#
# Only the identity a rule assumes to call states:StartExecution belongs
# here, scoped to exactly that one state machine. Creating this role is
# unconditional (no enable flag) because the role alone starts nothing --
# no EventBridge rule attaches to it from Terraform; only the deploy
# script's separately-gated rule/target creation actually wires up the
# recurring trigger.
#
# The state machine itself isn't a Terraform resource (imperatively
# managed), so it's referenced here by its well-known ARN -- the same
# convention the removed passive-Terraform schedule file
# (infra/terraform/accounts/prod/scheduled_daily_incremental.tf, deleted as
# part of this ticket) used.
locals {
  daily_incremental_state_machine_arn = "arn:aws:states:${var.aws_region}:${var.expected_aws_account_id}:stateMachine:edgartools-prod-daily-incremental"
  identity_refresh_alert_topic_arn    = "arn:aws:sns:${var.aws_region}:${var.expected_aws_account_id}:sec-edgar-pipeline-alerts"
}

resource "aws_iam_role_policy" "identity_refresh_operator_alerts" {
  name = "publish-identity-refresh-operator-alerts"
  role = basename(module.runtime_access.runner_step_functions_role_arn)

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = local.identity_refresh_alert_topic_arn
      }
    ]
  })
}

resource "aws_iam_role" "daily_incremental_scheduler" {
  name = "edgartools-prod-daily-incremental-scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.tags, { Name = "edgartools-prod-daily-incremental-scheduler" })
}

resource "aws_iam_role_policy" "daily_incremental_scheduler_start_execution" {
  name = "start-daily-incremental-execution"
  role = aws_iam_role.daily_incremental_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "states:StartExecution"
        Resource = local.daily_incremental_state_machine_arn
      }
    ]
  })
}
