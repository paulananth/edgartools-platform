variable "name" {
  description = "Globally unique storage account name. Must be 3-24 lowercase alphanumeric characters."
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

variable "replication_type" {
  description = "Storage account replication type."
  type        = string
  default     = "LRS"
}

variable "containers" {
  description = "ADLS Gen2 containers used by the warehouse runtime."
  type        = set(string)
  default     = ["bronze", "warehouse", "serving"]
}

variable "tags" {
  description = "Tags applied to Azure resources."
  type        = map(string)
  default     = {}
}
