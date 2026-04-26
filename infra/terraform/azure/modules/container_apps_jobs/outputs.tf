output "environment_id" {
  description = "Container Apps environment ID."
  value       = azurerm_container_app_environment.this.id
}

output "identity_id" {
  description = "User-assigned managed identity ID for jobs."
  value       = azurerm_user_assigned_identity.jobs.id
}

output "identity_principal_id" {
  description = "Managed identity principal ID for jobs."
  value       = azurerm_user_assigned_identity.jobs.principal_id
}

output "identity_client_id" {
  description = "Managed identity client ID for jobs."
  value       = azurerm_user_assigned_identity.jobs.client_id
}

output "job_names" {
  description = "Container Apps Job names by workflow key."
  value       = { for key, job in azurerm_container_app_job.workflow : key => job.name }
}
