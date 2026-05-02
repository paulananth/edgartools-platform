variable "resource_group_name" {
  description = "Azure resource group name."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "tenant_id" {
  description = "Azure tenant ID for the SQL Entra administrator."
  type        = string
}

variable "sql_location" {
  description = "Azure region for Azure SQL. Defaults to the resource group's location."
  type        = string
  default     = null
}

variable "sql_server_name" {
  description = "Globally unique Azure SQL logical server name."
  type        = string
}

variable "sql_database_name" {
  description = "Azure SQL database name for MDM."
  type        = string
  default     = "mdm"
}

variable "sql_aad_admin_login_username" {
  description = "Login username for the Azure SQL Entra administrator."
  type        = string
}

variable "sql_aad_admin_object_id" {
  description = "Object ID for the Azure SQL Entra administrator."
  type        = string
}

variable "sql_database_sku_name" {
  description = "Azure SQL database SKU."
  type        = string
  default     = "Basic"
}

variable "sql_database_max_size_gb" {
  description = "Azure SQL database max size in GB."
  type        = number
  default     = 2
}

variable "sql_public_network_access_enabled" {
  description = "Whether public network access is enabled for Azure SQL."
  type        = bool
  default     = true
}

variable "sql_allow_azure_services" {
  description = "Allow Azure services to reach Azure SQL."
  type        = bool
  default     = true
}

variable "sql_firewall_rules" {
  description = "Optional Azure SQL firewall rules keyed by rule name."
  type = map(object({
    start_ip_address = string
    end_ip_address   = string
  }))
  default = {}
}

variable "neo4j_storage_account_name" {
  description = "Globally unique storage account name for the Neo4j data share shell."
  type        = string
}

variable "tags" {
  description = "Tags applied to Azure resources."
  type        = map(string)
  default     = {}
}
