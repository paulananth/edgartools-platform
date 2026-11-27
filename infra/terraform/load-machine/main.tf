# The hosted load on AWS: one Step Functions state machine, its activity, and one large ARM Fargate task that runs the
# loader image. Applied and run by infra/load-pipeline/aws-load.sh, which names the image, the run and the lane count.

terraform {
  required_version = ">= 1.14.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.39.0"
    }
  }

  backend "s3" {
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = "prod"
      ManagedBy   = "terraform"
      Project     = "edgartools"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "expected_aws_account_id" {
  type    = string
  default = "690839588395"
}

variable "image" {
  description = "The loader image in ECR, by its commit tag."
  type        = string
}

variable "run" {
  description = "The load's run label: its state file, logs and run documents."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,60}$", var.run))
    error_message = "A run label is lowercase letters, digits and hyphens."
  }
}

variable "lanes" {
  description = "The load jobs file's lane count: every lane runs at once."
  type        = number
}

variable "cpu" {
  description = "Task CPU units (16384 is 16 vCPU, Fargate's largest)."
  type        = number
  default     = 16384
}

variable "memory" {
  description = "Task memory in MiB (122880 is 120 GB, Fargate's largest)."
  type        = number
  default     = 122880
}

variable "max_hours" {
  description = "The task stops itself after this many hours, whatever started it: it is billed while it runs."
  type        = number
  default     = 24
}

variable "metrics_cidr" {
  description = "The one address (a /32) that may read the task's load exporter: the operator's Mac, whose Prometheus scrapes it. Null opens nothing."
  type        = string
  default     = null

  validation {
    condition     = var.metrics_cidr == null || (can(cidrhost(var.metrics_cidr, 0)) && endswith(coalesce(var.metrics_cidr, "-"), "/32"))
    error_message = "metrics_cidr is one IPv4 address as a /32, or null."
  }
}

variable "disk_gib" {
  description = "Task disk: the captures, the run documents and the logs of one load."
  type        = number
  default     = 200
}

locals {
  name      = "edgartools-prod-load"
  bucket    = "edgartools-prod-bronze-${var.expected_aws_account_id}"
  s3        = "s3://${local.bucket}/load"
  aws_image = "public.ecr.aws/aws-cli/aws-cli:2.31.0"

  # The logins the gate and the load read, as the secret's keys and the file each becomes under the task's home.
  logins = {
    OWNER_ENV      = "hosted/owner.env"
    WORKER_ENV     = "hosted/worker.env"
    GOVERNANCE_ENV = "hosted/governance.env"
    READER_ENV     = "hosted/reader.env"
    MIRROR_ENV     = "mirror-operator/mirror-operator.env"
    MIRROR_KEY     = "mirror-operator/mirror-operator.p8"
  }

  home = "/data/home"

  # The load's one state machine definition, with every lane running at once.
  machine = jsondecode(templatefile("${path.module}/../../load-pipeline/state-machine.asl.json",
  { activity = aws_sfn_activity.load.id }))
  run_lanes = merge(local.machine.States["Run lanes"], { MaxConcurrency = var.lanes })

  fetch = join("\n", concat(
    [
      "set -eu",
      "umask 077",
      "config=${local.home}/.config/edgartools",
      "mkdir -p $config/hosted $config/mirror-operator /data/mdm/captures /data/mdm/proving /data/load-logs /data/manifests",
    ],
    [for key, file in local.logins : "printf '%s' \"$${${key}}\" | base64 -d > $config/${file}"],
    [
      # A capture is tens of thousands of small files: their number, not their size, sets the time.
      "aws configure set default.s3.max_concurrent_requests 100",
      "aws s3 sync --only-show-errors ${local.s3}/captures /data/mdm/captures",
      "aws s3 sync --only-show-errors ${local.s3}/proving /data/mdm/proving",
      # A task started again for the same run carries on from its state file and its run documents.
      "aws s3 sync --only-show-errors ${local.s3}/runs/${var.run}/logs /data/load-logs",
      "aws s3 sync --only-show-errors ${local.s3}/runs/${var.run}/manifests /data/manifests",
    ],
  ))

  # The run's record outlives the task: its logs, its run documents and the loader's error log are copied every minute,
  # each by its own loop so a long copy holds up no other, and the first two once more at the stop. This container also
  # bounds the task: when it ends after `max_hours`, the task stops with it.
  keep = <<-EOT
    record=${local.s3}/runs/${var.run}
    errors=${local.home}/.config/edgartools/hosted/load-errors.log
    started=$(date +%s)
    logs() {
      aws s3 sync --only-show-errors /data/load-logs $record/logs
      [ ! -f $errors ] || aws s3 cp --only-show-errors $errors $record/errors/load-errors-$started.log
    }
    documents() { aws s3 sync --only-show-errors /data/manifests $record/manifests; }
    while true; do logs || true; sleep 60; done & copying_logs=$!
    while true; do documents || true; sleep 60; done & copying_documents=$!
    finish() {
      kill $copying_logs $copying_documents 2>/dev/null
      logs; documents
      exit 0
    }
    trap finish TERM
    sleep $((${var.max_hours} * 3600)) & wait $!
    echo "the load task reached its bound of ${var.max_hours} hours: stopping"
    finish
  EOT

  exporter_port = 9108

  log = { for name in ["fetch", "keep", "worker", "exporter"] : name => {
    logDriver = "awslogs"
    options = {
      awslogs-group         = aws_cloudwatch_log_group.load.name
      awslogs-region        = var.aws_region
      awslogs-stream-prefix = name
    }
  } }
}

