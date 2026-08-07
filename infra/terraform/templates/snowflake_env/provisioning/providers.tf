provider "snowflake" {
  organization_name = var.snowflake_organization_name
  account_name      = var.snowflake_account_name
  user              = var.snowflake_user
  password          = var.snowflake_password
  authenticator     = var.snowflake_authenticator
  role              = var.snowflake_admin_role
  preview_features_enabled = [
    "snowflake_file_format_resource",
    "snowflake_pipe_resource",
    "snowflake_stage_external_s3_resource",
    "snowflake_stage_internal_resource",
    "snowflake_storage_integration_aws_resource",
    "snowflake_table_resource",
  ]
}
