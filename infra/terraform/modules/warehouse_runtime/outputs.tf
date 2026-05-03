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
  description = "Empty EDGAR identity secret container ARN."
  value       = local.resolved_edgar_identity_secret_arn
}

output "snowflake_manifest_sns_topic_arn" {
  description = "SNS topic ARN reserved for operator-managed Snowflake export manifest notifications."
  value       = aws_sns_topic.snowflake_manifest_events.arn
}

output "snowflake_export_root_url" {
  description = "S3 URL prefix for Snowflake export packages, including the trailing slash required by the storage integration allow-list."
  value       = local.snowflake_export_root_url
}

output "snowflake_export_prefix" {
  description = "Bucket-relative prefix for Snowflake export packages."
  value       = local.snowflake_export_prefix
}

output "log_group_name" {
  description = "CloudWatch log group for ECS tasks."
  value       = aws_cloudwatch_log_group.ecs.name
}

output "runner_credentials_secret_arn" {
  description = "Secrets Manager ARN for a legacy empty operator credential container. Normal AWS runtime uses sec_platform_runner service roles without access keys."
  value       = aws_secretsmanager_secret.runner_credentials.arn
}
