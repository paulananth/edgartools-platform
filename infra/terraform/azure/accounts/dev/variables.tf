variable "location" {
  description = "Azure region."
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Optional resource group name override."
  type        = string
  default     = null
}

variable "name_prefix" {
  description = "Azure resource name prefix."
  type        = string
  default     = "edgartools-dev"
}

variable "storage_account_name" {
  description = "Globally unique ADLS Gen2 account name."
  type        = string
}

variable "container_registry_name" {
  description = "Globally unique Azure Container Registry name."
  type        = string
}

variable "key_vault_name" {
  description = "Globally unique Azure Key Vault name."
  type        = string
}

variable "transform_container_image" {
  description = "edgar-warehouse-pipelines image reference in ACR (warehouse ETL jobs)."
  type        = string
}

variable "mdm_container_image" {
  description = "edgar-warehouse-mdm-neo4j image reference in ACR (MDM pipeline + API)."
  type        = string
}

variable "warehouse_runtime_mode" {
  description = "WAREHOUSE_RUNTIME_MODE for Container Apps Jobs."
  type        = string
  default     = "infrastructure_validation"
}

variable "daily_incremental_schedule" {
  description = "Optional cron expression for daily incremental Container Apps Job."
  type        = string
  default     = null
}

variable "databricks_workspace_name" {
  description = "Optional Databricks workspace name."
  type        = string
  default     = null
}

variable "enable_mdm" {
  description = "Provision Azure MDM data-plane resources."
  type        = bool
  default     = false
}

variable "mdm_sql_server_name" {
  description = "Globally unique Azure SQL logical server name for MDM."
  type        = string
  default     = null
}

variable "mdm_sql_location" {
  description = "Azure region for MDM Azure SQL. Defaults to the resource group's location."
  type        = string
  default     = null
}

variable "mdm_sql_database_name" {
  description = "Azure SQL database name for MDM."
  type        = string
  default     = "mdm"
}

variable "mdm_sql_admin_username" {
  description = "Azure SQL administrator username for MDM."
  type        = string
  default     = "mdmadmin"
}

variable "mdm_sql_database_sku_name" {
  description = "Azure SQL database SKU for MDM."
  type        = string
  default     = "Basic"
}

variable "mdm_sql_database_max_size_gb" {
  description = "Azure SQL database max size in GB for MDM."
  type        = number
  default     = 2
}

variable "mdm_sql_firewall_rules" {
  description = "Optional MDM Azure SQL firewall rules keyed by rule name."
  type = map(object({
    start_ip_address = string
    end_ip_address   = string
  }))
  default = {}
}

variable "mdm_neo4j_storage_account_name" {
  description = "Globally unique storage account name for Neo4j Azure Files persistence."
  type        = string
  default     = null
}

variable "mdm_neo4j_external_enabled" {
  description = "Expose Neo4j Bolt ingress externally."
  type        = bool
  default     = false
}

variable "mdm_api_external_enabled" {
  description = "Expose the MDM FastAPI app externally."
  type        = bool
  default     = false
}

variable "mdm_silver_duckdb_path" {
  description = "Optional MDM_SILVER_DUCKDB value for MDM run jobs."
  type        = string
  default     = null
}

variable "mdm_api_keys" {
  description = "Initial MDM API keys. A generated key is used when empty."
  type        = list(string)
  default     = []
  sensitive   = true
}

variable "tags" {
  description = "Tags applied to Azure resources."
  type        = map(string)
  default     = {}
}
