data "aws_caller_identity" "current" {}

locals {
  name_prefix               = "edgartools-${var.environment}"
  container_name            = "edgar-warehouse"
  snowflake_export_root     = "s3://${var.snowflake_export_bucket_name}/warehouse/artifacts/snowflake_exports"
  snowflake_export_root_url = "${local.snowflake_export_root}/"
  snowflake_export_prefix   = "warehouse/artifacts/snowflake_exports/"
  snowflake_manifest_prefix = "warehouse/artifacts/snowflake_exports/manifests/"
  # SNS topic policies can bootstrap with a wildcard principal, but IAM role trust policies cannot.
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
  tags = merge(
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = "edgartools"
    },
    var.tags,
  )

  default_task_profiles = {
    small = {
      cpu    = 512
      memory = 1024
    }
    medium = {
      cpu    = 1024
      memory = 2048
    }
    large = {
      cpu    = 2048
      memory = 4096
    }
  }

  task_profiles = merge(local.default_task_profiles, var.task_profiles)

  default_task_profile_by_workflow = {
    daily_incremental              = "medium"
    bootstrap_recent_10            = "medium"
    bootstrap_full                 = "large"
    targeted_resync                = "small"
    full_reconcile                 = "medium"
    load_daily_form_index_for_date = "small"
    catch_up_daily_form_index      = "small"
    seed_universe                  = "small"
    bootstrap_batch                = "medium"
  }

  task_profile_by_workflow = merge(local.default_task_profile_by_workflow, var.task_profile_by_workflow)

  workflows = {
    daily_incremental = {
      task_profile                               = local.task_profile_by_workflow.daily_incremental
      schedule_expression                        = var.daily_incremental_schedule
      gold_affecting                             = true
      warehouse_command_expression               = "States.Array('daily-incremental', '--run-id', $$.Execution.Name)"
      warehouse_command_with_cik_list_expression = "States.Array('daily-incremental', '--run-id', $$.Execution.Name, '--cik-list', $.cik_list)"
    }
    bootstrap_recent_10 = {
      task_profile                               = local.task_profile_by_workflow.bootstrap_recent_10
      schedule_expression                        = null
      gold_affecting                             = true
      warehouse_command_expression               = "States.Array('bootstrap-recent-10', '--run-id', $$.Execution.Name)"
      warehouse_command_with_cik_list_expression = "States.Array('bootstrap-recent-10', '--run-id', $$.Execution.Name, '--cik-list', $.cik_list)"
    }
    bootstrap_full = {
      task_profile                               = local.task_profile_by_workflow.bootstrap_full
      schedule_expression                        = null
      gold_affecting                             = true
      warehouse_command_expression               = "States.Array('bootstrap-full', '--run-id', $$.Execution.Name)"
      warehouse_command_with_cik_list_expression = "States.Array('bootstrap-full', '--run-id', $$.Execution.Name, '--cik-list', $.cik_list)"
    }
    seed_universe = {
      task_profile                               = local.task_profile_by_workflow.seed_universe
      schedule_expression                        = null
      gold_affecting                             = false
      warehouse_command_expression               = "States.Array('seed-universe', '--run-id', $$.Execution.Name)"
      warehouse_command_with_cik_list_expression = null
    }
    targeted_resync = {
      task_profile                               = local.task_profile_by_workflow.targeted_resync
      schedule_expression                        = null
      gold_affecting                             = true
      warehouse_command_expression               = "States.Array('targeted-resync', '--scope-type', $.scope_type, '--scope-key', $.scope_key, '--run-id', $$.Execution.Name)"
      warehouse_command_with_cik_list_expression = null
    }
    full_reconcile = {
      task_profile                               = local.task_profile_by_workflow.full_reconcile
      schedule_expression                        = var.full_reconcile_schedule
      gold_affecting                             = true
      warehouse_command_expression               = "States.Array('full-reconcile', '--run-id', $$.Execution.Name)"
      warehouse_command_with_cik_list_expression = null
    }
    load_daily_form_index_for_date = {
      task_profile                               = local.task_profile_by_workflow.load_daily_form_index_for_date
      schedule_expression                        = null
      gold_affecting                             = false
      warehouse_command_expression               = "States.Array('load-daily-form-index-for-date', $.target_date, '--run-id', $$.Execution.Name)"
      warehouse_command_with_cik_list_expression = null
    }
    catch_up_daily_form_index = {
      task_profile                               = local.task_profile_by_workflow.catch_up_daily_form_index
      schedule_expression                        = null
      gold_affecting                             = false
      warehouse_command_expression               = "States.Array('catch-up-daily-form-index', '--run-id', $$.Execution.Name)"
      warehouse_command_with_cik_list_expression = null
    }
  }

  scheduled_workflows = {
    for name, workflow in local.workflows :
    name => workflow if workflow.schedule_expression != null
  }
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

