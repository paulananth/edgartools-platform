resource "azurerm_user_assigned_identity" "jobs" {
  name                = "${var.name_prefix}-jobs"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.jobs.principal_id
}

resource "azurerm_role_assignment" "storage_blob_contributor" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.jobs.principal_id
}

resource "azurerm_key_vault_access_policy" "runtime" {
  key_vault_id = var.key_vault_id
  tenant_id    = var.tenant_id
  object_id    = azurerm_user_assigned_identity.jobs.principal_id

  secret_permissions = var.runtime_secret_permissions
}

resource "azurerm_key_vault_access_policy" "operator" {
  for_each = var.operator_object_ids

  key_vault_id = var.key_vault_id
  tenant_id    = var.tenant_id
  object_id    = each.value

  secret_permissions = var.operator_secret_permissions
}
