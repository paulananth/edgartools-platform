variable "environment" {
  description = "Environment name."
  type        = string
}

variable "snowflake_export_bucket_name" {
  description = "Dedicated Snowflake export bucket name."
  type        = string
}

variable "edgar_identity_secret_arn" {
  description = "Optional pre-existing EDGAR identity secret ARN."
  type        = string
  default     = null
}

variable "ecr_force_delete" {
  description = "Whether Terraform may delete the ECR repository even if images remain."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags applied to runtime resources."
  type        = map(string)
  default     = {}
}
