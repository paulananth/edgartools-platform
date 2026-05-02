variable "name_prefix" {
  description = "Azure resource name prefix."
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

variable "tenant_id" {
  description = "Azure tenant ID."
  type        = string
}

variable "acr_id" {
  description = "Azure Container Registry resource ID."
  type        = string
}

variable "storage_account_id" {
  description = "ADLS Gen2 storage account resource ID."
  type        = string
}

variable "key_vault_id" {
  description = "Key Vault resource ID."
  type        = string
}

variable "operator_object_ids" {
  description = "Operator/deployer object IDs that can manage runtime Key Vault secrets."
  type        = set(string)
  default     = []
}

variable "operator_secret_permissions" {
  description = "Key Vault secret permissions granted to operators."
  type        = list(string)
  default     = ["Get", "List", "Set", "Delete", "Purge", "Recover"]
}

variable "runtime_secret_permissions" {
  description = "Key Vault secret permissions granted to runtime jobs."
  type        = list(string)
  default     = ["Get"]
}

variable "tags" {
  description = "Tags applied to Azure access resources."
  type        = map(string)
  default     = {}
}
