data "terraform_remote_state" "provisioning" {
  backend = "s3"

  config = {
    bucket = var.provisioning_state_bucket
    key    = var.provisioning_state_key
    region = var.provisioning_state_region
  }
}

data "terraform_remote_state" "snowflake" {
  count   = var.snowflake_state_bucket == null ? 0 : 1
  backend = "s3"

  config = {
    bucket = var.snowflake_state_bucket
    key    = var.snowflake_state_key
    region = var.snowflake_state_region
  }
}

locals {
  environment    = "prod"
  name_prefix    = "edgartools-${local.environment}"
  provisioning   = data.terraform_remote_state.provisioning.outputs
  snowflake      = try(data.terraform_remote_state.snowflake[0].outputs, {})
  subscriber_arn = try(coalesce(var.snowflake_manifest_subscriber_arn, try(local.snowflake.snowflake_manifest_subscriber_arn, null)), null)
  storage_ext_id = coalesce(var.snowflake_storage_external_id, try(local.snowflake.snowflake_storage_external_id, null), "edgartools-${local.environment}-snowflake-native-pull")
  mdm_secret_arns = [
    for arn in [
      try(local.provisioning.mdm_postgres_dsn_secret_arn, ""),
      try(local.provisioning.mdm_neo4j_secret_arn, ""),
      try(local.provisioning.mdm_api_keys_secret_arn, ""),
      try(local.provisioning.mdm_snowflake_secret_arn, ""),
    ] : arn if arn != null && arn != ""
  ]
}

module "runtime_access" {
  source = "../../modules/runtime_access"

  environment                       = local.environment
  name_prefix                       = local.name_prefix
  # edgartools-prod-* S3 bucket names are already claimed globally by the real
  # prod AWS account; this build uses edgartools-prodb-* naming for globally-
  # namespaced resources (see accounts/prod/terraform.tfvars). The
  # sec_platform_runner_* IAM roles are NOT namespaced by name_prefix upstream
  # (account-scoped, historically a single fixed name) and this account
  # already has dev's sec_platform_runner_* roles, whose attached policies are
  # scoped to dev's exact resource ARNs -- reusing them here would silently
  # produce AccessDenied on prodb resources at runtime. Use a distinct prefix.
  runner_role_name_prefix           = "sec_platform_prodb"
  bronze_bucket_name                = local.provisioning.bronze_bucket_name
  bronze_bucket_arn                 = local.provisioning.bronze_bucket_arn
  warehouse_bucket_arn              = local.provisioning.warehouse_bucket_arn
  snowflake_export_bucket_arn       = local.provisioning.snowflake_export_bucket_arn
  snowflake_export_kms_key_arn      = local.provisioning.snowflake_export_kms_key_arn
  snowflake_export_prefix           = local.provisioning.snowflake_export_prefix
  snowflake_manifest_sns_topic_arn  = local.provisioning.snowflake_manifest_sns_topic_arn
  edgar_identity_secret_arn         = local.provisioning.edgar_identity_secret_arn
  mdm_secret_arns                   = local.mdm_secret_arns
  snowflake_manifest_subscriber_arn = local.subscriber_arn
  snowflake_bootstrap_enabled       = var.snowflake_bootstrap_enabled
  snowflake_storage_external_id     = local.storage_ext_id
  tags                              = var.tags
}
