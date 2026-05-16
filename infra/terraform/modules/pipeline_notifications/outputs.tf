output "sns_topic_arn" {
  description = "ARN of the pipeline-failures SNS topic."
  value       = aws_sns_topic.pipeline_failures.arn
}

output "event_rule_arn" {
  description = "ARN of the EventBridge rule that catches FAILED Step Functions executions."
  value       = aws_cloudwatch_event_rule.pipeline_failures.arn
}
