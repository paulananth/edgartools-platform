variable "environment" {
  description = "AWS account environment name."
  type        = string
}

variable "aws_region" {
  description = "AWS region for the Terraform state bucket."
  type        = string
  default     = "us-east-1"
}

variable "terraform_state_bucket_name" {
  description = "Optional state bucket override. It must match edgartools-<environment>-tfstate-<authenticated-account-id>."
  type        = string
  default     = null
}

variable "retired_aws_account_ids" {
  description = "AWS accounts in which bootstrap is forbidden."
  type        = set(string)
  default     = ["077127448006"]
}

variable "tags" {
  description = "Additional tags applied to state resources."
  type        = map(string)
  default     = {}
}
