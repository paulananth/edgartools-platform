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
  default     = "edgartools-prod"
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

variable "mdm_sql_database_sku_name" {
  description = "Azure SQL database SKU for MDM."
  type        = string
  default     = "S0"
}

variable "mdm_sql_aad_admin_login_username" {
  description = "Login username for the Azure SQL Entra administrator."
  type        = string
  default     = "terraform-deployer"
}

variable "mdm_sql_aad_admin_object_id" {
  description = "Optional object ID for the Azure SQL Entra administrator. Defaults to the current Terraform principal."
  type        = string
  default     = null
}

variable "mdm_sql_database_max_size_gb" {
  description = "Azure SQL database max size in GB for MDM."
  type        = number
  default     = 10
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

variable "tags" {
  description = "Tags applied to Azure resources."
  type        = map(string)
  default     = {}
}