data "aws_caller_identity" "current" {}

check "canonical_prod_account" {
  assert {
    condition     = data.aws_caller_identity.current.account_id == var.expected_aws_account_id
    error_message = "The load runs in AWS account ${var.expected_aws_account_id}."
  }
}

data "aws_vpc" "prod" {
  tags = { Name = "edgartools-prod-vpc" }
}

# The load exporter's port, open to the operator's Mac only. The task's other traffic goes through the cluster's own group.
resource "aws_security_group" "metrics" {
  name        = "${local.name}-metrics"
  description = "The load exporter, read by the operator's Prometheus"
  vpc_id      = data.aws_vpc.prod.id

  dynamic "ingress" {
    for_each = var.metrics_cidr == null ? [] : [var.metrics_cidr]
    content {
      description = "Prometheus on the operator's Mac"
      protocol    = "tcp"
      from_port   = local.exporter_port
      to_port     = local.exporter_port
      cidr_blocks = [ingress.value]
    }
  }
}

resource "aws_cloudwatch_log_group" "load" {
  name              = "/edgartools/prod/load"
  retention_in_days = 30
}

# Its value is written by aws-load.sh from the operator's private files, never by Terraform, so no login is in its state.
resource "aws_secretsmanager_secret" "logins" {
  name                    = "${local.name}/logins"
  recovery_window_in_days = 7
}

resource "aws_sfn_activity" "load" {
  name = local.name
}

data "aws_iam_policy_document" "assume" {
  for_each = toset(["ecs-tasks.amazonaws.com", "states.amazonaws.com"])

  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = [each.key]
    }
  }
}

resource "aws_iam_role" "machine" {
  name               = "${local.name}-machine"
  assume_role_policy = data.aws_iam_policy_document.assume["states.amazonaws.com"].json
}

resource "aws_sfn_state_machine" "load" {
  name       = local.name
  role_arn   = aws_iam_role.machine.arn
  definition = jsonencode(merge(local.machine, { States = merge(local.machine.States, { "Run lanes" = local.run_lanes }) }))
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.assume["ecs-tasks.amazonaws.com"].json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.logins.arn]
  }
}

resource "aws_iam_role_policy" "execution" {
  name   = "logins"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution.json
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.assume["ecs-tasks.amazonaws.com"].json
}

