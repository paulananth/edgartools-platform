locals {
  environment           = "prod"
  bronze_bucket_name    = coalesce(var.bronze_bucket_name, "edgartools-prod-bronze")
  warehouse_bucket_name = coalesce(var.warehouse_bucket_name, "edgartools-prod-warehouse")
  snowflake_export_bucket_name = coalesce(
    var.snowflake_export_bucket_name,
    "edgartools-prod-snowflake-export",
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
  source = "../../modules/storage_buckets"

  environment                  = local.environment
  bronze_bucket_name           = local.bronze_bucket_name
  warehouse_bucket_name        = local.warehouse_bucket_name
  snowflake_export_bucket_name = local.snowflake_export_bucket_name
  tags                         = var.tags
}

module "runtime" {
  source = "../../modules/warehouse_runtime"

  environment                  = local.environment
  snowflake_export_bucket_name = module.storage.snowflake_export_bucket_name
  edgar_identity_secret_arn    = var.edgar_identity_secret_arn
  ecr_force_delete             = false
  tags                         = var.tags
}
