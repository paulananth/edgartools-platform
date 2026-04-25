output "id" {
  description = "Storage account ID."
  value       = azurerm_storage_account.this.id
}

output "name" {
  description = "Storage account name."
  value       = azurerm_storage_account.this.name
}

output "primary_dfs_endpoint" {
  description = "Primary ADLS Gen2 DFS endpoint."
  value       = azurerm_storage_account.this.primary_dfs_endpoint
}

output "container_names" {
  description = "Created container names."
  value       = keys(azurerm_storage_container.this)
}

output "warehouse_bronze_root" {
  description = "WAREHOUSE_BRONZE_ROOT for Azure runtime."
  value       = "abfss://bronze@${azurerm_storage_account.this.name}.dfs.core.windows.net/warehouse/bronze"
}

output "warehouse_storage_root" {
  description = "WAREHOUSE_STORAGE_ROOT for Azure runtime."
  value       = "abfss://warehouse@${azurerm_storage_account.this.name}.dfs.core.windows.net/warehouse"
}

output "serving_export_root" {
  description = "SERVING_EXPORT_ROOT for Databricks serving exports."
  value       = "abfss://serving@${azurerm_storage_account.this.name}.dfs.core.windows.net/warehouse/serving_exports"
}
