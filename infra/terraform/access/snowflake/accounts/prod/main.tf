# The access controls the audit (skills/access-audit) tests, as code: read-only roles and their key-pair service users,
# and the cost and timeout guards. Changes go through plan, a recorded approval, apply, re-audit.


# --- Names ---------------------------------------------------------------------------------------------------------------
# Service logins sign in by key pair only because they are TYPE = SERVICE users, which Snowflake never lets use a password; no
# credential policy object is kept, since Snowflake keeps one only inside a database (operator, 2026-11-26).
locals {
  names         = yamldecode(file("${path.module}/../../../../../../rules/snowflake.yaml"))
  gold_database = local.names.gold.database
}

# --- Account guards -------------------------------------------------------------------------------------------------
resource "snowflake_account_parameter" "statement_timeout" {
  key   = "STATEMENT_TIMEOUT_IN_SECONDS"
  value = tostring(var.account_statement_timeout_seconds)
}

resource "snowflake_resource_monitor" "prod" {
  name            = "EDGARTOOLS_PROD_MONITOR"
  credit_quota    = var.monthly_credit_quota
  frequency       = "MONTHLY"
  start_timestamp = "IMMEDIATELY"
  notify_triggers = [75]
  suspend_trigger = 100
}

# --- The read-only log reader ---------------------------------------------------------------------------------------
resource "snowflake_account_role" "log_reader" {
  name    = "EDGARTOOLS_PROD_LOG_READER"
  comment = "Reads the Postgres server log in the event table, nothing else"
}

resource "snowflake_grant_application_role" "log_reader_events" {
  application_role_name    = "\"SNOWFLAKE\".\"EVENTS_VIEWER\""
  parent_account_role_name = snowflake_account_role.log_reader.name
}

resource "snowflake_grant_privileges_to_account_role" "log_reader_warehouse" {
  account_role_name = snowflake_account_role.log_reader.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = var.warehouse
  }
}

resource "snowflake_service_user" "log_reader" {
  name                         = "EDGARTOOLS_PROD_LOG_READER"
  default_role                 = snowflake_account_role.log_reader.name
  default_warehouse            = var.warehouse
  rsa_public_key               = var.log_reader_public_key
  statement_timeout_in_seconds = var.service_statement_timeout_seconds
  comment                      = "Read-only log monitoring"
}

resource "snowflake_grant_account_role" "log_reader" {
  role_name = snowflake_account_role.log_reader.name
  user_name = snowflake_service_user.log_reader.name
}


# --- The read-only auditor ------------------------------------------------------------------------------------------
resource "snowflake_account_role" "auditor" {
  name    = "EDGARTOOLS_PROD_AUDITOR"
  comment = "Read-only access auditor: reads metadata and usage, changes nothing"
}

resource "snowflake_grant_database_role" "auditor_viewers" {
  for_each           = toset(["SECURITY_VIEWER", "USAGE_VIEWER", "GOVERNANCE_VIEWER", "ORGANIZATION_BILLING_VIEWER"]) # the last reads the rate sheet, so a plan is priced from the account's own rates
  database_role_name = "\"SNOWFLAKE\".\"${each.key}\""
  parent_role_name   = snowflake_account_role.auditor.name
}

resource "snowflake_grant_privileges_to_account_role" "auditor_monitor" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["MONITOR USAGE"]
  on_account        = true
}

resource "snowflake_grant_privileges_to_account_role" "auditor_warehouse" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = var.warehouse
  }
}

# The Gold destination database: the auditor reads its metadata (schemas, objects, grants) to check what is there before a build, and
# no data (REFERENCES shows a table to the role without reading a row).
# Named once, in rules/snowflake.yaml; a renamed database is a one-line change there.
resource "snowflake_grant_privileges_to_account_role" "auditor_gold_database" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = local.gold_database
  }
}

resource "snowflake_grant_privileges_to_account_role" "auditor_gold_schemas" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = local.gold_database
  }
}

resource "snowflake_grant_privileges_to_account_role" "auditor_gold_future_schemas" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = local.gold_database
  }
}

# The operations database: the auditor reads its schemas, to check it holds only the one rules/snowflake.yaml names.
resource "snowflake_grant_privileges_to_account_role" "auditor_operations_database" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = local.names.operations.database
  }
}

resource "snowflake_grant_privileges_to_account_role" "auditor_operations_schemas" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = local.names.operations.database
  }
}

resource "snowflake_grant_privileges_to_account_role" "auditor_operations_future_schemas" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = local.names.operations.database
  }
}

resource "snowflake_grant_privileges_to_account_role" "auditor_gold_tables" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["REFERENCES"]
  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_database        = local.gold_database
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "auditor_gold_future_tables" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["REFERENCES"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = local.gold_database
    }
  }
}

