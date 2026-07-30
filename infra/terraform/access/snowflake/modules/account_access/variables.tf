variable "environment" {
  description = "Environment label used in comments."
  type        = string
}

variable "database_name" {
  description = "Snowflake database name."
  type        = string
}

variable "source_schema_name" {
  description = "Source schema name."
  type        = string
}

variable "gold_schema_name" {
  description = "Gold schema name."
  type        = string
}

variable "decision_schema_name" {
  description = "GH-247/GH-246: Decision Contract schema name. Not provisioned by account_baseline (created ad hoc by infra/snowflake/sql/decision_contract/*.sql) -- referenced here by name only, same pattern as other object-level grants this module doesn't own the lifecycle of."
  type        = string
  default     = "EDGARTOOLS_DECISION"
}

variable "role_names" {
  description = "Role names keyed by deployer, loader, reader, and dashboard_owner."
  type = object({
    deployer        = string
    loader          = string
    reader          = string
    dashboard_owner = string
  })
}

variable "warehouse_names" {
  description = "Warehouse names keyed by refresh and reader."
  type = object({
    refresh = string
    reader  = string
  })
}

variable "dashboard_schema_name" {
  description = "Dashboard schema name."
  type        = string
}

variable "dashboard_streamlit_qualified_name" {
  description = "Fully qualified dashboard Streamlit object name."
  type        = string
}

variable "dashboard_stage_qualified_name" {
  description = "Fully qualified internal stage holding the dashboard release."
  type        = string
}

variable "grant_roles_to_admin" {
  description = "Whether to grant managed roles to the parent admin role."
  type        = bool
  default     = true
}

variable "parent_admin_role_name" {
  description = "Administrative account role that should inherit the managed roles."
  type        = string
  default     = "SYSADMIN"
}
