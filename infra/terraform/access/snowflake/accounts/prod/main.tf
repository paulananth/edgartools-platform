# The access controls the audit (skills/access-audit) tests, as code: read-only roles and their key-pair service users,
# the cost and timeout guards, and the credential policies. Changes go through plan, a recorded approval, apply, re-audit.


# --- Credential policies: values and home in rules/snowflake_policy.yaml ----------------------------------------------
# A policy is a schema-level object, so it needs a schema; it lives in one of the Gold database's (rules/snowflake.yaml), and
# no database is created for it. The access audit (control POL) reads the live policies back against the same file.
locals {
  policy        = yamldecode(file("${path.module}/../../../../../../rules/snowflake_policy.yaml"))
  names         = yamldecode(file("${path.module}/../../../../../../rules/snowflake.yaml"))
  gold_database = local.names[local.policy.location.database_of].database
}

resource "snowflake_schema" "policies" {
  database = local.gold_database
  name     = local.policy.location.schema
}

resource "snowflake_password_policy" "standard" {
  database             = local.gold_database
  schema               = snowflake_schema.policies.name
  name                 = local.policy.password.name
  min_length           = local.policy.password.min_length
  min_upper_case_chars = local.policy.password.min_upper_case_chars
  min_lower_case_chars = local.policy.password.min_lower_case_chars
  min_numeric_chars    = local.policy.password.min_numeric_chars
  min_special_chars    = local.policy.password.min_special_chars
  max_age_days         = local.policy.password.max_age_days
  max_retries          = local.policy.password.max_retries
  lockout_time_mins    = local.policy.password.lockout_time_mins
  history              = local.policy.password.history
  comment              = "Values in rules/snowflake_policy.yaml"
}

resource "snowflake_account_password_policy_attachment" "standard" {
  password_policy = snowflake_password_policy.standard.fully_qualified_name
}

resource "snowflake_authentication_policy" "service_keypair_only" {
  database               = local.gold_database
  schema                 = snowflake_schema.policies.name
  name                   = local.policy.authentication.name
  authentication_methods = local.policy.authentication.methods
  comment                = "Values in rules/snowflake_policy.yaml"
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

resource "snowflake_user_authentication_policy_attachment" "log_reader" {
  user_name                  = snowflake_service_user.log_reader.name
  authentication_policy_name = snowflake_authentication_policy.service_keypair_only.fully_qualified_name
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

resource "snowflake_user_authentication_policy_attachment" "auditor" {
  user_name                  = snowflake_service_user.auditor.name
  authentication_policy_name = snowflake_authentication_policy.service_keypair_only.fully_qualified_name
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

resource "snowflake_user_authentication_policy_attachment" "mirror_operator" {
  user_name                  = snowflake_service_user.mirror_operator.name
  authentication_policy_name = snowflake_authentication_policy.service_keypair_only.fully_qualified_name
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

# --- Policy reader for the audit -------------------------------------------------------------------------------------------
# A role can DESCRIBE a policy only with a privilege on it, and the one that allows that (APPLY) also lets it attach the policy.
# So the audit reads through this owner's-rights procedure, which returns the policies' properties and changes nothing; the
# auditor holds USAGE on the procedure only. Same JSON shape for any platform's reader: {"password": [...], "authentication": [...]}.
resource "snowflake_procedure_javascript" "audit_credential_policies" {
  database            = local.gold_database
  schema              = "CONTROL"
  name                = "AUDIT_CREDENTIAL_POLICIES"
  execute_as          = "OWNER"
  return_type         = "VARCHAR"
  procedure_definition = <<-JS
    const out = {password: [], authentication: []};
    for (const kind of ["password", "authentication"]) {
      const listed = snowflake.execute({sqlText: "show " + kind + " policies in account"});
      const rows = [];
      while (listed.next()) rows.push({db: listed.getColumnValue("database_name"), sc: listed.getColumnValue("schema_name"), name: listed.getColumnValue("name")});
      for (const r of rows) {
        const d = snowflake.execute({sqlText: "describe " + kind + " policy \"" + r.db + "\".\"" + r.sc + "\".\"" + r.name + "\""});
        const properties = {};
        while (d.next()) properties[String(d.getColumnValue("property")).toLowerCase()] = String(d.getColumnValue("value"));
        out[kind].push({database_name: r.db, schema_name: r.sc, name: r.name, properties: properties});
      }
    }
    return JSON.stringify(out);
  JS
}

resource "snowflake_grant_privileges_to_account_role" "auditor_policy_reader" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_schema_object {
    object_type = "PROCEDURE"
    object_name = "${local.gold_database}.CONTROL.AUDIT_CREDENTIAL_POLICIES()"
  }
}

# --- The database owner ---------------------------------------------------------------------------------------------------
# The role named `owner` in rules/snowflake.yaml owns the platform's databases and is held by ACCOUNTADMIN, so the Gold database
# has a role of its own as owner rather than a person's account. Created by hand before this root existed: the next access apply
# imports the role, the grant of the role and the ownership first (terraform import), so a plan shows no change.
resource "snowflake_account_role" "owner" {
  name    = local.names.owner
  comment = "Owns the platform's databases (rules/snowflake.yaml owner); held by ACCOUNTADMIN"
}

resource "snowflake_grant_account_role" "owner_held_by_admin" {
  role_name        = snowflake_account_role.owner.name
  parent_role_name = "ACCOUNTADMIN"
}

resource "snowflake_grant_ownership" "gold_database" {
  account_role_name   = snowflake_account_role.owner.name
  outbound_privileges = "COPY"
  on {
    object_type = "DATABASE"
    object_name = local.gold_database
  }
}
