variable "environment" {
  description = "Environment name (e.g. dev, prod)."
  type        = string
}

variable "database_name" {
  description = "Snowflake database that owns the dashboard schema."
  type        = string
}

variable "gold_schema_name" {
  description = "Gold schema the dashboard reads from (for grants)."
  type        = string
}

variable "reader_role_name" {
  description = "Account role the dashboard runs as; must already have SELECT on the gold schema."
  type        = string
}

variable "reader_warehouse_name" {
  description = "Warehouse the Streamlit app uses for queries."
  type        = string
}

variable "dashboard_schema_name" {
  description = "Schema that owns the Streamlit app + its source stage."
  type        = string
  default     = "EDGARTOOLS_DASHBOARD"
}

variable "stage_name" {
  description = "Name of the internal stage that holds the Streamlit source files."
  type        = string
  default     = "DASHBOARD_SRC"
}

variable "streamlit_name" {
  description = "Name of the Streamlit app object."
  type        = string
  default     = "EDGARTOOLS_DASHBOARD"
}

variable "streamlit_main_file" {
  description = "Main Python file of the Streamlit app, relative to the stage root."
  type        = string
  default     = "streamlit_app.py"
}

variable "streamlit_title" {
  description = "Display title shown in Snowsight."
  type        = string
  default     = "EdgarTools Warehouse Dashboard"
}
