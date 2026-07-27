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
  decision_schema_fqn  = "${var.database_name}.${var.decision_schema_name}"

  # GH-247 criterion 2: "permitted operational status" objects the SiS
  # dashboard's Pipeline tab reads (streamlit_app.py's _pipeline_runs/
  # _pipeline_task_history/_manifest_copy_history) -- named explicitly,
  # not a blanket grant across all of EDGARTOOLS_SOURCE.
  status_object_names = [
    "SNOWFLAKE_REFRESH_STATUS",
    "SNOWFLAKE_RUN_MANIFEST_INBOX",
  ]
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

# GH-247: dashboard_owner is the least-privilege role that owns the
# Streamlit-in-Snowflake dashboard object and its source stage --
# distinct from reader (viewer access above) and from
# deployer/loader (data-plane roles). It gets NO direct SELECT on gold/
# decision/status data: SiS dashboards run under Caller's Rights, so the
# viewing session's own role (reader) is what governs query access, not
# the object owner's. Purely additive grants -- does not touch any
# existing role's grant set, so this cannot repeat the 2026-07-27
# REVOKE-CURRENT-GRANTS reader-access incident (CLAUDE.md "Manifest-
# pipeline ownership + cursor-syntax incident 5-whys").
#
# NOT applied to live Snowflake by this commit. Two things a live-apply
# pass still needs to verify, not assumed correct here:
#   1. Whether CREATE STAGE / CREATE STREAMLIT are exactly the privilege
#      names this Snowflake Terraform provider version expects (schema-
#      object-creation privilege naming has shifted across provider
#      versions) -- confirm via `terraform plan` before applying.
#   2. If the dashboard schema/stage/Streamlit object already exist
#      under a different owner (they do today -- created ad hoc by
#      deploy.sh's SnowCLI session), transferring ownership needs
#      `COPY CURRENT GRANTS` (not `REVOKE CURRENT GRANTS`, the exact
#      mistake in the incident above) and is a deliberate, separately
#      approved live step, not something this Terraform commit performs.
resource "snowflake_grant_privileges_to_account_role" "dashboard_owner_schema_grants" {
  account_role_name = snowflake_account_role.roles["dashboard_owner"].name
  privileges        = ["USAGE", "CREATE STAGE", "CREATE STREAMLIT"]

  on_schema {
    schema_name = local.dashboard_schema_fqn
  }
}

resource "snowflake_grant_privileges_to_account_role" "dashboard_owner_warehouse_usage" {
  account_role_name = snowflake_account_role.roles["dashboard_owner"].name
  privileges        = ["USAGE"]

  on_account_object {
    object_type = "WAREHOUSE"
    object_name = var.warehouse_names["reader"]
  }
}

# GH-246/GH-247 criterion 2: Decision Contract dependency modeled
# explicitly for the dashboard's viewer role. EDGARTOOLS_DECISION is not
# provisioned by account_baseline (see decision_schema_name's
# description) -- referenced here by name only.
resource "snowflake_grant_privileges_to_account_role" "reader_decision_schema_usage" {
  account_role_name = snowflake_account_role.roles["reader"].name
  privileges        = ["USAGE"]

  on_schema {
    schema_name = local.decision_schema_fqn
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_decision_all_objects" {
  for_each = toset(["TABLES", "VIEWS"])

  account_role_name = snowflake_account_role.roles["reader"].name
  privileges        = ["SELECT"]

  on_schema_object {
    all {
      object_type_plural = each.value
      in_schema          = local.decision_schema_fqn
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "reader_decision_future_objects" {
  for_each = toset(["TABLES", "VIEWS"])

  account_role_name = snowflake_account_role.roles["reader"].name
  privileges        = ["SELECT"]

  on_schema_object {
    future {
      object_type_plural = each.value
      in_schema          = local.decision_schema_fqn
    }
  }
}

# GH-247 criterion 2: bounded "permitted operational status" dependency --
# only the 2 EDGARTOOLS_SOURCE tables streamlit_app.py's Pipeline tab
# directly SELECTs from (_pipeline_runs), not blanket SOURCE-schema
# access. NOT covered here (left as an explicitly unverified follow-up,
# not guessed): the Pipeline tab's 3 other calls
# (_pipeline_task_history/_manifest_copy_history/
# _dynamic_table_refresh_history) go through
# `table(information_schema.*_history(...))` table functions, whose
# exact required privilege (MONITOR on the referenced task/table vs.
# plain SELECT) was not verified against live Snowflake for this PR.
resource "snowflake_grant_privileges_to_account_role" "reader_source_status_objects" {
  for_each = toset(local.status_object_names)

  account_role_name = snowflake_account_role.roles["reader"].name
  privileges        = ["SELECT"]

  on_schema_object {
    object_type = "TABLE"
    object_name = "${local.schema_fqns["source"]}.${each.value}"
  }
}
