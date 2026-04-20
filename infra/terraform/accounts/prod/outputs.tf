output "bronze_bucket_name" {
  description = "Prod bronze bucket name."
  value       = module.storage.bronze_bucket_name
}

output "warehouse_bucket_name" {
  description = "Prod warehouse bucket name."
  value       = module.storage.warehouse_bucket_name
}

output "snowflake_export_bucket_name" {
  description = "Prod Snowflake export bucket name."
  value       = module.storage.snowflake_export_bucket_name
}

output "ecr_repository_url" {
  description = "Prod ECR repository URL."
  value       = module.runtime.ecr_repository_url
}

output "cluster_name" {
  description = "Prod ECS cluster name."
  value       = module.runtime.cluster_name
}

output "edgar_identity_secret_arn" {
  description = "Prod EDGAR identity secret ARN."
  value       = module.runtime.edgar_identity_secret_arn
}

output "state_machine_arns" {
  description = "Prod Step Functions state machines."
  value       = module.runtime.state_machine_arns
}

output "snowflake_manifest_sns_topic_arn" {
  description = "Prod SNS topic ARN for Snowflake export run-manifest notifications."
  value       = module.runtime.snowflake_manifest_sns_topic_arn
}

output "snowflake_storage_role_arn" {
  description = "Prod IAM role ARN that Snowflake assumes for native export reads."
  value       = module.runtime.snowflake_storage_role_arn
}

output "snowflake_export_root_url" {
  description = "Prod S3 URL prefix for Snowflake export packages."
  value       = module.runtime.snowflake_export_root_url
}

output "snowflake_export_prefix" {
  description = "Prod bucket-relative prefix for Snowflake export packages."
  value       = module.runtime.snowflake_export_prefix
}

output "snowflake_export_kms_key_arn" {
  description = "Prod KMS key ARN for Snowflake export artifacts."
  value       = module.runtime.snowflake_export_kms_key_arn
}

output "snowflake_manifest_subscriber_arn" {
  description = "Prod Snowflake-managed AWS principal ARN subscribed to manifest notifications."
  value       = module.runtime.snowflake_manifest_subscriber_arn
}

output "runner_user_name" {
  description = "Prod runner IAM user name. Create access keys with: aws iam create-access-key --user-name <value>"
  value       = module.runtime.runner_user_name
}

output "runner_user_arn" {
  description = "Prod runner IAM user ARN."
  value       = module.runtime.runner_user_arn
}

output "runner_credentials_secret_arn" {
  description = "Prod runner credentials secret ARN. Populate it after creating a runner access key."
  value       = module.runtime.runner_credentials_secret_arn
}
