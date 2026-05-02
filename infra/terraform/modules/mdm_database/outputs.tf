output "db_instance_id" {
  description = "RDS instance identifier."
  value       = aws_db_instance.mdm.id
}

output "db_endpoint" {
  description = "RDS endpoint hostname."
  value       = aws_db_instance.mdm.address
}

output "db_port" {
  description = "RDS port."
  value       = aws_db_instance.mdm.port
}

output "db_master_user_secret_arn" {
  description = "AWS-managed RDS master user secret ARN."
  value       = try(aws_db_instance.mdm.master_user_secret[0].secret_arn, null)
}

output "db_security_group_id" {
  description = "Security group attached to the RDS instance."
  value       = aws_security_group.rds.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs created for the MDM data plane."
  value       = [for s in aws_subnet.private : s.id]
}

output "postgres_dsn_secret_arn" {
  description = "Secrets Manager ARN for the empty operator-populated PostgreSQL DSN container."
  value       = aws_secretsmanager_secret.postgres_dsn.arn
}

output "neo4j_secret_arn" {
  description = "Secrets Manager ARN for the empty operator-populated Neo4j connection container."
  value       = aws_secretsmanager_secret.neo4j.arn
}

output "api_keys_secret_arn" {
  description = "Secrets Manager ARN for the empty operator-populated MDM API key container."
  value       = aws_secretsmanager_secret.api_keys.arn
}
