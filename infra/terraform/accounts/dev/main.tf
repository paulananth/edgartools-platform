locals {
  environment        = "dev"
  bronze_bucket_name = coalesce(var.bronze_bucket_name, "edgartools-dev-bronze")
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
  snowflake_export_bucket_name = local.snowflake_export_bucket_name
  tags                         = var.tags
}


# The dev warehouse bucket is retired with the decommissioned dev environment.
# Forget any stale state without destroying bucket data.
removed {
  from = module.storage.aws_s3_bucket.warehouse

  lifecycle {
    destroy = false
  }
}

removed {
  from = module.storage.aws_s3_bucket_public_access_block.warehouse

  lifecycle {
    destroy = false
  }
}

removed {
  from = module.storage.aws_s3_bucket_server_side_encryption_configuration.warehouse

  lifecycle {
    destroy = false
  }
}

removed {
  from = module.storage.aws_s3_bucket_versioning.warehouse

  lifecycle {
    destroy = false
  }
}

removed {
  from = module.storage.aws_s3_bucket_ownership_controls.warehouse

  lifecycle {
    destroy = false
  }
}

module "runtime" {
  source = "../../modules/warehouse_runtime"

  environment                  = local.environment
  snowflake_export_bucket_name = module.storage.snowflake_export_bucket_name
  edgar_identity_secret_arn    = var.edgar_identity_secret_arn
  ecr_force_delete             = true
  tags                         = var.tags
}
