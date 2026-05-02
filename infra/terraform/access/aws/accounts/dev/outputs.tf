output "ecs_task_execution_role_arn" {
  description = "Dev ECS task execution role ARN for operator-managed task definitions."
  value       = module.runtime_access.ecs_task_execution_role_arn
}

output "ecs_task_role_arn" {
  description = "Dev ECS task role ARN for operator-managed task definitions."
  value       = module.runtime_access.ecs_task_role_arn
}

output "step_functions_role_arn" {
  description = "Dev Step Functions execution role ARN for operator-managed state machines."
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

output "runner_user_name" {
  description = "Dev out-of-band runner IAM user name."
  value       = module.runtime_access.runner_user_name
}

output "runner_user_arn" {
  description = "Dev runner IAM user ARN."
  value       = module.runtime_access.runner_user_arn
}
