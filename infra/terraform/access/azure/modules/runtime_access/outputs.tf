output "identity_id" {
  description = "User-assigned managed identity ID for out-of-band jobs."
  value       = azurerm_user_assigned_identity.jobs.id
}

output "identity_principal_id" {
  description = "Managed identity principal ID for out-of-band jobs."
  value       = azurerm_user_assigned_identity.jobs.principal_id
}

output "identity_client_id" {
  description = "Managed identity client ID for out-of-band jobs."
  value       = azurerm_user_assigned_identity.jobs.client_id
}
