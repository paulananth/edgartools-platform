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

variable "role_names" {
  description = "Role names keyed by deployer, refresher, and reader."
  type = object({
    deployer  = string
    refresher = string
    reader    = string
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
