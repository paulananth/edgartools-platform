variable "environment" {
  description = "Environment name (dev, prod)."
  type        = string
}

variable "name_prefix" {
  description = "Resource name prefix, e.g. edgartools-dev."
  type        = string
}

variable "github_org" {
  description = "GitHub organisation or user that owns the repository."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name (without org prefix)."
  type        = string
}

variable "ecr_name_prefix" {
  description = "ECR repository name prefix. All repos matching '<prefix>*' receive push permission."
  type        = string
}

variable "tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default     = {}
}