data "aws_iam_policy_document" "task" {
  statement {
    actions   = ["states:GetActivityTask"]
    resources = [aws_sfn_activity.load.id]
  }

  # A task token names its own execution: these actions take no narrower resource.
  statement {
    actions   = ["states:SendTaskSuccess", "states:SendTaskFailure", "states:SendTaskHeartbeat"]
    resources = ["*"]
  }

  statement {
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${local.bucket}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["load/*"]
    }
  }

  statement {
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${local.bucket}/load/*"]
  }

  # The captures are read only: a task writes its own run's record and nothing else.
  statement {
    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::${local.bucket}/load/runs/${var.run}/*"]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "load"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

resource "aws_ecs_task_definition" "load" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  ephemeral_storage {
    size_in_gib = var.disk_gib
  }

  # The exporter reads the load's processes (each step's CPU and memory) as the local pipeline's exporter does.
  pid_mode = "task"

  volume {
    name = "data"
  }

  container_definitions = jsonencode([
    {
      name             = "fetch"
      image            = local.aws_image
      essential        = false
      entryPoint       = ["/bin/sh", "-c"]
      command          = [local.fetch]
      secrets          = [for key, file in local.logins : { name = key, valueFrom = "${aws_secretsmanager_secret.logins.arn}:${key}::" }]
      mountPoints      = [{ sourceVolume = "data", containerPath = "/data" }]
      logConfiguration = local.log["fetch"]
    },
    {
      name             = "keep"
      image            = local.aws_image
      essential        = true
      entryPoint       = ["/bin/sh", "-c"]
      command          = [local.keep]
      dependsOn        = [{ containerName = "fetch", condition = "SUCCESS" }]
      stopTimeout      = 120
      mountPoints      = [{ sourceVolume = "data", containerPath = "/data" }]
      logConfiguration = local.log["keep"]
    },
    {
      name      = "worker"
      image     = var.image
      essential = true
      # The record's keeper starts first, so it stops last.
      dependsOn       = [{ containerName = "fetch", condition = "SUCCESS" }, { containerName = "keep", condition = "START" }]
      linuxParameters = { initProcessEnabled = true }
      stopTimeout     = 120
      environment = [for name, value in {
        HOME               = local.home
        STORES             = "${local.home}/.config/edgartools/hosted"
        CAPTURES           = "/data/mdm/captures"
        PROVING            = "/data/mdm/proving"
        LOGS               = "/data/load-logs"
        RUN                = var.run
        ACTIVITY_ARN       = aws_sfn_activity.load.id
        AWS_DEFAULT_REGION = var.aws_region
      } : { name = name, value = value }]
      mountPoints      = [{ sourceVolume = "data", containerPath = "/data" }]
      logConfiguration = local.log["worker"]
    },
    {
      # The load monitor's exporter, as the local pipeline runs it: the reader login and the run's logs, read only.
      name         = "exporter"
      image        = var.image
      essential    = false
      entryPoint   = ["python", "/app/skills/load-monitoring/scripts/exporter.py", "serve"]
      dependsOn    = [{ containerName = "fetch", condition = "SUCCESS" }]
      portMappings = [{ containerPort = local.exporter_port, protocol = "tcp" }]
      environment = [for name, value in {
        HOME     = local.home
        STORES   = "${local.home}/.config/edgartools/hosted"
        LOGS     = "/data/load-logs"
        RUN      = var.run
        CAPACITY = "local"
      } : { name = name, value = value }]
      mountPoints      = [{ sourceVolume = "data", containerPath = "/data", readOnly = true }]
      logConfiguration = local.log["exporter"]
    },
  ])
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.load.arn
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.load.arn
}

output "metrics_security_group_id" {
  value = aws_security_group.metrics.id
}

output "exporter_port" {
  value = local.exporter_port
}

output "secret_arn" {
  value = aws_secretsmanager_secret.logins.arn
}

output "record" {
  value = "${local.s3}/runs/${var.run}"
}
