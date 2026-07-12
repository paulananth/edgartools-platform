data "aws_caller_identity" "current" {}

locals {
  expected_terraform_state_bucket_name = "edgartools-${var.environment}-tfstate-${data.aws_caller_identity.current.account_id}"
  terraform_state_bucket_name          = coalesce(var.terraform_state_bucket_name, local.expected_terraform_state_bucket_name)
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = local.terraform_state_bucket_name

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = !contains(var.retired_aws_account_ids, data.aws_caller_identity.current.account_id)
      error_message = "Refusing to bootstrap Terraform state in retired AWS account ${data.aws_caller_identity.current.account_id}. Fix the selected AWS profile before retrying."
    }

    precondition {
      condition     = local.terraform_state_bucket_name == local.expected_terraform_state_bucket_name
      error_message = "Terraform state bucket must be ${local.expected_terraform_state_bucket_name}; got ${local.terraform_state_bucket_name}. Remove the stale override or select the correct AWS profile."
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    # SSE-C (customer-provided keys) is blocked at the account level.
    # Declared explicitly so Terraform tracks it and plan stays clean.
    blocked_encryption_types = ["SSE-C"]

    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
