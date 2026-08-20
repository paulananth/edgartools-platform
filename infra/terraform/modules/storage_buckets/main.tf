locals {
  tags = merge(
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = "edgartools"
    },
    var.tags,
  )
}

resource "aws_s3_bucket" "bronze" {
  bucket = var.bronze_bucket_name

  tags = merge(local.tags, { Name = var.bronze_bucket_name, DataZone = "bronze" })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "bronze" {
  bucket = aws_s3_bucket.bronze.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "bronze" {
  bucket = aws_s3_bucket.bronze.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "bronze" {
  bucket = aws_s3_bucket.bronze.id

  rule {
    # SSE-C (customer-provided keys) is blocked at the account level.
    # Declared explicitly so Terraform tracks it and plan stays clean.
    blocked_encryption_types = ["SSE-C"]

    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "bronze" {
  bucket = aws_s3_bucket.bronze.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket" "warehouse" {
  bucket = var.warehouse_bucket_name

  tags = merge(local.tags, { Name = var.warehouse_bucket_name, DataZone = "warehouse" })
}

resource "aws_s3_bucket_public_access_block" "warehouse" {
  bucket = aws_s3_bucket.warehouse.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "warehouse" {
  bucket = aws_s3_bucket.warehouse.id

  rule {
    # SSE-C (customer-provided keys) is blocked at the account level.
    # Declared explicitly so Terraform tracks it and plan stays clean.
    blocked_encryption_types = ["SSE-C"]

    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "warehouse" {
  bucket = aws_s3_bucket.warehouse.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_ownership_controls" "warehouse" {
  bucket = aws_s3_bucket.warehouse.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "warehouse" {
  bucket = aws_s3_bucket.warehouse.id

  # Backstop for staged canonical-silver promotion candidates
  # (warehouse/silverstage/<uuid>/..., written by
  # ObjectStorage.write_staged_bytes -- see
  # edgar_warehouse/infrastructure/object_storage.py). The relative write
  # path is silverstage/<uuid>/..., but ObjectStorage.join() prefixes the
  # storage root, which already ends in /warehouse, so live keys are
  # warehouse/silverstage/... . A filter of silverstage/ matches nothing
  # (confirmed 2026-08-20: 1,999 orphaned DuckDB copies, 1.70 TiB).
  # promote_staged deliberately never deletes a staged object on a
  # PromotionConflictError (left in place for inspection/retry), and the
  # reducer's own explicit-delete-on-success path (release-readiness
  # ticket 65) only covers the success case. Without this rule a staged
  # object with no successful promotion and no manual cleanup lives
  # forever -- confirmed live in prod: 46 orphaned objects, 49.3GB, under
  # the pre-rename `_staging/` prefix, with no lifecycle rule at all
  # (`get-bucket-lifecycle-configuration` returned NoSuchLifecycleConfiguration).
  rule {
    id     = "expire-silver-staging-candidates"
    status = "Enabled"

    filter {
      prefix = "warehouse/silverstage/"
    }

    expiration {
      days = 3
    }

    noncurrent_version_expiration {
      noncurrent_days = 3
    }
  }

  # Backstop for the canonical silver.duckdb + shard-N.duckdb keys under
  # warehouse/silver/. Every merge_candidate_into_canonical publish
  # (edgar_warehouse/silver_protection.py) promotes a brand-new full-file
  # copy onto these keys; with bucket versioning enabled and no lifecycle
  # rule, every prior version stays billed forever. Confirmed live in prod
  # (ecs-cost-sizing ticket 22): 458+ noncurrent versions on silver.duckdb
  # alone, 1.34TB of pure noncurrent-version waste across the 5 canonical
  # keys (~$1.05/day of the platform's measured ~$2/day steady-state S3
  # cost). No `expiration` block here, deliberately -- unlike
  # silverstage/'s ephemeral staging candidates, these ARE the live
  # canonical data; expiring the *current* version on a quiet day would
  # delete the only copy. Only noncurrent (already-superseded) versions
  # are ever eligible.
  rule {
    id     = "expire-noncurrent-silver-canonical-versions"
    status = "Enabled"

    filter {
      prefix = "warehouse/silver/"
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

resource "aws_kms_key" "snowflake_export" {
  description             = "CMK for Snowflake export artifacts in ${var.environment}."
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(local.tags, { Name = "${var.snowflake_export_bucket_name}-kms" })
}

resource "aws_kms_alias" "snowflake_export" {
  name          = "alias/${var.snowflake_export_bucket_name}"
  target_key_id = aws_kms_key.snowflake_export.key_id
}

resource "aws_s3_bucket" "snowflake_export" {
  bucket = var.snowflake_export_bucket_name

  tags = merge(local.tags, { Name = var.snowflake_export_bucket_name, DataZone = "snowflake-export" })
}

resource "aws_s3_bucket_public_access_block" "snowflake_export" {
  bucket = aws_s3_bucket.snowflake_export.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "snowflake_export" {
  bucket = aws_s3_bucket.snowflake_export.id

  rule {
    blocked_encryption_types = ["SSE-C"]
    bucket_key_enabled       = true

    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.snowflake_export.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_versioning" "snowflake_export" {
  bucket = aws_s3_bucket.snowflake_export.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_ownership_controls" "snowflake_export" {
  bucket = aws_s3_bucket.snowflake_export.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "snowflake_export" {
  bucket = aws_s3_bucket.snowflake_export.id

  rule {
    id     = "expire-snowflake-exports"
    status = "Enabled"

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}
