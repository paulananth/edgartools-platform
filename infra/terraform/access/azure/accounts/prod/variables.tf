variable "provisioning_state_resource_group_name" {
  description = "Azure resource group containing the provisioning Terraform state account."
  type        = string
}

variable "provisioning_state_storage_account_name" {
  description = "Azure Storage account containing the provisioning Terraform state."
  type        = string
}

variable "provisioning_state_container_name" {
  description = "Blob container containing the provisioning Terraform state."
  type        = string
  default     = "tfstate"
}

variable "provisioning_state_key" {
  description = "Blob key for the Azure provisioning Terraform state."
  type        = string
  default     = "azure/prod/terraform.tfstate"
}

variable "name_prefix" {
  description = "Azure resource name prefix."
  type        = string
  default     = "edgartools-prod"
}

variable "operator_object_ids" {
  description = "Optional operator/deployer object IDs. Defaults to the current Terraform principal."
  type        = set(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to Azure access resources."
  type        = map(string)
  default     = {}
}
