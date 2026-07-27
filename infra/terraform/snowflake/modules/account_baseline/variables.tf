variable "environment" {
  description = "Environment label used in comments and object naming."
  type        = string
}

variable "database_name" {
  description = "Snowflake database name."
  type        = string
}

variable "source_schema_name" {
  description = "Schema for internal Snowflake source objects."
  type        = string
}

variable "gold_schema_name" {
  description = "Schema for business-facing gold objects."
  type        = string
}

variable "deployer_role_name" {
  description = "Role used for Terraform and dbt deployment."
  type        = string
}

variable "loader_role_name" {
  description = "Role that owns the EDGARTOOLS_GOLD dynamic tables and manifest-pipeline procedures, and executes the post-load Snowflake refresh runtime."
  type        = string
}

variable "reader_role_name" {
  description = "Role used by business readers."
  type        = string
}

variable "dashboard_owner_role_name" {
  description = "GH-247: least-privilege role that owns the Streamlit-in-Snowflake dashboard object and its source stage. Deliberately distinct from reader (viewer access) and deployer/loader (data-plane roles) -- has no direct SELECT on gold/decision/status data; the dashboard runs under Caller's Rights, so the viewer's own role grants (reader) are what govern query access, not the owner's."
  type        = string
}

variable "refresh_warehouse_name" {
  description = "Warehouse used for Snowflake refresh workloads."
  type        = string
}

variable "reader_warehouse_name" {
  description = "Warehouse used for business-reader queries."
  type        = string
}

variable "refresh_warehouse_size" {
  description = "Snowflake size for the refresh warehouse."
  type        = string
  default     = "XSMALL"
}

variable "reader_warehouse_size" {
  description = "Snowflake size for the reader warehouse."
  type        = string
  default     = "XSMALL"
}

variable "warehouse_auto_suspend_seconds" {
  description = "Auto suspend timeout for created warehouses."
  type        = number
  default     = 60
}

variable "data_retention_time_in_days" {
  description = "Database and schema time travel retention."
  type        = number
  default     = 1
}

variable "grant_roles_to_admin" {
  description = "Whether to grant the baseline roles to the parent admin role."
  type        = bool
  default     = true
}

variable "parent_admin_role_name" {
  description = "Administrative account role that should inherit the baseline roles."
  type        = string
  default     = "SYSADMIN"
}
