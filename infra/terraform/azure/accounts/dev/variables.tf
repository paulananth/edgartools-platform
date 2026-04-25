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

variable "container_image" {
  description = "Warehouse image reference in ACR."
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

variable "tags" {
  description = "Tags applied to Azure resources."
  type        = map(string)
  default     = {}
}
