variable "aws_region" {
  description = "AWS region for the prod account."
  type        = string
  default     = "us-east-1"
}

variable "provisioning_state_bucket" {
  description = "S3 bucket containing the AWS provisioning Terraform state."
  type        = string
}

variable "provisioning_state_key" {
  description = "S3 key for the AWS provisioning Terraform state."
  type        = string
  default     = "accounts/prod/terraform.tfstate"
}

variable "provisioning_state_region" {
  description = "AWS region for the AWS provisioning Terraform state bucket."
  type        = string
  default     = "us-east-1"
}

variable "snowflake_state_bucket" {
  description = "Optional S3 bucket containing Snowflake provisioning Terraform state."
  type        = string
  default     = null
}

variable "snowflake_state_key" {
  description = "S3 key for the Snowflake provisioning Terraform state."
  type        = string
  default     = "snowflake/prod/terraform.tfstate"
}

variable "snowflake_state_region" {
  description = "AWS region for the Snowflake provisioning Terraform state bucket."
  type        = string
  default     = "us-east-1"
}

variable "snowflake_manifest_subscriber_arn" {
  description = "Optional Snowflake-managed AWS principal ARN. Overrides Snowflake remote-state discovery."
  type        = string
  default     = null
}

variable "snowflake_bootstrap_enabled" {
  description = "Whether to use temporary bootstrap trust before Snowflake emits its AWS principal."
  type        = bool
  default     = false
}

variable "snowflake_storage_external_id" {
  description = "Optional Snowflake storage external ID. Defaults to the deterministic environment value."
  type        = string
  default     = null
}

variable "tags" {
  description = "Additional tags applied to prod access-control resources."
  type        = map(string)
  default     = {}
}
