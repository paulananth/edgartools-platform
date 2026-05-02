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

output "neo4j_storage_account_name" {
  description = "Neo4j data storage account shell name."
  value       = azurerm_storage_account.neo4j.name
}

output "neo4j_storage_share_name" {
  description = "Neo4j data storage share shell name."
  value       = azurerm_storage_share.neo4j.name
}
