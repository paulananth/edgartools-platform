output "role_arn" {
  description = "IAM role ARN that GitHub Actions assumes via OIDC."
  value       = aws_iam_role.github_actions_ecr.arn
}

output "role_name" {
  description = "IAM role name."
  value       = aws_iam_role.github_actions_ecr.name
}