resource "snowflake_service_user" "auditor" {
  name                         = "EDGARTOOLS_PROD_AUDITOR"
  default_role                 = snowflake_account_role.auditor.name
  default_warehouse            = var.warehouse
  rsa_public_key               = var.auditor_public_key
  statement_timeout_in_seconds = var.service_statement_timeout_seconds
  comment                      = "Read-only access audit"
}

resource "snowflake_grant_account_role" "auditor" {
  role_name = snowflake_account_role.auditor.name
  user_name = snowflake_service_user.auditor.name
}


# --- The mirror operator ---------------------------------------------------------------------------------------------
# Creates, reads back and changes the managed Postgres mirrors (SNOWFLAKE.POSTGRES.*_MIRROR) and nothing else, so no mirror
# step needs the account administrator (separation of duties). The mirroring application role is all it holds beyond the
# warehouse; the Snowflake application needs USAGE on the instance it mirrors.
resource "snowflake_account_role" "mirror_operator" {
  name    = "EDGARTOOLS_MIRROR_OPERATOR"
  comment = "Managed Postgres mirrors: create, read back, change; nothing else"
}

resource "snowflake_grant_application_role" "mirror_operator" {
  application_role_name    = "\"SNOWFLAKE\".\"POSTGRES_MIRROR_ADMIN\""
  parent_account_role_name = snowflake_account_role.mirror_operator.name
}

resource "snowflake_grant_privileges_to_account_role" "mirror_operator_warehouse" {
  account_role_name = snowflake_account_role.mirror_operator.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = var.warehouse
  }
}

resource "snowflake_execute" "mirror_instance_usage" {
  execute = "GRANT USAGE ON POSTGRES INSTANCE ${var.postgres_instance} TO APPLICATION SNOWFLAKE"
  revert  = "REVOKE USAGE ON POSTGRES INSTANCE ${var.postgres_instance} FROM APPLICATION SNOWFLAKE"
}

resource "snowflake_service_user" "mirror_operator" {
  name                         = "EDGARTOOLS_MIRROR_OPERATOR"
  default_role                 = snowflake_account_role.mirror_operator.name
  default_warehouse            = var.warehouse
  rsa_public_key               = var.mirror_operator_public_key
  statement_timeout_in_seconds = var.service_statement_timeout_seconds
  comment                      = "Managed Postgres mirrors"
}

resource "snowflake_grant_account_role" "mirror_operator" {
  role_name = snowflake_account_role.mirror_operator.name
  user_name = snowflake_service_user.mirror_operator.name
}


# CREATE_MIRROR refuses a role that does not own the Postgres instance ("does not own the requested postgres instance"), so
# the mirror operator owns it. The grants on it are copied, never revoked, and the administrator holds the operator role, so
# it keeps control of the instance (operator, 2026-11-19: "Fix the permission issue").
resource "snowflake_grant_account_role" "mirror_operator_to_admin" {
  role_name        = snowflake_account_role.mirror_operator.name
  parent_role_name = "ACCOUNTADMIN"
}

resource "snowflake_execute" "mirror_operator_owns_instance" {
  execute    = "GRANT OWNERSHIP ON POSTGRES INSTANCE ${var.postgres_instance} TO ROLE ${snowflake_account_role.mirror_operator.name} COPY CURRENT GRANTS"
  revert     = "GRANT OWNERSHIP ON POSTGRES INSTANCE ${var.postgres_instance} TO ROLE ACCOUNTADMIN COPY CURRENT GRANTS"
  depends_on = [snowflake_grant_account_role.mirror_operator_to_admin]
}

# --- The database owner ---------------------------------------------------------------------------------------------------
# The role named `owner` in rules/snowflake.yaml owns the platform's databases (held by the administrator role, whose grants this root never plans), so the Gold and operations databases
# have a role of their own as owner rather than a person's account. Objects that already exist are imported once (terraform import:
# the role and the ownership), so a plan shows no change.
resource "snowflake_account_role" "owner" {
  name    = local.names.owner
  comment = "Owns the platform's databases (rules/snowflake.yaml owner); held by the administrator role"
}

resource "snowflake_grant_ownership" "gold_database" {
  account_role_name   = snowflake_account_role.owner.name
  outbound_privileges = "COPY"
  on {
    object_type = "DATABASE"
    object_name = local.gold_database
  }
}

resource "snowflake_grant_ownership" "operations_database" {
  account_role_name   = snowflake_account_role.owner.name
  outbound_privileges = "COPY"
  on {
    object_type = "DATABASE"
    object_name = local.names.operations.database
  }
}
