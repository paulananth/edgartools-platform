locals {
  environment            = "dev"
  database_name          = "EDGARTOOLS_DEV"
  source_schema_name     = "EDGARTOOLS_SOURCE"
  gold_schema_name       = "EDGARTOOLS_GOLD"
  deployer_role_name     = "EDGARTOOLS_DEV_DEPLOYER"
  refresher_role_name    = "EDGARTOOLS_DEV_REFRESHER"
  reader_role_name       = "EDGARTOOLS_DEV_READER"
  refresh_warehouse_name = "EDGARTOOLS_DEV_REFRESH_WH"
  reader_warehouse_name  = "EDGARTOOLS_DEV_READER_WH"
  native_pull_enabled    = var.snowflake_storage_role_arn != null && var.snowflake_export_root_url != null && var.snowflake_manifest_sns_topic_arn != null
  storage_external_id    = coalesce(var.snowflake_storage_external_id, "edgartools-${local.environment}-snowflake-native-pull")
}

module "baseline" {
  source = "../../modules/account_baseline"

  environment                    = local.environment
  database_name                  = local.database_name
  source_schema_name             = local.source_schema_name
  gold_schema_name               = local.gold_schema_name
  deployer_role_name             = local.deployer_role_name
  refresher_role_name            = local.refresher_role_name
  reader_role_name               = local.reader_role_name
  refresh_warehouse_name         = local.refresh_warehouse_name
  reader_warehouse_name          = local.reader_warehouse_name
  refresh_warehouse_size         = var.refresh_warehouse_size
  reader_warehouse_size          = var.reader_warehouse_size
  warehouse_auto_suspend_seconds = var.warehouse_auto_suspend_seconds
  data_retention_time_in_days    = var.data_retention_time_in_days
  grant_roles_to_admin           = var.grant_roles_to_admin
  parent_admin_role_name         = var.parent_admin_role_name
}

module "dashboard" {
  source = "../../modules/dashboard"

  environment           = local.environment
  database_name         = module.baseline.database_name
  gold_schema_name      = module.baseline.schema_names.gold
  reader_role_name      = module.baseline.role_names.reader
  reader_warehouse_name = module.baseline.warehouse_names.reader
}

module "native_pull" {
  count = local.native_pull_enabled ? 1 : 0

  source = "../../modules/native_pull"

  environment            = local.environment
  database_name          = module.baseline.database_name
  source_schema_name     = module.baseline.schema_names.source
  gold_schema_name       = module.baseline.schema_names.gold
  refresh_warehouse_name = module.baseline.warehouse_names.refresh
  storage_role_arn       = var.snowflake_storage_role_arn
  storage_external_id    = local.storage_external_id
  export_root_url        = var.snowflake_export_root_url
  manifest_sns_topic_arn = var.snowflake_manifest_sns_topic_arn

  depends_on = [module.baseline]
}
