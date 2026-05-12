data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  oidc_url          = "token.actions.githubusercontent.com"
  oidc_provider_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.oidc_url}"
  role_name         = "${var.name_prefix}-github-actions-ecr"
  # Wildcard ARN covering all repos with the given prefix in this account/region.
  ecr_arn_pattern   = "arn:aws:ecr:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:repository/${var.ecr_name_prefix}*"
}

# GitHub OIDC provider — one per AWS account, idempotent.
resource "aws_iam_openid_connect_provider" "github_actions" {
  url = "https://${local.oidc_url}"

  client_id_list = ["sts.amazonaws.com"]

  # AWS validates the cert chain; thumbprints are a secondary guard.
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]

  tags = var.tags

  lifecycle {
    ignore_changes = [thumbprint_list]
  }
}

# IAM role assumed by GitHub Actions via OIDC.
resource "aws_iam_role" "github_actions_ecr" {
  name = local.role_name
  tags = var.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = local.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${local.oidc_url}:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "${local.oidc_url}:sub" = "repo:${var.github_org}/${var.github_repo}:*"
          }
        }
      }
    ]
  })

  depends_on = [aws_iam_openid_connect_provider.github_actions]
}

# ECR authentication + push to all repos with the given name prefix.
resource "aws_iam_role_policy" "ecr_push" {
  name = "ecr-push"
  role = aws_iam_role.github_actions_ecr.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ECRAuth"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "ECRPush"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:DescribeRepositories",
          "ecr:CreateRepository",
          "ecr:DescribeImages",
        ]
        Resource = local.ecr_arn_pattern
      }
    ]
  })
}

# Step Functions + CloudWatch read access for the smoke test workflow.
resource "aws_iam_role_policy" "smoke_test" {
  name = "smoke-test"
  role = aws_iam_role.github_actions_ecr.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "StepFunctions"
        Effect = "Allow"
        Action = [
          "states:StartExecution",
          "states:DescribeExecution",
          "states:ListExecutions",
          "states:GetExecutionHistory",
        ]
        Resource = [
          "arn:aws:states:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.ecr_name_prefix}*",
          "arn:aws:states:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:execution:${var.ecr_name_prefix}*:*",
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/states/${var.ecr_name_prefix}*:*"
      },
      {
        Sid    = "SecretsManagerRead"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
        ]
        Resource = "arn:aws:secretsmanager:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:secret:${var.ecr_name_prefix}*"
      }
    ]
  })
}
