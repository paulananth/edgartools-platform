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
  name         = "${local.name_prefix}-warehouse"
  force_delete = var.ecr_force_delete
  # MUTABLE, not IMMUTABLE: :dev is deliberately overwritten on every build
  # (see repo docs' "Tagging strategy" table -- ":dev" is the mutable latest
  # dev image). IMMUTABLE here broke every push to :dev after the first one,
  # since ECR refuses to overwrite an immutable tag -- this is what took the
  # Deploy GitHub Actions workflow down on every run from PR #107 onward
  # until fixed directly via `aws ecr put-image-tag-mutability`. Declaring it
  # MUTABLE here too (not just live) so `terraform apply` doesn't silently
  # revert that fix back to IMMUTABLE the next time state is reconciled.
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.tags, { Name = "${local.name_prefix}-warehouse" })
}

resource "aws_ecr_lifecycle_policy" "warehouse" {
  repository = aws_ecr_repository.warehouse.name

  # ECS task definitions pin image digests that are also retained under
  # immutable sha-* tags. Expiring tagged images by repository count can make
  # a still-registered task definition unlaunchable. Clean up only untagged
  # manifests; tagged rollback and task-definition images remain durable.
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire only untagged images beyond the newest 20"
        selection = {
          tagStatus   = "untagged"
          countType   = "imageCountMoreThan"
          countNumber = 20
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
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

resource "aws_secretsmanager_secret" "mdm_postgres_dsn" {
  name        = "${local.name_prefix}/mdm/postgres_dsn"
  description = "Empty PostgreSQL connection string container for MDM. Populate the Snowflake Postgres application DSN out-of-band."

  tags = merge(local.tags, { Name = "${local.name_prefix}/mdm/postgres_dsn", RuntimeSecret = "mdm-postgres-dsn" })
}

resource "aws_secretsmanager_secret" "mdm_neo4j" {
  name        = "${local.name_prefix}/mdm/neo4j"
  description = "Empty Neo4j connection details container for MDM graph sync. Populate the value out-of-band."

  tags = merge(local.tags, { Name = "${local.name_prefix}/mdm/neo4j", RuntimeSecret = "mdm-neo4j" })
}

resource "aws_secretsmanager_secret" "mdm_api_keys" {
  name        = "${local.name_prefix}/mdm/api_keys"
  description = "Empty MDM API key container. Populate the value out-of-band."

  tags = merge(local.tags, { Name = "${local.name_prefix}/mdm/api_keys", RuntimeSecret = "mdm-api-keys" })
}

resource "aws_secretsmanager_secret" "mdm_snowflake" {
  name        = "${local.name_prefix}/mdm/snowflake"
  description = "Empty Snowflake connection details container for MDM graph/export tasks. Populate the value out-of-band."

  tags = merge(local.tags, { Name = "${local.name_prefix}/mdm/snowflake", RuntimeSecret = "mdm-snowflake" })
}
