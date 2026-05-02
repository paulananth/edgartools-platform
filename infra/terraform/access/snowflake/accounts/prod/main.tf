data "terraform_remote_state" "provisioning" {
  backend = "s3"

  config = {
    bucket = var.provisioning_state_bucket
    key    = var.provisioning_state_key
    region = var.provisioning_state_region
  }
}

locals {
  environment  = "prod"
  provisioning = data.terraform_remote_state.provisioning.outputs
}

module "account_access" {
  source = "../../modules/account_access"

  environment                        = local.environment
  database_name                      = local.provisioning.database_name
  source_schema_name                 = local.provisioning.schema_names.source
  gold_schema_name                   = local.provisioning.schema_names.gold
  role_names                         = local.provisioning.role_names
  warehouse_names                    = local.provisioning.warehouse_names
  dashboard_schema_name              = local.provisioning.dashboard_schema_name
  dashboard_streamlit_qualified_name = local.provisioning.dashboard_streamlit_qualified_name
  grant_roles_to_admin               = var.grant_roles_to_admin
  parent_admin_role_name             = var.parent_admin_role_name
}
