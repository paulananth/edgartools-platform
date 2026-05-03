output "runner_execution_role_arn" {
  description = "Dev sec_platform_runner_execution role ARN for ECS task image pulls, logging, and runtime secret reads."
  value       = module.runtime_access.runner_execution_role_arn
}

output "runner_task_role_arn" {
  description = "Dev sec_platform_runner_task role ARN for warehouse application task permissions."
  value       = module.runtime_access.runner_task_role_arn
}

output "runner_step_functions_role_arn" {
  description = "Dev sec_platform_runner_step_functions role ARN assumed by Step Functions state machines."
  value       = module.runtime_access.runner_step_functions_role_arn
}

output "ecs_task_execution_role_arn" {
  description = "Dev compatibility output for the sec_platform_runner_execution role ARN."
  value       = module.runtime_access.ecs_task_execution_role_arn
}

output "ecs_task_role_arn" {
  description = "Dev compatibility output for the sec_platform_runner_task role ARN."
  value       = module.runtime_access.ecs_task_role_arn
}

output "step_functions_role_arn" {
  description = "Dev compatibility output for the sec_platform_runner_step_functions role ARN."
  value       = module.runtime_access.step_functions_role_arn
}

output "snowflake_storage_role_arn" {
  description = "Dev IAM role ARN that Snowflake assumes for native export reads."
  value       = module.runtime_access.snowflake_storage_role_arn
}

output "snowflake_manifest_sns_topic_arn" {
  description = "Dev SNS topic ARN for Snowflake export run-manifest notifications."
  value       = local.provisioning.snowflake_manifest_sns_topic_arn
}

output "snowflake_export_root_url" {
  description = "Dev S3 URL prefix for Snowflake export packages."
  value       = local.provisioning.snowflake_export_root_url
}

output "snowflake_storage_external_id" {
  description = "Dev external ID required by the Snowflake export reader role."
  value       = module.runtime_access.snowflake_storage_external_id
}

output "snowflake_manifest_subscriber_arn" {
  description = "Dev Snowflake-managed AWS principal ARN used by AWS access, if known."
  value       = local.subscriber_arn
}
