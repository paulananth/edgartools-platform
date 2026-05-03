locals {
  name_prefix               = "edgartools-${var.environment}"
  snowflake_export_root     = "s3://${var.snowflake_export_bucket_name}/warehouse/artifacts/snowflake_exports"
  snowflake_export_root_url = "${local.snowflake_export_root}/"
  snowflake_export_prefix   = "warehouse/artifacts/snowflake_exports/"
  tags = merge(
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = "edgartools"
    },
    var.tags,
  )
}

resource "aws_ecr_repository" "warehouse" {
  name                 = "${local.name_prefix}-warehouse"
  force_delete         = var.ecr_force_delete
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.tags, { Name = "${local.name_prefix}-warehouse" })
}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/aws/ecs/${local.name_prefix}-warehouse"
  retention_in_days = 30

  tags = local.tags
}

resource "aws_sns_topic" "snowflake_manifest_events" {
  name = "${local.name_prefix}-snowflake-manifest-events"
  tags = merge(local.tags, { Name = "${local.name_prefix}-snowflake-manifest-events" })
}

resource "aws_secretsmanager_secret" "edgar_identity" {
  count = var.edgar_identity_secret_arn == null ? 1 : 0

  name                    = "${local.name_prefix}-edgar-identity"
  description             = "Empty SEC EDGAR identity secret container. Populate the value out-of-band."
  recovery_window_in_days = 0

  tags = merge(local.tags, { Name = "${local.name_prefix}-edgar-identity" })
}

locals {
  resolved_edgar_identity_secret_arn = coalesce(
    var.edgar_identity_secret_arn,
    try(aws_secretsmanager_secret.edgar_identity[0].arn, null),
  )
}

resource "aws_ecs_cluster" "warehouse" {
  name = "${local.name_prefix}-warehouse"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(local.tags, { Name = "${local.name_prefix}-warehouse" })
}

resource "aws_secretsmanager_secret" "runner_credentials" {
  name                    = "${local.name_prefix}-runner-credentials"
  description             = "Legacy empty operator credential container. Do not use for sec_platform_runner runtime roles."
  recovery_window_in_days = 0

  tags = merge(local.tags, { Name = "${local.name_prefix}-runner-credentials", Legacy = "runner-credentials" })
}
