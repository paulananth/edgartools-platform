variable "environment" {
  type        = string
  description = "Deployment environment (e.g. prod, dev)."
}

variable "name_prefix" {
  type        = string
  description = "Prefix for AWS resource names."
}

variable "vpc_id" {
  type        = string
  description = "ID of the VPC where RDS will live."
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block of the VPC (used for security group egress scoping)."
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks for the MDM private subnets (one per AZ)."
}

variable "availability_zones" {
  type        = list(string)
  description = "Availability zones for the private subnets."
}

variable "ecs_security_group_id" {
  type        = string
  description = "Security group ID of ECS tasks that need to reach PostgreSQL."
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class."
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  type        = number
  description = "Allocated storage in GB."
  default     = 20
}

variable "db_engine_version" {
  type        = string
  description = "Optional PostgreSQL engine version. When null, RDS selects the current default version for the region."
  default     = null
  nullable    = true
}

variable "db_name" {
  type        = string
  description = "Initial database name."
  default     = "mdm"
}

variable "db_master_username" {
  type        = string
  description = "Master DB username."
  default     = "mdm_admin"
}

variable "tags" {
  type        = map(string)
  description = "Common resource tags."
  default     = {}
}
