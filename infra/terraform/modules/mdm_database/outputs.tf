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

output "db_security_group_id" {
  description = "Security group attached to the RDS instance."
  value       = aws_security_group.rds.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs created for the MDM data plane."
  value       = [for s in aws_subnet.private : s.id]
}

output "postgres_dsn_secret_arn" {
  description = "Secrets Manager ARN for the PostgreSQL DSN."
  value       = aws_secretsmanager_secret.postgres_dsn.arn
}

output "neo4j_secret_arn" {
  description = "Secrets Manager ARN for Neo4j connection details."
  value       = aws_secretsmanager_secret.neo4j.arn
}

output "api_keys_secret_arn" {
  description = "Secrets Manager ARN for MDM API keys."
  value       = aws_secretsmanager_secret.api_keys.arn
}
