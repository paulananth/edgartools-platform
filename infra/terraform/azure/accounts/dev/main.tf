data "azurerm_client_config" "current" {}

locals {
  environment               = "dev"
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
  workflows = merge(
    {
      bootstrap_recent_10 = {
        command  = ["bootstrap-recent-10"]
        cpu      = 1
        memory   = "2Gi"
        schedule = null
      }
    },
    var.daily_incremental_schedule == null ? {} : {
      daily_incremental = {
        command  = ["daily-incremental"]
        cpu      = 1
        memory   = "2Gi"
        schedule = var.daily_incremental_schedule
      }
    }
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

  environment               = local.environment
  name_prefix               = var.name_prefix
  resource_group_name       = module.resource_group.name
  location                  = module.resource_group.location
  container_image           = var.transform_container_image
  acr_id                    = module.acr.id
  acr_login_server          = module.acr.login_server
  storage_account_id        = module.storage.id
  key_vault_id              = module.key_vault.id
  tenant_id                 = data.azurerm_client_config.current.tenant_id
  warehouse_bronze_root     = module.storage.warehouse_bronze_root
  warehouse_storage_root    = module.storage.warehouse_storage_root
  serving_export_root       = module.storage.serving_export_root
  edgar_identity_secret_uri = "${module.key_vault.vault_uri}secrets/edgar-identity"
  warehouse_runtime_mode    = var.warehouse_runtime_mode
  workflows                 = local.workflows
  tags                      = local.tags
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

  environment                  = local.environment
  name_prefix                  = var.name_prefix
  resource_group_name          = module.resource_group.name
  location                     = module.resource_group.location
  key_vault_id                 = module.key_vault.id
  container_app_environment_id = module.container_jobs.environment_id
  container_image              = var.mdm_container_image
  acr_login_server             = module.acr.login_server
  workload_identity_id         = module.container_jobs.identity_id
  workload_identity_client_id  = module.container_jobs.identity_client_id
  sql_server_name              = var.mdm_sql_server_name
  sql_location                 = var.mdm_sql_location
  sql_database_name            = var.mdm_sql_database_name
  sql_admin_username           = var.mdm_sql_admin_username
  sql_database_sku_name        = var.mdm_sql_database_sku_name
  sql_database_max_size_gb     = var.mdm_sql_database_max_size_gb
  sql_firewall_rules           = var.mdm_sql_firewall_rules
  neo4j_storage_account_name   = var.mdm_neo4j_storage_account_name
  neo4j_external_enabled       = var.mdm_neo4j_external_enabled
  mdm_api_external_enabled     = var.mdm_api_external_enabled
  mdm_silver_duckdb_path       = coalesce(var.mdm_silver_duckdb_path, "${module.storage.warehouse_storage_root}/silver/sec/silver.duckdb")
  mdm_run_limit                = var.mdm_run_limit
  api_keys                     = var.mdm_api_keys
  tags                         = local.tags

  depends_on = [module.key_vault, module.container_jobs]
}
