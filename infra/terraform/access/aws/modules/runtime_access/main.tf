data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  snowflake_sns_principal_arn = (
    var.snowflake_manifest_subscriber_arn != null
    ? var.snowflake_manifest_subscriber_arn
    : (var.snowflake_bootstrap_enabled ? "*" : null)
  )
  snowflake_role_trust_principal_arn = (
    var.snowflake_manifest_subscriber_arn != null
    ? var.snowflake_manifest_subscriber_arn
    : (var.snowflake_bootstrap_enabled ? "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" : null)
  )
  aws_region                  = data.aws_region.current.region
  ecs_task_definition_pattern = "arn:aws:ecs:${local.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${var.name_prefix}-*:*"
  runner_execution_role_name  = "sec_platform_runner_execution"
  runner_task_role_name       = "sec_platform_runner_task"
  runner_sfn_role_name        = "sec_platform_runner_step_functions"
  tags = merge(
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = "edgartools"
    },
    var.tags,
  )
}

resource "aws_sns_topic_policy" "snowflake_manifest_events" {
  arn = var.snowflake_manifest_sns_topic_arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid    = "AllowS3PublishFromSnowflakeExportBucket"
          Effect = "Allow"
          Principal = {
            Service = "s3.amazonaws.com"
          }
          Action   = "SNS:Publish"
          Resource = var.snowflake_manifest_sns_topic_arn
          Condition = {
            ArnLike = {
              "aws:SourceArn" = var.snowflake_export_bucket_arn
            }
            StringEquals = {
              "aws:SourceAccount" = data.aws_caller_identity.current.account_id
            }
          }
        }
      ],
      local.snowflake_sns_principal_arn == null ? [] : [
        {
          Sid    = "AllowSnowflakeSubscribeToManifestTopic"
          Effect = "Allow"
          Principal = {
            AWS = local.snowflake_sns_principal_arn
          }
          Action   = "SNS:Subscribe"
          Resource = var.snowflake_manifest_sns_topic_arn
        }
      ]
    )
  })
}

resource "aws_iam_role" "snowflake_storage_reader" {
  count = local.snowflake_role_trust_principal_arn == null ? 0 : 1

  name = "${var.name_prefix}-snowflake-s3"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = local.snowflake_role_trust_principal_arn
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = var.snowflake_storage_external_id
          }
        }
      }
    ]
  })

  tags = merge(local.tags, { Name = "${var.name_prefix}-snowflake-s3", Role = "snowflake-storage-reader" })
}

resource "aws_iam_role_policy" "snowflake_storage_reader" {
  count = length(aws_iam_role.snowflake_storage_reader) == 0 ? 0 : 1

  name = "${var.name_prefix}-snowflake-export-s3-read"
  role = aws_iam_role.snowflake_storage_reader[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "GetSnowflakeExportBucketLocation"
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation"]
        Resource = var.snowflake_export_bucket_arn
      },
      {
        Sid      = "ListSnowflakeExportPrefix"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.snowflake_export_bucket_arn
        Condition = {
          StringLike = {
            "s3:prefix" = [
              var.snowflake_export_prefix,
              "${var.snowflake_export_prefix}*"
            ]
          }
        }
      },
      {
        Sid    = "ReadSnowflakeExportObjects"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion"
        ]
        Resource = "${var.snowflake_export_bucket_arn}/${var.snowflake_export_prefix}*"
      },
      {
        Sid    = "DecryptSnowflakeExportObjects"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey",
          "kms:GenerateDataKey"
        ]
        Resource = var.snowflake_export_kms_key_arn
      }
    ]
  })
}

resource "aws_iam_role" "ecs_task_execution_warehouse" {
  name = local.runner_execution_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.tags, {
    Name         = local.runner_execution_role_name
    Principal    = "sec_platform_runner"
    RunnerRole   = "execution"
    ServiceTrust = "ecs-tasks.amazonaws.com"
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_warehouse_managed" {
  role       = aws_iam_role.ecs_task_execution_warehouse.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_task_execution_warehouse_secret" {
  name = "sec_platform_runner_execution_secret"
  role = aws_iam_role.ecs_task_execution_warehouse.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = concat([var.edgar_identity_secret_arn], var.mdm_secret_arns)
      }
    ]
  })
}

resource "aws_iam_role" "ecs_task_warehouse" {
  name = local.runner_task_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.tags, {
    Name         = local.runner_task_role_name
    Principal    = "sec_platform_runner"
    RunnerRole   = "task"
    ServiceTrust = "ecs-tasks.amazonaws.com"
  })
}

resource "aws_iam_role_policy" "ecs_task_warehouse_storage" {
  name = "sec_platform_runner_task_storage"
  role = aws_iam_role.ecs_task_warehouse.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = [var.bronze_bucket_arn, var.warehouse_bucket_arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.snowflake_export_bucket_arn
        Condition = {
          StringLike = {
            "s3:prefix" = [
              trimsuffix(var.snowflake_export_prefix, "/"),
              "${var.snowflake_export_prefix}*"
            ]
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${var.bronze_bucket_arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "${var.warehouse_bucket_arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${var.snowflake_export_bucket_arn}/${var.snowflake_export_prefix}*"
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = var.snowflake_export_kms_key_arn
      }
    ]
  })
}

resource "aws_iam_role" "step_functions" {
  name = local.runner_sfn_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.tags, {
    Name         = local.runner_sfn_role_name
    Principal    = "sec_platform_runner"
    RunnerRole   = "step-functions"
    ServiceTrust = "states.amazonaws.com"
  })
}

resource "aws_iam_role_policy" "step_functions_runtime" {
  name = "sec_platform_runner_step_functions_runtime"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = local.ecs_task_definition_pattern
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeTasks",
          "ecs:StopTask"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_task_execution_warehouse.arn,
          aws_iam_role.ecs_task_warehouse.arn
        ]
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "events:PutTargets",
          "events:PutRule",
          "events:DescribeRule"
        ]
        Resource = "arn:aws:events:${local.aws_region}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventsForECSTaskRule"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.bronze_bucket_arn,
          "${var.bronze_bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "states:StartExecution",
          "states:DescribeExecution",
          "states:StopExecution"
        ]
        Resource = "*"
      }
    ]
  })
}
