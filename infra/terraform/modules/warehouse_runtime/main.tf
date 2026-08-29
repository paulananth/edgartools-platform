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

# Single shared image repository for both runtimes (warehouse, mdm) and both
# build stages (deps, final) -- role/stage is encoded in the tag prefix
# (warehouse-*, mdm-*, warehouse-deps-*, mdm-deps-*) instead of the repo name.
# Replaces the original 4-repo split (warehouse/mdm x final/deps) -- those
# repos and their aws_ecr_repository.warehouse Terraform resource have been
# deleted after every ECS task definition was confirmed re-pointed here; see
# CLAUDE.md's "Image management" section.
resource "aws_ecr_repository" "images" {
  name         = "${local.name_prefix}-images"
  force_delete = var.ecr_force_delete
  # MUTABLE, not IMMUTABLE: role-prefixed :dev/:prod tags (warehouse-dev,
  # mdm-prod, ...) are deliberately overwritten on every build. IMMUTABLE
  # broke every push to :dev after the first one for the predecessor repo
  # (see PR #107 incident, TODOS.md) -- declaring it MUTABLE here too so
  # `terraform apply` can't silently revert that.
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.tags, { Name = "${local.name_prefix}-images" })
}

resource "aws_ecr_lifecycle_policy" "images" {
  repository = aws_ecr_repository.images.name

  # ECS task definitions pin image digests that are also retained under
  # immutable role-prefixed sha tags. Expiring tagged images by count can
  # make a still-registered task definition unlaunchable, so only untagged
  # manifests are ever expired -- every tagged image stays durable.
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
  name = "/aws/ecs/${local.name_prefix}-warehouse"
  # Operational Forensics Window (ops-cost-control map): seven days across
  # every production CloudWatch log group. Keep in sync with the Step
  # Functions and Container Insights groups, both set the same way by
  # ensure_log_group() in deploy-aws-application.sh.
  retention_in_days = 7

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

resource "aws_secretsmanager_secret" "bookkeeping_postgres_dsn" {
  name        = "${local.name_prefix}/bookkeeping/postgres_dsn"
  description = "Empty PostgreSQL connection string container for the bookkeeping store (dedicated bookkeeping_app role, same Snowflake Postgres instance as MDM). Populate out-of-band via bootstrap-bookkeeping-postgres.sh."

  tags = merge(local.tags, { Name = "${local.name_prefix}/bookkeeping/postgres_dsn", RuntimeSecret = "bookkeeping-postgres-dsn" })
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
