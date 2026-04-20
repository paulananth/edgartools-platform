output "cluster_name" {
  description = "Warehouse ECS cluster name."
  value       = aws_ecs_cluster.warehouse.name
}

output "cluster_arn" {
  description = "Warehouse ECS cluster ARN."
  value       = aws_ecs_cluster.warehouse.arn
}

output "ecr_repository_url" {
  description = "Warehouse ECR repository URL."
  value       = aws_ecr_repository.warehouse.repository_url
}

output "edgar_identity_secret_arn" {
  description = "EDGAR identity secret ARN used by ECS tasks."
  value       = local.resolved_edgar_identity_secret_arn
}

output "snowflake_manifest_sns_topic_arn" {
  description = "SNS topic ARN that receives Snowflake export run-manifest object notifications."
  value       = aws_sns_topic.snowflake_manifest_events.arn
}

output "snowflake_storage_role_arn" {
  description = "IAM role ARN that Snowflake assumes for native S3 export reads."
  value       = try(aws_iam_role.snowflake_storage_reader[0].arn, null)
}

output "snowflake_export_root_url" {
  description = "S3 URL prefix for Snowflake export packages, including the trailing slash required by the storage integration allow-list."
  value       = local.snowflake_export_root_url
}

output "snowflake_export_prefix" {
  description = "Bucket-relative prefix for Snowflake export packages."
  value       = local.snowflake_export_prefix
}

output "snowflake_export_kms_key_arn" {
  description = "KMS key ARN used to encrypt Snowflake export artifacts."
  value       = var.snowflake_export_kms_key_arn
}

output "snowflake_manifest_subscriber_arn" {
  description = "Snowflake-managed AWS principal ARN subscribed to manifest events."
  value       = var.snowflake_manifest_subscriber_arn
}

output "state_machine_arns" {
  description = "State machine ARNs keyed by workflow."
  value       = { for name, workflow in aws_sfn_state_machine.workflow : name => workflow.arn }
}

output "log_group_name" {
  description = "CloudWatch log group for ECS tasks."
  value       = aws_cloudwatch_log_group.ecs.name
}

output "step_functions_log_group_name" {
  description = "CloudWatch log group for Step Functions workflow logs."
  value       = aws_cloudwatch_log_group.step_functions.name
}

output "runner_user_name" {
  description = "IAM user name for the runner account (start/monitor Step Functions only). Create access keys with: aws iam create-access-key --user-name <value>"
  value       = aws_iam_user.runner.name
}

output "runner_user_arn" {
  description = "IAM user ARN for the runner account."
  value       = aws_iam_user.runner.arn
}

output "runner_credentials_secret_arn" {
  description = "Secrets Manager ARN holding the runner access key credentials. The secret value is populated out-of-band after aws iam create-access-key."
  value       = aws_secretsmanager_secret.runner_credentials.arn
}
