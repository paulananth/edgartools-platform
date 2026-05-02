output "container_registry_login_server" {
  description = "ACR login server."
  value       = module.acr.login_server
}

output "container_registry_id" {
  description = "ACR resource ID."
  value       = module.acr.id
}

output "resource_group_name" {
  description = "Azure resource group name."
  value       = module.resource_group.name
}

output "resource_group_location" {
  description = "Azure resource group location."
  value       = module.resource_group.location
}

output "storage_account_id" {
  description = "ADLS Gen2 storage account resource ID."
  value       = module.storage.id
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

output "key_vault_id" {
  description = "Azure Key Vault resource ID."
  value       = module.key_vault.id
}

output "edgar_identity_secret_uri" {
  description = "Versionless Key Vault secret URI for the out-of-band EDGAR_IDENTITY value."
  value       = "${module.key_vault.vault_uri}secrets/edgar-identity"
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID."
  value       = module.container_jobs.log_analytics_workspace_id
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

output "mdm_runtime_secret_uris" {
  description = "Versionless Key Vault URIs expected by out-of-band MDM runtime setup. Terraform does not create these secret values."
  value = var.enable_mdm ? {
    database_url   = "${module.key_vault.vault_uri}secrets/mdm-database-url"
    neo4j          = "${module.key_vault.vault_uri}secrets/mdm-neo4j"
    neo4j_uri      = "${module.key_vault.vault_uri}secrets/mdm-neo4j-uri"
    neo4j_user     = "${module.key_vault.vault_uri}secrets/mdm-neo4j-user"
    neo4j_password = "${module.key_vault.vault_uri}secrets/mdm-neo4j-password"
    api_keys       = "${module.key_vault.vault_uri}secrets/mdm-api-keys"
    api_keys_csv   = "${module.key_vault.vault_uri}secrets/mdm-api-keys-csv"
  } : {}
}

output "mdm_neo4j_storage_account_name" {
  description = "Neo4j data storage account shell name."
  value       = try(module.mdm[0].neo4j_storage_account_name, null)
}

output "mdm_neo4j_storage_share_name" {
  description = "Neo4j data storage share shell name."
  value       = try(module.mdm[0].neo4j_storage_share_name, null)
}
