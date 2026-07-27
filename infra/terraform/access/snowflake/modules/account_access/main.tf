locals {
  schema_names = {
    source = var.source_schema_name
    gold   = var.gold_schema_name
  }

  schema_fqns = {
    for key, schema_name in local.schema_names :
    key => "${var.database_name}.${schema_name}"
  }

  dashboard_schema_fqn = "${var.database_name}.${var.dashboard_schema_name}"
}

resource "snowflake_account_role" "roles" {
  for_each = var.role_names

  name    = each.value
  comment = "Access-control ${each.key} role for the EdgarTools ${var.environment} gold mirror."
}

resource "snowflake_grant_account_role" "roles_to_admin" {
  for_each = var.grant_roles_to_admin ? var.role_names : {}

  role_name        = snowflake_account_role.roles[each.key].name
  parent_role_name = var.parent_admin_role_name
}

resource "snowflake_grant_privileges_to_account_role" "database_usage" {
  for_each = var.role_names

  account_role_name = snowflake_account_role.roles[each.key].name
  privileges = each.key == "deployer" ? [
    "USAGE",
    "MONITOR",
    "CREATE SCHEMA",
    ] : [
    "USAGE",
    "MONITOR",
  ]

  on_account_object {
    object_type = "DATABASE"
    object_name = var.database_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "deployer_account_privileges" {
  account_role_name = snowflake_account_role.roles["deployer"].name
  privileges        = ["CREATE INTEGRATION"]
  on_account        = true
}

resource "snowflake_grant_privileges_to_account_role" "schema_usage" {
  for_each = {
    for grant in flatten([
      {
        id         = "deployer_source"
        role_key   = "deployer"
        schema_key = "source"
        privileges = ["USAGE", "CREATE TABLE", "CREATE VIEW", "CREATE STAGE", "CREATE FILE FORMAT", "CREATE PROCEDURE", "CREATE TASK", "CREATE PIPE", "CREATE STREAM"]
      },
      {
        id         = "deployer_gold"
        role_key   = "deployer"
        schema_key = "gold"
        privileges = ["USAGE", "CREATE TABLE", "CREATE VIEW", "CREATE STAGE", "CREATE FILE FORMAT", "CREATE PROCEDURE", "CREATE TASK", "CREATE DYNAMIC TABLE"]
      },
      {
        id         = "loader_source"
        role_key   = "loader"
        schema_key = "source"
        privileges = ["USAGE", "CREATE TABLE", "CREATE VIEW", "CREATE STAGE", "CREATE FILE FORMAT", "CREATE PROCEDURE", "CREATE TASK", "CREATE PIPE", "CREATE STREAM"]
      },
      {
        id         = "loader_gold"
        role_key   = "loader"
        schema_key = "gold"
        privileges = ["USAGE", "CREATE DYNAMIC TABLE", "CREATE PROCEDURE", "CREATE TASK"]
      },
      {
        id         = "reader_gold"
        role_key   = "reader"
        schema_key = "gold"
        privileges = ["USAGE"]
      },
    ]) :
    grant.id => grant
  }

  account_role_name = snowflake_account_role.roles[each.value.role_key].name
  privileges        = each.value.privileges

  on_schema {
    schema_name = local.schema_fqns[each.value.schema_key]
  }
}

resource "snowflake_grant_privileges_to_account_role" "warehouse_usage" {
  for_each = {
    for grant in flatten([
      {
        id            = "deployer_refresh"
        role_key      = "deployer"
        warehouse_key = "refresh"
        privileges    = ["USAGE", "MONITOR", "OPERATE"]
      },
      {
        id            = "deployer_reader"
        role_key      = "deployer"
        warehouse_key = "reader"
        privileges    = ["USAGE", "MONITOR", "OPERATE"]
      },
      {
        id            = "loader_refresh"
        role_key      = "loader"
        warehouse_key = "refresh"
        privileges    = ["USAGE", "MONITOR", "OPERATE"]
      },
      {
        id            = "reader_reader"
        role_key      = "reader"
        warehouse_key = "reader"
        privileges    = ["USAGE"]
      },
    ]) :
    grant.id => grant
  }

  account_role_name = snowflake_account_role.roles[each.value.role_key].name
  privileges        = each.value.privileges

  on_account_object {
    object_type = "WAREHOUSE"
    object_name = var.warehouse_names[each.value.warehouse_key]
  }
}

resource "snowflake_grant_privileges_to_account_role" "deployer_source_all_objects" {
  for_each = toset(["TABLES", "VIEWS", "DYNAMIC TABLES"])

  account_role_name = snowflake_account_role.roles["deployer"].name
  privileges        = ["SELECT"]

  on_schema_object {
    all {
      object_type_plural = each.value
      in_schema          = local.schema_fqns["source"]
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "deployer_source_future_objects" {
  for_each = toset(["TABLES", "VIEWS", "DYNAMIC TABLES"])

  account_role_name = snowflake_account_role.roles["deployer"].name
  privileges        = ["SELECT"]

  on_schema_object {
    future {
      object_type_plural = each.value
      in_schema          = local.schema_fqns["source"]
    }
  }
}

# loader reads every EDGARTOOLS_SOURCE table (current + future) to run the
# manifest pipeline (LOAD_EXPORTS_FOR_RUN). Two object-level grants this role
# also needs -- SELECT on the manifest stream, SELECT+UPDATE on
# SNOWFLAKE_REFRESH_STATUS -- aren't modeled here (Terraform doesn't grant
# per-object privileges anywhere in this module, only schema/database/
# warehouse-level); they're granted by
# infra/snowflake/sql/bootstrap/08_loader_role.sql, which also owns
# transferring ownership of the EDGARTOOLS_GOLD dynamic tables and the 3
# manifest procedures onto this role -- object ownership isn't something
# this Terraform module manages for any role, including deployer.
resource "snowflake_grant_privileges_to_account_role" "loader_source_all_objects" {
  for_each = toset(["TABLES", "VIEWS", "DYNAMIC TABLES"])

  account_role_name = snowflake_account_role.roles["loader"].name
  privileges        = ["SELECT"]

  on_schema_object {
    all {
      object_type_plural = each.value
      in_schema          = local.schema_fqns["source"]
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "loader_source_future_objects" {
  for_each = toset(["TABLES", "VIEWS", "DYNAMIC TABLES"])

  account_role_name = snowflake_account_role.roles["loader"].name
  privileges        = ["SELECT"]

  on_schema_object {
    future {
      object_type_plural = each.value
      in_schema          = local.schema_fqns["source"]
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_all_schema_objects" {
  for_each = toset(["TABLES", "VIEWS", "DYNAMIC TABLES"])

  account_role_name = snowflake_account_role.roles["reader"].name
  privileges        = ["SELECT"]

  on_schema_object {
    all {
      object_type_plural = each.value
      in_schema          = local.schema_fqns["gold"]
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_future_schema_objects" {
  for_each = toset(["TABLES", "VIEWS", "DYNAMIC TABLES"])

  account_role_name = snowflake_account_role.roles["reader"].name
  privileges        = ["SELECT"]

  on_schema_object {
    future {
      object_type_plural = each.value
      in_schema          = local.schema_fqns["gold"]
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_dashboard_schema_usage" {
  account_role_name = snowflake_account_role.roles["reader"].name
  privileges        = ["USAGE"]

  on_schema {
    schema_name = local.dashboard_schema_fqn
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_dashboard_streamlit_usage" {
  account_role_name = snowflake_account_role.roles["reader"].name
  privileges        = ["USAGE"]

  on_schema_object {
    object_type = "STREAMLIT"
    object_name = var.dashboard_streamlit_qualified_name
  }
}
