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

  lifecycle {
    ignore_changes = [directory, file_format]
  }
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

  # stage is built from local.stage_fqn (a plain string interpolation, not a
  # resource attribute reference), so Terraform sees no implicit dependency
  # edge on snowflake_stage_internal.dashboard_src and is free to create
  # both in parallel. Hit live in prod for GH-252's second dashboard
  # instance: "The specified stage DASHBOARD_SRC does not exist" when the
  # streamlit create raced ahead of the stage create. The first (GH-246)
  # instance never hit this only by ordering luck.
  depends_on = [snowflake_stage_internal.dashboard_src]
}
