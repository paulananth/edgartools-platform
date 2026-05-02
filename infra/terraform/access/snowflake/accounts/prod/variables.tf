variable "snowflake_organization_name" {
  description = "Snowflake organization name used by the Terraform provider."
  type        = string
}

variable "snowflake_account_name" {
  description = "Snowflake account name used by the Terraform provider."
  type        = string
}

variable "snowflake_user" {
  description = "Snowflake user used by the Terraform provider."
  type        = string
}

variable "snowflake_password" {
  description = "Optional Snowflake password. Leave null when using browser-based auth."
  type        = string
  default     = null
  sensitive   = true
}

variable "snowflake_authenticator" {
  description = "Snowflake authenticator for Terraform sessions."
  type        = string
  default     = "externalbrowser"
}

variable "snowflake_admin_role" {
  description = "Snowflake administrative role used by Terraform."
  type        = string
  default     = "ACCOUNTADMIN"
}

variable "provisioning_state_bucket" {
  description = "S3 bucket containing Snowflake provisioning Terraform state."
  type        = string
}

variable "provisioning_state_key" {
  description = "S3 key for Snowflake provisioning Terraform state."
  type        = string
  default     = "snowflake/prod/terraform.tfstate"
}

variable "provisioning_state_region" {
  description = "AWS region for the Snowflake provisioning Terraform state bucket."
  type        = string
  default     = "us-east-1"
}

variable "grant_roles_to_admin" {
  description = "Whether to grant the baseline roles to the parent admin role."
  type        = bool
  default     = true
}

variable "parent_admin_role_name" {
  description = "Administrative account role that should inherit the baseline roles."
  type        = string
  default     = "SYSADMIN"
}
