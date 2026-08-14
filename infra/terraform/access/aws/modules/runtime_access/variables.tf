variable "environment" {
  description = "Environment name."
  type        = string
}

variable "name_prefix" {
  description = "AWS resource name prefix."
  type        = string
}

variable "runner_role_name_prefix" {
  description = <<-EOT
    Prefix for the sec_platform_runner_* IAM role names. Defaults to "sec_platform",
    matching the historical hardcoded names (arg required by deploy-aws-application.sh's
    --execution-role-arn/--task-role-arn/--step-functions-role-arn defaults). IAM role
    names are account-scoped, not environment-scoped by default -- if two environments
    (e.g. dev and a second build) share one AWS account, their runner roles collide on
    this literal name, and because the attached policies are scoped to that environment's
    exact resource ARNs (buckets, secrets), silently reusing one environment's role for
    another produces AccessDenied at runtime, not a plan-time error. Override this to a
    distinct value for any environment sharing an account with another.
  EOT
  type        = string
  default     = "sec_platform"
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

variable "additional_export_prefixes" {
  description = <<-EOT
    Extra bucket-relative prefixes to add to the Snowflake storage-reader
    role's s3:ListBucket/s3:GetObject grants, alongside snowflake_export_prefix.
    This IAM policy is a separate, independently-scoped exact-prefix allowlist
    from Snowflake's own STORAGE_ALLOWED_LOCATIONS on the storage integration
    (see the native_pull module's additional_storage_locations variable for
    that side) -- both must list a new prefix before Snowflake can actually
    read it, confirmed live when silver-snowflake-migration Ticket 07's first
    COPY INTO test failed with ListBucket AccessDenied despite the storage
    integration already being widened. Used by that same ticket to let the
    silver-landing stage (a separate prefix from snowflake_export_prefix)
    share this role instead of provisioning a new one.
  EOT
  type        = list(string)
  default     = []
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
