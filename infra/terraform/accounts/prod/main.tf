locals {
  environment           = "prod"
  bronze_bucket_name    = coalesce(var.bronze_bucket_name, "edgartools-prod-bronze-690839588395")
  warehouse_bucket_name = coalesce(var.warehouse_bucket_name, "edgartools-prod-warehouse-690839588395")
  snowflake_export_bucket_name = coalesce(
    var.snowflake_export_bucket_name,
    "edgartools-prod-snowflake-export-690839588395",
  )
}

data "aws_caller_identity" "current" {}

check "canonical_prod_account" {
  assert {
    condition     = data.aws_caller_identity.current.account_id == var.expected_aws_account_id
    error_message = "Production Terraform must run in canonical AWS account ${var.expected_aws_account_id}."
  }
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

# ── Pipeline Failure Notifications ────────────────────────────────────────────
#
# Dev deployment target per CONTEXT.md D-03. Although this is the prod account
# root (local.environment = "prod"), the notification infra targets the dev
# Step Functions state machines. environment = "dev" is passed as a string
# literal — do NOT use local.environment here, or the EventBridge prefix filter
# would become edgartools-prod-* and match zero existing state machines.
#
# Enable with:  terraform apply -var="pipeline_notifications_enabled=true" \
#                               -var="pipeline_failure_subscriber_email=you@example.com"
#
module "pipeline_notifications" {
  count  = var.pipeline_notifications_enabled ? 1 : 0
  source = "../../modules/pipeline_notifications"

  environment      = "dev"
  name_prefix      = "edgartools-dev"
  aws_region       = var.aws_region
  account_id       = "690839588395"
  subscriber_email = var.pipeline_failure_subscriber_email
  tags             = var.tags
}
