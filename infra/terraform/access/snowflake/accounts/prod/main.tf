# The access controls the audit (skills/access-audit) tests, as code: read-only roles and their key-pair service users,
# the cost and timeout guards, and the credential policies. Changes go through plan, a recorded approval, apply, re-audit.


# --- Policies live in their own database -----------------------------------------------------------------------------
resource "snowflake_database" "governance" {
  name    = "EDGARTOOLS_GOVERNANCE"
  comment = "Account-level policies: password, authentication"
}

resource "snowflake_schema" "policies" {
  database = snowflake_database.governance.name
  name     = "POLICIES"
}

resource "snowflake_password_policy" "standard" {
  database             = snowflake_database.governance.name
  schema               = snowflake_schema.policies.name
  name                 = "EDGARTOOLS_PASSWORD_POLICY"
  min_length           = 14
  min_upper_case_chars = 1
  min_lower_case_chars = 1
  min_numeric_chars    = 1
  min_special_chars    = 1
  max_age_days         = 0
  max_retries          = 5
  lockout_time_mins    = 15
  history              = 5
  comment              = "Standard for any password that exists; max age is set once the human admin password is gone"
}

resource "snowflake_account_password_policy_attachment" "standard" {
  password_policy = snowflake_password_policy.standard.fully_qualified_name
}

resource "snowflake_authentication_policy" "service_keypair_only" {
  database               = snowflake_database.governance.name
  schema                 = snowflake_schema.policies.name
  name                   = "EDGARTOOLS_SERVICE_KEYPAIR_ONLY"
  authentication_methods = ["KEYPAIR"]
  comment                = "Service users sign in with a key pair only"
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
variable "gold_database" {
  type    = string
  default = "DB_EDGARTOOLS_GOLD"
}

resource "snowflake_grant_privileges_to_account_role" "auditor_gold_database" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = var.gold_database
  }
}

resource "snowflake_grant_privileges_to_account_role" "auditor_gold_schemas" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_schema {
    all_schemas_in_database = var.gold_database
  }
}

resource "snowflake_grant_privileges_to_account_role" "auditor_gold_future_schemas" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = var.gold_database
  }
}

resource "snowflake_grant_privileges_to_account_role" "auditor_gold_tables" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["REFERENCES"]
  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_database        = var.gold_database
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "auditor_gold_future_tables" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["REFERENCES"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = var.gold_database
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
