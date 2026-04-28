variable "environment" {
  description = "Deployment environment."
  type        = string
}

variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
}

variable "resource_group_name" {
  description = "Azure resource group name."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "sql_location" {
  description = "Azure region for Azure SQL. Defaults to the resource group's location."
  type        = string
  default     = null
}

variable "key_vault_id" {
  description = "Key Vault ID where MDM secrets are stored."
  type        = string
}

variable "container_app_environment_id" {
  description = "Container Apps environment ID for Neo4j."
  type        = string
}

variable "container_image" {
  description = "MDM-capable container image reference."
  type        = string
}

variable "acr_login_server" {
  description = "ACR login server for pulling the MDM-capable image."
  type        = string
}

variable "workload_identity_id" {
  description = "User-assigned managed identity resource ID used by MDM apps/jobs."
  type        = string
}

variable "workload_identity_client_id" {
  description = "User-assigned managed identity client ID used by Azure SDKs in MDM workloads."
  type        = string
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

variable "sql_admin_username" {
  description = "Azure SQL administrator username."
  type        = string
  default     = "mdmadmin"
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
  description = "Allow Azure services to reach Azure SQL. Required for public Container Apps unless private networking is added."
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
  description = "Globally unique storage account name for Neo4j Azure Files persistence."
  type        = string
}

variable "neo4j_image" {
  description = "Neo4j container image."
  type        = string
  default     = "neo4j:5-community"
}

variable "neo4j_user" {
  description = "Neo4j username."
  type        = string
  default     = "neo4j"
}

variable "neo4j_cpu" {
  description = "Neo4j Container App CPU."
  type        = number
  default     = 2
}

variable "neo4j_memory" {
  description = "Neo4j Container App memory."
  type        = string
  default     = "4Gi"
}

variable "neo4j_external_enabled" {
  description = "Expose Neo4j Bolt ingress externally."
  type        = bool
  default     = false
}

variable "neo4j_min_replicas" {
  description = "Minimum Neo4j replicas."
  type        = number
  default     = 1
}

variable "neo4j_max_replicas" {
  description = "Maximum Neo4j replicas. Keep at 1 for single-node Neo4j."
  type        = number
  default     = 1
}

variable "api_keys" {
  description = "MDM API X-API-Key values. A generated key is used when empty."
  type        = list(string)
  default     = []
  sensitive   = true
}

variable "mdm_silver_duckdb_path" {
  description = "Optional MDM_SILVER_DUCKDB value for MDM run jobs."
  type        = string
  default     = null
}

variable "mdm_run_limit" {
  description = "Optional --limit N passed to `mdm run`. 0 = no limit (production default)."
  type        = number
  default     = 0
}

variable "mdm_api_external_enabled" {
  description = "Expose the MDM FastAPI app externally."
  type        = bool
  default     = false
}

variable "mdm_api_min_replicas" {
  description = "Minimum MDM API replicas."
  type        = number
  default     = 1
}

variable "mdm_api_max_replicas" {
  description = "Maximum MDM API replicas."
  type        = number
  default     = 3
}

variable "mdm_api_cpu" {
  description = "MDM API container CPU."
  type        = number
  default     = 1
}

variable "mdm_api_memory" {
  description = "MDM API container memory."
  type        = string
  default     = "2Gi"
}

variable "tags" {
  description = "Tags applied to Azure resources."
  type        = map(string)
  default     = {}
}
