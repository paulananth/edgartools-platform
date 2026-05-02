locals {
  schema_names = {
    source = var.source_schema_name
    gold   = var.gold_schema_name
  }

  roles = {
    deployer  = var.deployer_role_name
    refresher = var.refresher_role_name
    reader    = var.reader_role_name
  }

  warehouses = {
    refresh = {
      name = var.refresh_warehouse_name
      size = var.refresh_warehouse_size
    }
    reader = {
      name = var.reader_warehouse_name
      size = var.reader_warehouse_size
    }
  }

  schema_fqns = {
    for key, schema_name in local.schema_names :
    key => "${var.database_name}.${schema_name}"
  }
}

resource "snowflake_database" "this" {
  name                        = var.database_name
  comment                     = "Baseline database for the EdgarTools ${var.environment} gold mirror."
  data_retention_time_in_days = var.data_retention_time_in_days
}

resource "snowflake_schema" "schemas" {
  for_each = local.schema_names

  database                    = snowflake_database.this.name
  name                        = each.value
  comment                     = "Baseline ${each.key} schema for the EdgarTools ${var.environment} gold mirror."
  data_retention_time_in_days = var.data_retention_time_in_days

  lifecycle {
    # is_transient drifts between "false" (Snowflake default) and "default" (provider default)
    # when importing existing non-transient schemas.  Ignore to prevent forced replacement.
    ignore_changes = [is_transient]
  }
}

resource "snowflake_warehouse" "warehouses" {
  for_each = local.warehouses

  name                = each.value.name
  comment             = "Baseline ${each.key} warehouse for the EdgarTools ${var.environment} gold mirror."
  warehouse_size      = each.value.size
  auto_suspend        = var.warehouse_auto_suspend_seconds
  auto_resume         = true
  initially_suspended = true
}