resource "aws_cloudwatch_log_group" "step_functions" {
  name              = "/aws/states/${local.name_prefix}-warehouse"
  retention_in_days = 30

  tags = local.tags
}

resource "aws_sns_topic" "snowflake_manifest_events" {
  name = "${local.name_prefix}-snowflake-manifest-events"
  tags = merge(local.tags, { Name = "${local.name_prefix}-snowflake-manifest-events" })
}

resource "aws_sns_topic_policy" "snowflake_manifest_events" {
  arn = aws_sns_topic.snowflake_manifest_events.arn

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
          Resource = aws_sns_topic.snowflake_manifest_events.arn
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
          Resource = aws_sns_topic.snowflake_manifest_events.arn
        }
      ]
    )
  })
}

resource "aws_s3_bucket_notification" "snowflake_manifest_events" {
  bucket = var.snowflake_export_bucket_name

  topic {
    topic_arn     = aws_sns_topic.snowflake_manifest_events.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = local.snowflake_manifest_prefix
    filter_suffix = ".json"
  }

  depends_on = [aws_sns_topic_policy.snowflake_manifest_events]
}

resource "aws_iam_role" "snowflake_storage_reader" {
  count = local.snowflake_role_trust_principal_arn == null ? 0 : 1

  name = "${local.name_prefix}-snowflake-s3"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      merge(
        {
          Effect = "Allow"
          Principal = {
            AWS = local.snowflake_role_trust_principal_arn
          }
          Action = "sts:AssumeRole"
        },
        var.snowflake_storage_external_id == null ? {} : {
          Condition = {
            StringEquals = {
              "sts:ExternalId" = var.snowflake_storage_external_id
            }
          }
        }
      )
    ]
  })

  tags = merge(local.tags, { Name = "${local.name_prefix}-snowflake-s3", Role = "snowflake-storage-reader" })
}

