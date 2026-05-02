data "azurerm_client_config" "current" {}

locals {
  environment               = "prod"
  resource_group_name       = coalesce(var.resource_group_name, "${var.name_prefix}-rg")
  databricks_workspace_name = coalesce(var.databricks_workspace_name, "${var.name_prefix}-dbw")
  tags = merge(
    {
      Environment = local.environment
      ManagedBy   = "terraform"
      Project     = "edgartools"
    },
    var.tags,
  )
}

module "resource_group" {
  source = "../../modules/resource_group"

  name     = local.resource_group_name
  location = var.location
  tags     = local.tags
}

module "storage" {
  source = "../../modules/storage_account"

  name                = var.storage_account_name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  tags                = local.tags
}

module "acr" {
  source = "../../modules/container_registry"

  name                = var.container_registry_name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  sku                 = "Standard"
  tags                = local.tags
}

module "key_vault" {
  source = "../../modules/key_vault"

  name                = var.key_vault_name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  tags                = local.tags
}

module "container_jobs" {
  source = "../../modules/container_apps_jobs"

  name_prefix         = var.name_prefix
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  tags                = local.tags
}

module "databricks" {
  source = "../../modules/databricks_workspace"

  name                = local.databricks_workspace_name
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  tags                = local.tags
}

module "mdm" {
  count  = var.enable_mdm ? 1 : 0
  source = "../../modules/mdm_data_plane"

  resource_group_name          = module.resource_group.name
  location                     = module.resource_group.location
  tenant_id                    = data.azurerm_client_config.current.tenant_id
  sql_server_name              = var.mdm_sql_server_name
  sql_location                 = var.mdm_sql_location
  sql_database_name            = var.mdm_sql_database_name
  sql_aad_admin_login_username = var.mdm_sql_aad_admin_login_username
  sql_aad_admin_object_id      = coalesce(var.mdm_sql_aad_admin_object_id, data.azurerm_client_config.current.object_id)
  sql_database_sku_name        = var.mdm_sql_database_sku_name
  sql_database_max_size_gb     = var.mdm_sql_database_max_size_gb
  sql_firewall_rules           = var.mdm_sql_firewall_rules
  neo4j_storage_account_name   = var.mdm_neo4j_storage_account_name
  tags                         = local.tags

  depends_on = [module.key_vault, module.container_jobs]
}
