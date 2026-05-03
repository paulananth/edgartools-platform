output "bronze_bucket_name" {
  description = "Dev bronze bucket name."
  value       = module.storage.bronze_bucket_name
}

output "bronze_bucket_arn" {
  description = "Dev bronze bucket ARN."
  value       = module.storage.bronze_bucket_arn
}

output "warehouse_bucket_name" {
  description = "Dev warehouse bucket name."
  value       = module.storage.warehouse_bucket_name
}

output "warehouse_bucket_arn" {
  description = "Dev warehouse bucket ARN."
  value       = module.storage.warehouse_bucket_arn
}

output "snowflake_export_bucket_name" {
  description = "Dev Snowflake export bucket name."
  value       = module.storage.snowflake_export_bucket_name
}

output "snowflake_export_bucket_arn" {
  description = "Dev Snowflake export bucket ARN."
  value       = module.storage.snowflake_export_bucket_arn
}

output "ecr_repository_url" {
  description = "Dev ECR repository URL."
  value       = module.runtime.ecr_repository_url
}

output "cluster_name" {
  description = "Dev ECS cluster name."
  value       = module.runtime.cluster_name
}

output "cluster_arn" {
  description = "Dev ECS cluster ARN."
  value       = module.runtime.cluster_arn
}

output "public_subnet_ids" {
  description = "Dev public subnet IDs for operator-managed ECS tasks."
  value       = module.network.public_subnet_ids
}

output "public_ecs_security_group_id" {
  description = "Dev outbound-only security group ID for operator-managed ECS tasks."
  value       = module.network.public_ecs_security_group_id
}

output "log_group_name" {
  description = "Dev CloudWatch log group for ECS tasks."
  value       = module.runtime.log_group_name
}

output "edgar_identity_secret_arn" {
  description = "Dev empty EDGAR identity secret container ARN."
  value       = module.runtime.edgar_identity_secret_arn
}

output "snowflake_manifest_sns_topic_arn" {
  description = "Dev SNS topic ARN reserved for operator-managed Snowflake export run-manifest notifications."
  value       = module.runtime.snowflake_manifest_sns_topic_arn
}

output "snowflake_export_root_url" {
  description = "Dev S3 URL prefix for Snowflake export packages."
  value       = module.runtime.snowflake_export_root_url
}

output "snowflake_export_prefix" {
  description = "Dev bucket-relative prefix for Snowflake export packages."
  value       = module.runtime.snowflake_export_prefix
}

output "snowflake_export_kms_key_arn" {
  description = "Dev KMS key ARN for Snowflake export artifacts."
  value       = module.storage.snowflake_export_kms_key_arn
}

output "runner_credentials_secret_arn" {
  description = "Dev legacy empty operator credential container ARN. Normal AWS runtime uses sec_platform_runner service roles without access keys."
  value       = module.runtime.runner_credentials_secret_arn
}

output "mdm_db_endpoint" {
  description = "Dev MDM PostgreSQL endpoint hostname (only set when var.mdm_enabled = true)."
  value       = try(module.mdm[0].db_endpoint, null)
}

output "mdm_db_master_user_secret_arn" {
  description = "Dev AWS-managed RDS master user secret ARN."
  value       = try(module.mdm[0].db_master_user_secret_arn, null)
}

output "mdm_postgres_dsn_secret_arn" {
  description = "Dev empty Secrets Manager container ARN for an operator-populated MDM PostgreSQL DSN."
  value       = try(module.mdm[0].postgres_dsn_secret_arn, null)
}

output "mdm_neo4j_secret_arn" {
  description = "Dev empty Secrets Manager container ARN for operator-populated Neo4j connection details."
  value       = try(module.mdm[0].neo4j_secret_arn, null)
}

output "mdm_api_keys_secret_arn" {
  description = "Dev empty Secrets Manager container ARN for operator-populated MDM API keys."
  value       = try(module.mdm[0].api_keys_secret_arn, null)
}

output "mdm_db_security_group_id" {
  description = "Dev MDM RDS security group ID."
  value       = try(module.mdm[0].db_security_group_id, null)
}
