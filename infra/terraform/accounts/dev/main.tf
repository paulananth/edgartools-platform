locals {
  environment           = "dev"
  bronze_bucket_name    = coalesce(var.bronze_bucket_name, "edgartools-dev-bronze")
  warehouse_bucket_name = coalesce(var.warehouse_bucket_name, "edgartools-dev-warehouse")
  storage_external_id   = coalesce(var.snowflake_storage_external_id, "edgartools-${local.environment}-snowflake-native-pull")
  snowflake_export_bucket_name = coalesce(
    var.snowflake_export_bucket_name,
    "edgartools-dev-snowflake-export",
  )
}

module "network" {
  source = "../../modules/network_runtime"

  environment         = local.environment
  name_prefix         = "edgartools-${local.environment}"
  vpc_cidr            = var.vpc_cidr
  public_subnet_cidrs = var.public_subnet_cidrs
  availability_zones  = var.availability_zones
  tags                = var.tags
}

module "storage" {
  source = "../../modules/storage_buckets_destroyable"

  environment                  = local.environment
  bronze_bucket_name           = local.bronze_bucket_name
  warehouse_bucket_name        = local.warehouse_bucket_name
  snowflake_export_bucket_name = local.snowflake_export_bucket_name
  tags                         = var.tags
}

module "runtime" {
  source = "../../modules/warehouse_runtime"

  environment                       = local.environment
  aws_region                        = var.aws_region
  container_image                   = var.container_image
  warehouse_runtime_mode            = var.warehouse_runtime_mode
  warehouse_bronze_cik_limit        = var.warehouse_bronze_cik_limit
  bronze_bucket_name                = module.storage.bronze_bucket_name
  bronze_bucket_arn                 = module.storage.bronze_bucket_arn
  warehouse_bucket_name             = module.storage.warehouse_bucket_name
  warehouse_bucket_arn              = module.storage.warehouse_bucket_arn
  snowflake_export_bucket_name      = module.storage.snowflake_export_bucket_name
  snowflake_export_bucket_arn       = module.storage.snowflake_export_bucket_arn
  snowflake_export_kms_key_arn      = module.storage.snowflake_export_kms_key_arn
  snowflake_manifest_subscriber_arn = var.snowflake_manifest_subscriber_arn
  snowflake_bootstrap_enabled       = var.snowflake_bootstrap_enabled
  snowflake_storage_external_id     = local.storage_external_id
  public_subnet_ids                 = module.network.public_subnet_ids
  public_security_group_id          = module.network.public_ecs_security_group_id
  edgar_identity_secret_arn         = var.edgar_identity_secret_arn
  edgar_identity_value              = var.edgar_identity_value
  daily_incremental_schedule        = var.daily_incremental_schedule
  full_reconcile_schedule           = var.full_reconcile_schedule
  schedule_timezone                 = var.schedule_timezone
  task_profiles                     = var.task_profiles
  task_profile_by_workflow          = var.task_profile_by_workflow
  ecr_force_delete                  = true
  runner_user_force_destroy         = true
  tags                              = var.tags
}
