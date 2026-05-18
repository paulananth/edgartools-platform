variable "environment" {
  description = "Deployment environment (e.g. dev, prod)."
  type        = string
}

variable "name_prefix" {
  description = "Resource name prefix (e.g. edgartools-dev)."
  type        = string
}

variable "aws_region" {
  description = "AWS region where resources are deployed."
  type        = string
}

variable "account_id" {
  description = "AWS account ID — used in the EventBridge ARN prefix filter and the SNS topic policy."
  type        = string
}

variable "subscriber_email" {
  description = "Email address that receives pipeline failure notifications. No default — operator must supply explicitly."
  type        = string
}

variable "tags" {
  description = "Additional tags merged onto all resources."
  type        = map(string)
  default     = {}
}
