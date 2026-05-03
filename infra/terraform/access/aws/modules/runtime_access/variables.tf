variable "environment" {
  description = "Environment name."
  type        = string
}

variable "name_prefix" {
  description = "AWS resource name prefix."
  type        = string
}

variable "bronze_bucket_name" {
  description = "Bronze bucket name."
  type        = string
}

variable "bronze_bucket_arn" {
  description = "Bronze bucket ARN."
  type        = string
}

variable "warehouse_bucket_arn" {
  description = "Warehouse bucket ARN."
  type        = string
}

variable "snowflake_export_bucket_arn" {
  description = "Snowflake export bucket ARN."
  type        = string
}

variable "snowflake_export_kms_key_arn" {
  description = "KMS key ARN for Snowflake export artifacts."
  type        = string
}

variable "snowflake_export_prefix" {
  description = "Bucket-relative Snowflake export prefix."
  type        = string
}

variable "snowflake_manifest_sns_topic_arn" {
  description = "SNS topic ARN for Snowflake export manifest notifications."
  type        = string
}

variable "edgar_identity_secret_arn" {
  description = "EDGAR identity secret ARN read by ECS task execution."
  type        = string
}

variable "mdm_secret_arns" {
  description = "Optional MDM runtime secret ARNs readable by ECS task execution."
  type        = list(string)
  default     = []
}

variable "snowflake_manifest_subscriber_arn" {
  description = "Optional Snowflake-managed AWS principal ARN allowed to subscribe to manifest notifications and assume the storage role."
  type        = string
  default     = null
}

variable "snowflake_bootstrap_enabled" {
  description = "Whether to use temporary bootstrap trust before Snowflake emits its AWS principal."
  type        = bool
  default     = false
}

variable "snowflake_storage_external_id" {
  description = "External ID Snowflake must present when assuming the export-reader role."
  type        = string
}

variable "tags" {
  description = "Additional tags applied to access-control resources."
  type        = map(string)
  default     = {}
}
