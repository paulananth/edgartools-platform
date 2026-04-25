variable "aws_region" {
  description = "AWS region for the prod account."
  type        = string
  default     = "us-east-1"
}

variable "container_image" {
  description = "Warehouse container image tag or digest."
  type        = string
  default     = null
}

variable "warehouse_runtime_mode" {
  description = "Canonical warehouse runtime mode for the prod ECS warehouse task."
  type        = string
  default     = "infrastructure_validation"
}

variable "warehouse_bronze_cik_limit" {
  description = "Optional bounded-validation cap for daily bronze submissions capture in prod."
  type        = number
  default     = null
}

variable "bronze_bucket_name" {
  description = "Optional override for the bronze bucket name."
  type        = string
  default     = null
}

variable "warehouse_bucket_name" {
  description = "Optional override for the warehouse bucket name."
  type        = string
  default     = null
}

variable "snowflake_export_bucket_name" {
  description = "Optional override for the Snowflake export bucket name."
  type        = string
  default     = null
}

variable "edgar_identity_secret_arn" {
  description = "Optional pre-existing EDGAR identity secret ARN."
  type        = string
  default     = null
}

variable "edgar_identity_value" {
  description = "EDGAR identity string to store in Secrets Manager (e.g. 'MyApp admin@example.com')."
  type        = string
  sensitive   = true
  default     = null
}

variable "snowflake_manifest_subscriber_arn" {
  description = "Optional Snowflake-managed AWS principal ARN allowed to subscribe to the manifest SNS topic for Snowpipe auto-ingest."
  type        = string
  default     = null
}

variable "snowflake_bootstrap_enabled" {
  description = "Whether to use temporary bootstrap trust for the Snowflake export reader role."
  type        = bool
  default     = false
}

variable "snowflake_storage_external_id" {
  description = "Optional external ID that Snowflake must present when assuming the Snowflake S3 reader role."
  type        = string
  default     = null
}

variable "vpc_cidr" {
  description = "CIDR block for the prod VPC."
  type        = string
  default     = "10.30.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks for prod."
  type        = list(string)
  default     = ["10.30.0.0/24", "10.30.1.0/24"]
}

variable "availability_zones" {
  description = "Availability zones for the prod public subnets."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "daily_incremental_schedule" {
  description = "Schedule for daily incremental runs."
  type        = string
  default     = "cron(30 6 ? * MON-FRI *)"
}

variable "full_reconcile_schedule" {
  description = "Schedule for full reconcile runs."
  type        = string
  default     = "cron(0 9 ? * SAT *)"
}

variable "schedule_timezone" {
  description = "Timezone for scheduled workflows."
  type        = string
  default     = "America/New_York"
}

variable "task_profiles" {
  description = "CPU and memory settings per ECS task profile."
  type = map(object({
    cpu    = number
    memory = number
  }))
  default = {}
}

variable "task_profile_by_workflow" {
  description = "Task profile name for each workflow."
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Additional tags applied to prod resources."
  type        = map(string)
  default     = {}
}

variable "mdm_enabled" {
  description = "Whether to provision the MDM RDS + Secrets Manager stack."
  type        = bool
  default     = false
}

variable "mdm_private_subnet_cidrs" {
  description = "CIDR blocks for the MDM private subnets (one per AZ)."
  type        = list(string)
  default     = []
}

variable "mdm_db_instance_class" {
  description = "RDS instance class for the MDM database."
  type        = string
  default     = "db.t3.micro"
}

variable "mdm_neo4j_uri" {
  description = "Neo4j AuraDB Bolt URI. Stored in Secrets Manager."
  type        = string
  default     = ""
}

variable "mdm_neo4j_user" {
  description = "Neo4j AuraDB username. Stored in Secrets Manager."
  type        = string
  default     = ""
}

variable "mdm_neo4j_password" {
  description = "Neo4j AuraDB password. Stored in Secrets Manager."
  type        = string
  default     = ""
  sensitive   = true
}

variable "mdm_api_keys" {
  description = "Initial API keys for the MDM REST API. Stored in Secrets Manager."
  type        = list(string)
  default     = []
  sensitive   = true
}
