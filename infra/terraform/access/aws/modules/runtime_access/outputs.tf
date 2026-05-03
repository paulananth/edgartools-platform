output "runner_execution_role_arn" {
  description = "sec_platform_runner_execution role ARN for ECS task image pulls, logging, and runtime secret reads."
  value       = aws_iam_role.ecs_task_execution_warehouse.arn
}

output "runner_task_role_arn" {
  description = "sec_platform_runner_task role ARN for warehouse application task permissions."
  value       = aws_iam_role.ecs_task_warehouse.arn
}

output "runner_step_functions_role_arn" {
  description = "sec_platform_runner_step_functions role ARN assumed by Step Functions state machines."
  value       = aws_iam_role.step_functions.arn
}

output "ecs_task_execution_role_arn" {
  description = "Compatibility output for the sec_platform_runner_execution ECS task execution role ARN."
  value       = aws_iam_role.ecs_task_execution_warehouse.arn
}

output "ecs_task_role_arn" {
  description = "Compatibility output for the sec_platform_runner_task ECS task role ARN."
  value       = aws_iam_role.ecs_task_warehouse.arn
}

output "step_functions_role_arn" {
  description = "Compatibility output for the sec_platform_runner_step_functions role ARN."
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
