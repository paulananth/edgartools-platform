variable "aws_region" {
  description = "AWS region for the dev account."
  type        = string
  default     = "us-east-1"
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

variable "vpc_cidr" {
  description = "CIDR block for the dev VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks for dev."
  type        = list(string)
  default     = ["10.20.0.0/24", "10.20.1.0/24"]
}

variable "availability_zones" {
  description = "Availability zones for the dev public subnets."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "tags" {
  description = "Additional tags applied to dev resources."
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
  default     = ["10.20.10.0/24", "10.20.11.0/24"]
}

variable "mdm_db_instance_class" {
  description = "RDS instance class for the MDM database."
  type        = string
  default     = "db.t3.micro"
}

variable "mdm_db_engine_version" {
  description = "Optional RDS PostgreSQL engine version for MDM. Null lets RDS choose the current regional default."
  type        = string
  default     = null
  nullable    = true
}
