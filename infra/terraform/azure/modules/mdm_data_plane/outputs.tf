output "sql_server_name" {
  description = "Azure SQL logical server name."
  value       = azurerm_mssql_server.mdm.name
}

output "sql_server_fqdn" {
  description = "Azure SQL logical server FQDN."
  value       = azurerm_mssql_server.mdm.fully_qualified_domain_name
}

output "sql_database_name" {
  description = "Azure SQL database name."
  value       = azurerm_mssql_database.mdm.name
}

output "database_url_secret_id" {
  description = "Key Vault secret ID for MDM_DATABASE_URL."
  value       = azurerm_key_vault_secret.database_url.id
}

output "neo4j_container_app_name" {
  description = "Neo4j Container App name."
  value       = azurerm_container_app.neo4j.name
}

output "neo4j_fqdn" {
  description = "Neo4j Container App FQDN."
  value       = azurerm_container_app.neo4j.latest_revision_fqdn
}

output "neo4j_uri" {
  description = "Neo4j Bolt URI."
  value       = local.neo4j_bolt_uri
}

output "neo4j_secret_id" {
  description = "Key Vault secret ID for Neo4j connection details."
  value       = azurerm_key_vault_secret.neo4j.id
}

output "neo4j_uri_secret_id" {
  description = "Key Vault secret ID for NEO4J_URI."
  value       = azurerm_key_vault_secret.neo4j_uri.id
}

output "api_keys_secret_id" {
  description = "Key Vault secret ID for MDM API keys."
  value       = azurerm_key_vault_secret.api_keys.id
}

output "api_keys_csv_secret_id" {
  description = "Key Vault secret ID for comma-delimited MDM API keys."
  value       = azurerm_key_vault_secret.api_keys_csv.id
}

output "mdm_api_fqdn" {
  description = "MDM API Container App FQDN."
  value       = azurerm_container_app.mdm_api.latest_revision_fqdn
}

output "mdm_job_names" {
  description = "MDM Container Apps Job names by workflow."
  value       = { for key, job in azurerm_container_app_job.mdm : key => job.name }
}
