# Least-privilege IAM identity for the EventBridge rule that triggers
# edgartools-prod-mdm-utility's mdm_check_fence mode on a schedule (Ticket
# 44, change-propagation map: the drift-monitoring follow-up split from
# Ticket 30's own live incident, where a Snowflake-hosted Postgres platform
# behavior silently reopened application/snowflake_write's revoked access
# to the acquisition-ledger/registry tables on every credential rotation).
#
# Mirrors scheduled_daily_incremental.tf's own pattern and its stated
# rationale exactly: per that file's decision, the rule/target itself is
# NOT Terraform-managed here -- a Terraform apply must never be able to
# silently enable a recurring autonomous prod trigger. It's created by
# infra/scripts/deploy-aws-application.sh's off-by-default
# --configure-fence-monitor-schedule control instead, run explicitly as
# sec_platform_deployer. Only the identity a rule assumes to call
# states:StartExecution belongs here, scoped to exactly the one state
# machine this rule targets -- and, unlike daily_incremental's dedicated
# machine, that's the shared mdm_utility machine every other MDM CLI
# wrapper mode also uses. This role's policy is scoped to StartExecution on
# that machine's ARN only; it grants no ability to choose which mode an
# execution runs (that's fixed by the Input JSON the EventBridge target
# itself carries, set by the deploy script, not by this role).
#
# Creating this role is unconditional (no enable flag) because the role
# alone starts nothing -- no EventBridge rule attaches to it from
# Terraform; only the deploy script's separately-gated rule/target creation
# actually wires up the recurring trigger.
locals {
  mdm_utility_state_machine_arn = "arn:aws:states:${var.aws_region}:${var.expected_aws_account_id}:stateMachine:edgartools-prod-mdm-utility"
}

resource "aws_iam_role" "fence_monitor_scheduler" {
  name = "edgartools-prod-fence-monitor-scheduler"

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

  tags = merge(var.tags, { Name = "edgartools-prod-fence-monitor-scheduler" })
}

resource "aws_iam_role_policy" "fence_monitor_scheduler_start_execution" {
  name = "start-mdm-utility-execution"
  role = aws_iam_role.fence_monitor_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "states:StartExecution"
        Resource = local.mdm_utility_state_machine_arn
      }
    ]
  })
}
