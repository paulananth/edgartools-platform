locals {
  dashboard_schema_fqn = "${var.database_name}.${var.dashboard_schema_name}"
  stage_fqn            = "${local.dashboard_schema_fqn}.${var.stage_name}"
  streamlit_fqn        = "${local.dashboard_schema_fqn}.${var.streamlit_name}"
}

resource "snowflake_schema" "dashboard" {
  database = var.database_name
  name     = var.dashboard_schema_name
  comment  = "Streamlit-in-Snowflake dashboard schema for EdgarTools ${var.environment}."

  lifecycle {
    ignore_changes = [is_transient]
  }
}

resource "snowflake_stage_internal" "dashboard_src" {
  database = var.database_name
  schema   = snowflake_schema.dashboard.name
  name     = var.stage_name
  comment  = "Internal stage holding the Streamlit source files for the EdgarTools ${var.environment} dashboard."
}

resource "snowflake_streamlit" "dashboard" {
  database        = var.database_name
  schema          = snowflake_schema.dashboard.name
  name            = var.streamlit_name
  stage           = local.stage_fqn
  main_file       = var.streamlit_main_file
  query_warehouse = var.reader_warehouse_name
  title           = var.streamlit_title
  comment         = "EdgarTools ${var.environment} gold-mirror dashboard."
}

resource "snowflake_grant_privileges_to_account_role" "reader_schema_usage" {
  account_role_name = var.reader_role_name
  privileges        = ["USAGE"]

  on_schema {
    schema_name = local.dashboard_schema_fqn
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_streamlit_usage" {
  account_role_name = var.reader_role_name
  privileges        = ["USAGE"]

  on_schema_object {
    object_type = "STREAMLIT"
    object_name = local.streamlit_fqn
  }
}