resource "aws_iam_role_policy" "snowflake_storage_reader" {
  count = length(aws_iam_role.snowflake_storage_reader) == 0 ? 0 : 1

  name = "${local.name_prefix}-snowflake-export-s3-read"
  role = aws_iam_role.snowflake_storage_reader[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GetSnowflakeExportBucketLocation"
        Effect = "Allow"
        Action = [
          "s3:GetBucketLocation"
        ]
        Resource = var.snowflake_export_bucket_arn
      },
      {
        Sid    = "ListSnowflakeExportPrefix"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = var.snowflake_export_bucket_arn
        Condition = {
          StringLike = {
            "s3:prefix" = [
              local.snowflake_export_prefix,
              "${local.snowflake_export_prefix}*"
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
        Resource = "${var.snowflake_export_bucket_arn}/${local.snowflake_export_prefix}*"
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

resource "aws_secretsmanager_secret" "edgar_identity" {
  count = var.edgar_identity_secret_arn == null ? 1 : 0

  name                    = "${local.name_prefix}-edgar-identity"
  description             = "SEC EDGAR identity string for warehouse jobs."
  recovery_window_in_days = 0

  tags = merge(local.tags, { Name = "${local.name_prefix}-edgar-identity" })
}

resource "aws_secretsmanager_secret_version" "edgar_identity" {
  count = var.edgar_identity_secret_arn == null && var.edgar_identity_value != null ? 1 : 0

  secret_id     = aws_secretsmanager_secret.edgar_identity[0].id
  secret_string = var.edgar_identity_value
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

resource "aws_iam_role" "ecs_task_execution_warehouse" {
  name = "${local.name_prefix}-warehouse-execution"

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

  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_warehouse_managed" {
  role       = aws_iam_role.ecs_task_execution_warehouse.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_task_execution_warehouse_secret" {
  name = "${local.name_prefix}-warehouse-execution-secret"
  role = aws_iam_role.ecs_task_execution_warehouse.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = local.resolved_edgar_identity_secret_arn
      }
    ]
  })
}

resource "aws_iam_role" "ecs_task_warehouse" {
  name = "${local.name_prefix}-warehouse-task"

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

  tags = local.tags
}

resource "aws_iam_role_policy" "ecs_task_warehouse_storage" {
  name = "${local.name_prefix}-warehouse-storage"
  role = aws_iam_role.ecs_task_warehouse.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = [
          var.bronze_bucket_arn,
          var.warehouse_bucket_arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = var.snowflake_export_bucket_arn
        Condition = {
          StringLike = {
            "s3:prefix" = [
              "warehouse/artifacts/snowflake_exports",
              "warehouse/artifacts/snowflake_exports/*"
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
        Resource = "${var.snowflake_export_bucket_arn}/warehouse/artifacts/snowflake_exports/*"
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

resource "aws_ecs_task_definition" "warehouse" {
  for_each = local.task_profiles

  family                   = "${local.name_prefix}-${each.key}"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution_warehouse.arn
  task_role_arn            = aws_iam_role.ecs_task_warehouse.arn

  container_definitions = jsonencode([
    {
      name      = local.container_name
      image     = coalesce(var.container_image, "scratch")
      essential = true
      command   = ["--help"]
      environment = concat(
        [
          {
            name  = "AWS_REGION"
            value = var.aws_region
          },
          {
            name  = "WAREHOUSE_BRONZE_ROOT"
            value = "s3://${var.bronze_bucket_name}/warehouse/bronze"
          },
          {
            name  = "WAREHOUSE_STORAGE_ROOT"
            value = "s3://${var.warehouse_bucket_name}/warehouse"
          },
          {
            name  = "WAREHOUSE_RUNTIME_MODE"
            value = var.warehouse_runtime_mode
          },
          {
            name  = "WAREHOUSE_ENVIRONMENT"
            value = var.environment
          },
          {
            name  = "SNOWFLAKE_EXPORT_ROOT"
            value = local.snowflake_export_root
          },
          {
            # Silver DuckDB must live on local container disk -- DuckDB cannot
            # read/write S3 paths directly.  /tmp is always writable on Fargate
            # and has 21 GB of ephemeral storage, which is more than enough for
            # a single-run DuckDB file.
            name  = "WAREHOUSE_SILVER_ROOT"
            value = "/tmp/edgar-warehouse-silver"
          }
        ],
        var.warehouse_bronze_cik_limit == null ? [] : [
          {
            name  = "WAREHOUSE_BRONZE_CIK_LIMIT"
            value = tostring(var.warehouse_bronze_cik_limit)
          }
        ]
      )
      secrets = [
        {
          name      = "EDGAR_IDENTITY"
          valueFrom = local.resolved_edgar_identity_secret_arn
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.ecs.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "warehouse-${each.key}"
        }
      }
    }
  ])

  tags = merge(local.tags, { TaskProfile = each.key, Runtime = "warehouse" })
}

resource "aws_iam_role" "step_functions" {
  name = "${local.name_prefix}-step-functions"

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

  tags = local.tags
}

resource "aws_iam_role_policy" "step_functions_runtime" {
  name = "${local.name_prefix}-step-functions-runtime"
  role = aws_iam_role.step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = [for task_definition in aws_ecs_task_definition.warehouse : task_definition.arn]
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
      },
      {
        Effect = "Allow"
        Action = [
          "events:PutTargets",
          "events:PutRule",
          "events:DescribeRule"
        ]
        Resource = "arn:aws:events:${var.aws_region}:${data.aws_caller_identity.current.account_id}:rule/StepFunctionsGetEventsForECSTaskRule"
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

resource "aws_sfn_state_machine" "workflow" {
  for_each = local.workflows

  name     = "${local.name_prefix}-${replace(each.key, "_", "-")}"
  role_arn = aws_iam_role.step_functions.arn

  definition = each.value.warehouse_command_with_cik_list_expression == null ? templatefile("${path.module}/templates/ecs_run_task_single_step.asl.json.tmpl", {
    cluster_arn                  = aws_ecs_cluster.warehouse.arn
    task_definition_arn          = aws_ecs_task_definition.warehouse[each.value.task_profile].arn
    container_name               = local.container_name
    warehouse_command_expression = each.value.warehouse_command_expression
    subnets_json                 = jsonencode(var.public_subnet_ids)
    security_groups_json         = jsonencode([var.public_security_group_id])
    }) : templatefile("${path.module}/templates/ecs_run_task_optional_cik_list.asl.json.tmpl", {
    cluster_arn                                = aws_ecs_cluster.warehouse.arn
    task_definition_arn                        = aws_ecs_task_definition.warehouse[each.value.task_profile].arn
    container_name                             = local.container_name
    warehouse_command_expression               = each.value.warehouse_command_expression
    warehouse_command_with_cik_list_expression = each.value.warehouse_command_with_cik_list_expression
    subnets_json                               = jsonencode(var.public_subnet_ids)
    security_groups_json                       = jsonencode([var.public_security_group_id])
  })

  logging_configuration {
    include_execution_data = true
    level                  = "ALL"
    log_destination        = "${aws_cloudwatch_log_group.step_functions.arn}:*"
  }

  tags = merge(local.tags, { Workflow = each.key })
}

resource "aws_sfn_state_machine" "bootstrap_batched" {
  name     = "${local.name_prefix}-bootstrap-batched"
  role_arn = aws_iam_role.step_functions.arn

  definition = templatefile("${path.module}/templates/ecs_distributed_map_bootstrap.asl.json.tmpl", {
    cluster_arn                     = aws_ecs_cluster.warehouse.arn
    seed_task_definition_arn        = aws_ecs_task_definition.warehouse[local.task_profile_by_workflow.seed_universe].arn
    batch_task_definition_arn       = aws_ecs_task_definition.warehouse[local.task_profile_by_workflow.bootstrap_batch].arn
    container_name                  = local.container_name
    bronze_bucket_name              = var.bronze_bucket_name
    subnets_json                    = jsonencode(var.public_subnet_ids)
    security_groups_json            = jsonencode([var.public_security_group_id])
    batch_concurrency               = var.bootstrap_batch_concurrency
  })

  logging_configuration {
    include_execution_data = true
    level                  = "ALL"
    log_destination        = "${aws_cloudwatch_log_group.step_functions.arn}:*"
  }

  tags = merge(local.tags, { Workflow = "bootstrap_batched" })
}

resource "aws_iam_role" "scheduler" {
  name = "${local.name_prefix}-scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy" "scheduler_start_execution" {
  name = "${local.name_prefix}-scheduler-start-execution"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "states:StartExecution"
        ]
        Resource = [for workflow in aws_sfn_state_machine.workflow : workflow.arn]
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Runner IAM user — may start and monitor Step Functions executions and read
# ECS task logs.  Must NOT have any infrastructure or S3 write permissions.
# Separate from the Terraform deployer account by design.
#
# Access keys are created manually:
#   aws iam create-access-key --user-name <runner-user-name>
# then stored in Secrets Manager:
#   secret name: <name_prefix>-runner-credentials
#   format: {"aws_access_key_id":"...","aws_secret_access_key":"...","aws_region":"..."}
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "runner_credentials" {
  name                    = "${local.name_prefix}-runner-credentials"
  description             = "AWS access key credentials for the ${local.name_prefix}-runner IAM user (Step Functions trigger only). Value set out-of-band after key creation."
  recovery_window_in_days = 0

  tags = merge(local.tags, { Name = "${local.name_prefix}-runner-credentials", Role = "runner" })
}

resource "aws_iam_user" "runner" {
  name          = "${local.name_prefix}-runner"
  force_destroy = var.runner_user_force_destroy
  tags          = merge(local.tags, { Name = "${local.name_prefix}-runner", Role = "runner" })
}

resource "aws_iam_user_policy" "runner" {
  name = "${local.name_prefix}-runner"
  user = aws_iam_user.runner.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "StartWorkflows"
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = [for workflow in aws_sfn_state_machine.workflow : workflow.arn]
      },
      {
        Sid    = "MonitorWorkflows"
        Effect = "Allow"
        Action = [
          "states:DescribeExecution",
          "states:GetExecutionHistory",
          "states:DescribeStateMachine",
          "states:ListExecutions",
          "states:ListStateMachines"
        ]
        Resource = "*"
      },
      {
        Sid    = "ReadTaskLogs"
        Effect = "Allow"
        Action = [
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "${aws_cloudwatch_log_group.ecs.arn}:*"
      }
    ]
  })
}

resource "aws_scheduler_schedule" "workflow" {
  for_each = local.scheduled_workflows

  name                         = "${local.name_prefix}-${replace(each.key, "_", "-")}"
  description                  = "Schedule for ${each.key}"
  group_name                   = "default"
  schedule_expression          = each.value.schedule_expression
  schedule_expression_timezone = var.schedule_timezone
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.workflow[each.key].arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      trigger  = "scheduler"
      workflow = each.key
    })
  }
}

resource "aws_cloudwatch_metric_alarm" "workflow_failures" {
  for_each = local.workflows

  alarm_name          = "${local.name_prefix}-${replace(each.key, "_", "-")}-failures"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_description   = "Alarm when ${each.key} fails."

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.workflow[each.key].arn
  }
}
