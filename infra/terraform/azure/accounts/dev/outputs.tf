output "container_registry_login_server" {
  description = "ACR login server."
  value       = module.acr.login_server
}

output "resource_group_name" {
  description = "Azure resource group name."
  value       = module.resource_group.name
}

output "warehouse_bronze_root" {
  description = "Azure WAREHOUSE_BRONZE_ROOT."
  value       = module.storage.warehouse_bronze_root
}

output "warehouse_storage_root" {
  description = "Azure WAREHOUSE_STORAGE_ROOT."
  value       = module.storage.warehouse_storage_root
}

output "serving_export_root" {
  description = "Azure SERVING_EXPORT_ROOT."
  value       = module.storage.serving_export_root
}

output "key_vault_name" {
  description = "Azure Key Vault name for runtime secrets."
  value       = module.key_vault.name
}

output "edgar_identity_secret_uri" {
  description = "Versionless Key Vault secret URI used for EDGAR_IDENTITY."
  value       = "${module.key_vault.vault_uri}secrets/edgar-identity"
}

output "container_app_job_names" {
  description = "Container Apps Job names by workflow."
  value       = module.container_jobs.job_names
}

output "bootstrap_recent_10_container_app_job_name" {
  description = "Manual validation Container Apps Job name."
  value       = module.container_jobs.job_names.bootstrap_recent_10
}

output "databricks_workspace_url" {
  description = "Databricks workspace URL."
  value       = module.databricks.workspace_url
}

output "mdm_sql_server_fqdn" {
  description = "Azure SQL Server FQDN for MDM."
  value       = try(module.mdm[0].sql_server_fqdn, null)
}

output "mdm_sql_database_name" {
  description = "Azure SQL database name for MDM."
  value       = try(module.mdm[0].sql_database_name, null)
}

output "mdm_database_url_secret_id" {
  description = "Key Vault secret ID for MDM_DATABASE_URL."
  value       = try(module.mdm[0].database_url_secret_id, null)
}

output "mdm_neo4j_uri" {
  description = "Neo4j Bolt URI for MDM."
  value       = try(module.mdm[0].neo4j_uri, null)
}

output "mdm_neo4j_secret_id" {
  description = "Key Vault secret ID for Neo4j connection details."
  value       = try(module.mdm[0].neo4j_secret_id, null)
}

output "mdm_api_keys_secret_id" {
  description = "Key Vault secret ID for MDM API keys."
  value       = try(module.mdm[0].api_keys_secret_id, null)
}

output "mdm_api_fqdn" {
  description = "MDM API Container App FQDN."
  value       = try(module.mdm[0].mdm_api_fqdn, null)
}

output "mdm_container_app_job_names" {
  description = "MDM Container Apps Job names by workflow."
  value       = try(module.mdm[0].mdm_job_names, null)
}
