data "azurerm_client_config" "current" {}

data "terraform_remote_state" "provisioning" {
  backend = "azurerm"

  config = {
    resource_group_name  = var.provisioning_state_resource_group_name
    storage_account_name = var.provisioning_state_storage_account_name
    container_name       = var.provisioning_state_container_name
    key                  = var.provisioning_state_key
  }
}

locals {
  environment         = "prod"
  provisioning        = data.terraform_remote_state.provisioning.outputs
  operator_object_ids = length(var.operator_object_ids) == 0 ? toset([data.azurerm_client_config.current.object_id]) : var.operator_object_ids
  tags = merge(
    {
      Environment = local.environment
      ManagedBy   = "terraform"
      Project     = "edgartools"
    },
    var.tags,
  )
}

module "runtime_access" {
  source = "../../modules/runtime_access"

  name_prefix         = var.name_prefix
  resource_group_name = local.provisioning.resource_group_name
  location            = local.provisioning.resource_group_location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  acr_id              = local.provisioning.container_registry_id
  storage_account_id  = local.provisioning.storage_account_id
  key_vault_id        = local.provisioning.key_vault_id
  operator_object_ids = local.operator_object_ids
  tags                = local.tags
}
