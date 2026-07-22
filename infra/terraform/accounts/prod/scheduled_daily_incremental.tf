# Seed-universe wayfinder ticket 02: daily-incremental's existing
# _load_daily_index_for_date -> _seed_silver_tracking_status logic already
# marks any brand-new CIK "active" the moment it files anything (IPOs
# included), and ticket 03's Form 15 demotion (warehouse_orchestrator.py)
# already rides the same pipeline -- but nothing schedules daily-incremental
# to run at all (confirmed via `aws events list-rules`: zero rules target it
# as of 2026-07-22). This is that schedule.
#
# daily-incremental's own scope resolution (_resolve_scope in
# warehouse_orchestrator.py) self-catches-up from the last successful
# checkpoint date when start_date/end_date are omitted, so an empty `{}`
# input is the correct, safe trigger payload -- no date arithmetic needed
# here.
#
# Gated OFF by default (daily_incremental_schedule_enabled = false): building
# this Terraform is not the same as turning the schedule on. Enabling it
# starts a recurring, autonomous production Step Functions execution, so it
# requires the same explicit-go discipline as any other autonomous prod
# trigger in this repo -- flip the variable only after an operator confirms.
#
# The state machine itself (edgartools-prod-daily-incremental) is created by
# infra/scripts/deploy-aws-application.sh, not Terraform (this repo's Step
# Functions are managed imperatively -- see CLAUDE.md), so it's referenced
# here by its well-known ARN rather than a Terraform resource reference.

locals {
  daily_incremental_state_machine_arn = "arn:aws:states:${var.aws_region}:${var.expected_aws_account_id}:stateMachine:edgartools-prod-daily-incremental"
}

resource "aws_iam_role" "daily_incremental_scheduler" {
  count = var.daily_incremental_schedule_enabled ? 1 : 0

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
  count = var.daily_incremental_schedule_enabled ? 1 : 0

  name = "start-daily-incremental-execution"
  role = aws_iam_role.daily_incremental_scheduler[0].id

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

resource "aws_cloudwatch_event_rule" "daily_incremental_schedule" {
  count = var.daily_incremental_schedule_enabled ? 1 : 0

  name        = "edgartools-prod-daily-incremental-schedule"
  description = "Daily trigger for edgartools-prod-daily-incremental (seed-universe IPO/deregistration signals, wayfinder tickets 02/03)"

  # 12:00 UTC = 7am EST / 8am EDT -- safely after the daily-index file's
  # expected ~6am ET availability (sec_calendar.expected_available_at) in
  # both standard and daylight time, with margin.
  schedule_expression = "cron(0 12 * * ? *)"

  tags = merge(var.tags, { Name = "edgartools-prod-daily-incremental-schedule" })
}

resource "aws_cloudwatch_event_target" "daily_incremental_schedule" {
  count = var.daily_incremental_schedule_enabled ? 1 : 0

  rule      = aws_cloudwatch_event_rule.daily_incremental_schedule[0].name
  target_id = "daily-incremental-sfn"
  arn       = local.daily_incremental_state_machine_arn
  role_arn  = aws_iam_role.daily_incremental_scheduler[0].arn
  input     = "{}"
}
