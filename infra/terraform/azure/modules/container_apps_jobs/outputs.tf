output "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID."
  value       = azurerm_log_analytics_workspace.this.id
}
