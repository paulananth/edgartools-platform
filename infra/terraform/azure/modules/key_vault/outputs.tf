output "id" {
  description = "Key Vault ID."
  value       = azurerm_key_vault.this.id
}

output "name" {
  description = "Key Vault name."
  value       = azurerm_key_vault.this.name
}

output "vault_uri" {
  description = "Key Vault URI."
  value       = azurerm_key_vault.this.vault_uri
}
