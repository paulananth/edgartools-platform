variable "environment" {
  description = "Deployment environment name, for example dev or prod."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for Container Apps resources."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group name."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "container_image" {
  description = "Warehouse container image reference, usually an ACR digest or immutable tag."
  type        = string
}

variable "acr_id" {
  description = "Azure Container Registry resource ID."
  type        = string
}

variable "acr_login_server" {
  description = "Azure Container Registry login server."
  type        = string
}

variable "storage_account_id" {
  description = "ADLS Gen2 storage account ID."
  type        = string
}

variable "warehouse_bronze_root" {
  description = "WAREHOUSE_BRONZE_ROOT value."
  type        = string
}

variable "warehouse_storage_root" {
  description = "WAREHOUSE_STORAGE_ROOT value."
  type        = string
}

variable "serving_export_root" {
  description = "SERVING_EXPORT_ROOT value."
  type        = string
}

variable "key_vault_id" {
  description = "Key Vault ID that stores runtime secrets."
  type        = string
}

variable "tenant_id" {
  description = "Azure tenant ID used for Key Vault access policies."
  type        = string
}

variable "edgar_identity_secret_uri" {
  description = "Versionless Key Vault secret URI for the SEC EDGAR User-Agent identity."
  type        = string
}

variable "warehouse_runtime_mode" {
  description = "WAREHOUSE_RUNTIME_MODE for jobs."
  type        = string
  default     = "infrastructure_validation"
}

variable "workflows" {
  description = "Container Apps Jobs to create."
  type = map(object({
    command     = list(string)
    cpu         = number
    memory      = string
    schedule    = optional(string)
    parallelism = optional(number, 1)
  }))
}

variable "tags" {
  description = "Tags applied to Azure resources."
  type        = map(string)
  default     = {}
}
