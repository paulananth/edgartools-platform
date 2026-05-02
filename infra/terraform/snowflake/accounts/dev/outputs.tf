output "database_name" {
  description = "Dev Snowflake database name."
  value       = module.baseline.database_name
}

output "schema_names" {
  description = "Dev Snowflake schema names."
  value       = module.baseline.schema_names
}

output "role_names" {
  description = "Dev Snowflake role names."
  value       = module.baseline.role_names
}

output "warehouse_names" {
  description = "Dev Snowflake warehouse names."
  value       = module.baseline.warehouse_names
}

output "dashboard_stage_qualified_name" {
  description = "Dev Streamlit stage qualified name."
  value       = module.dashboard.stage_qualified_name
}

output "dashboard_schema_name" {
  description = "Dev Streamlit dashboard schema name."
  value       = module.dashboard.schema_name
}

output "dashboard_streamlit_qualified_name" {
  description = "Dev Streamlit app qualified name."
  value       = module.dashboard.streamlit_qualified_name
}

output "snowflake_manifest_subscriber_arn" {
  description = "Dev Snowflake-managed AWS principal ARN emitted by the storage integration."
  value       = try(module.native_pull[0].storage_aws_iam_user_arn, null)
}

output "snowflake_storage_external_id" {
  description = "Dev storage integration external ID used for AWS trust."
  value       = try(module.native_pull[0].storage_external_id, local.storage_external_id)
}

output "native_pull_storage_integration_name" {
  description = "Dev Snowflake storage integration name."
  value       = try(module.native_pull[0].storage_integration_name, null)
}

output "native_pull_stage_qualified_name" {
  description = "Dev native-pull stage qualified name."
  value       = try(module.native_pull[0].stage_fully_qualified_name, null)
}

output "native_pull_ready" {
  description = "Whether the dev native-pull object graph is provisioned."
  value       = try(module.native_pull[0].native_pull_ready, false)
}
