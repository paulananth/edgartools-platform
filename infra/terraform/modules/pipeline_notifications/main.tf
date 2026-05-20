locals {
  name_prefix = var.name_prefix
  tags = merge(
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = "edgartools"
    },
    var.tags,
  )
}

# ── SNS Topic ─────────────────────────────────────────────────────────────────

resource "aws_sns_topic" "pipeline_failures" {
  name = "${local.name_prefix}-pipeline-failures"
  tags = merge(local.tags, { Name = "${local.name_prefix}-pipeline-failures" })
}

# ── SNS Topic Policy ──────────────────────────────────────────────────────────
#
# IMPORTANT: AWS explicitly prohibits Condition blocks in SNS topic policies
# for EventBridge targets. The AllowEventBridgePublish statement has NO Condition.
# Reference: https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-use-resource-based.html
#
data "aws_iam_policy_document" "pipeline_failures_sns_policy" {
  policy_id = "__default_policy_ID"

  # Allows EventBridge to publish to this topic.
  # NO Condition block — AWS restriction for EventBridge SNS targets.
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

  # Default account-owner statement — preserves SNS management permissions.
  statement {
    sid    = "__default_statement_ID"
    effect = "Allow"
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

# ── SNS Email Subscription ────────────────────────────────────────────────────
#
# terraform apply completes immediately; subscription enters PendingConfirmation.
# Operator must click the confirmation link in the "AWS Notification - Subscription
# Confirmation" email before notifications will be delivered.
#
resource "aws_sns_topic_subscription" "pipeline_failures" {
  topic_arn = aws_sns_topic.pipeline_failures.arn
  protocol  = "email"
  endpoint  = var.subscriber_email
}

# ── EventBridge Rule ──────────────────────────────────────────────────────────
#
# Single catch-all rule matching all edgartools-{env}-* state machines (D-02).
# The prefix filter covers all 5 production state machines:
#   edgartools-dev-load-history, edgartools-dev-silver-mdm-gold,
#   edgartools-dev-gold-refresh, edgartools-dev-mdm-gold,
#   edgartools-dev-ownership-mdm-gold
# It also matches other edgartools-dev-* machines (e.g. daily-incremental,
# targeted-resync) — intentional per D-02 catch-all scope.
#
resource "aws_cloudwatch_event_rule" "pipeline_failures" {
  name        = "${local.name_prefix}-pipeline-failures"
  description = "Catch all Step Functions FAILED executions for ${local.name_prefix} state machines"

  event_pattern = jsonencode({
    source        = ["aws.states"]
    "detail-type" = ["Step Functions Execution Status Change"]
    detail = {
      status = ["FAILED"]
      stateMachineArn = [
        { prefix = "arn:aws:states:${var.aws_region}:${var.account_id}:stateMachine:${local.name_prefix}-" }
      ]
    }
  })

  tags = merge(local.tags, { Name = "${local.name_prefix}-pipeline-failures" })
}

# ── EventBridge Target → SNS ──────────────────────────────────────────────────
#
# input_transformer formats the email body. SNS Subject is NOT settable from
# EventBridge — it defaults to "AWS Notification Message". The formatted subject
# line "[EdgarTools] Pipeline FAILED: <execution_name>" is placed as the FIRST
# LINE of the message body (D-04 intent, adapted to platform constraint).
#
# stopDate is epoch milliseconds (e.g. 1551225151881). No arithmetic is possible
# in an input transformer, so the raw value is included as a labeled timestamp
# field. The static CloudWatch log group URL (D-07) does not include a time
# filter — operator uses the stopDate value to set the filter manually.
#
# "failed stage name" is NOT included: it requires GetExecutionHistory + Lambda,
# which is forbidden by D-01. Descoped per user decision D-06.
#
# Do NOT add role_arn to this target. SNS targets use the resource-based topic
# policy above; adding a role_arn causes delivery failures.
#
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
      "Pipeline:          <state_machine_arn>"
      "Execution:         <execution_arn>"
      "Failed at (epoch): <stop_date>"
      "Step Functions:    https://console.aws.amazon.com/states/home?region=us-east-1#/executions/details/<execution_arn>"
      "CloudWatch Logs:   https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Faws$252Fecs$252F${local.name_prefix}-warehouse"
    EOT
  }
}
