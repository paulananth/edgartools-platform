output "runtime_identity_id" {
  description = "Prod managed identity ID for out-of-band runtime jobs."
  value       = module.runtime_access.identity_id
}

output "runtime_identity_principal_id" {
  description = "Prod managed identity principal ID for out-of-band runtime jobs."
  value       = module.runtime_access.identity_principal_id
}

output "runtime_identity_client_id" {
  description = "Prod managed identity client ID for out-of-band runtime jobs."
  value       = module.runtime_access.identity_client_id
}
