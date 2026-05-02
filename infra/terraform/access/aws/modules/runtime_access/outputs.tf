output "ecs_task_execution_role_arn" {
  description = "Warehouse ECS task execution role ARN for operator-managed task definitions."
  value       = aws_iam_role.ecs_task_execution_warehouse.arn
}

output "ecs_task_role_arn" {
  description = "Warehouse ECS task role ARN for operator-managed task definitions."
  value       = aws_iam_role.ecs_task_warehouse.arn
}

output "step_functions_role_arn" {
  description = "Step Functions execution role ARN for operator-managed state machines."
  value       = aws_iam_role.step_functions.arn
}

output "snowflake_storage_role_arn" {
  description = "IAM role ARN that Snowflake assumes for native S3 export reads."
  value       = try(aws_iam_role.snowflake_storage_reader[0].arn, null)
}

output "snowflake_manifest_subscriber_arn" {
  description = "Snowflake-managed AWS principal ARN used by the access policy, if known."
  value       = var.snowflake_manifest_subscriber_arn
}

output "snowflake_storage_external_id" {
  description = "External ID required by the Snowflake export reader IAM role."
  value       = var.snowflake_storage_external_id
}

output "runner_user_name" {
  description = "Out-of-band runner IAM user name."
  value       = aws_iam_user.runner.name
}

output "runner_user_arn" {
  description = "Runner IAM user ARN."
  value       = aws_iam_user.runner.arn
}
