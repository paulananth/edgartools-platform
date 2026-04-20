output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs for canonical warehouse tasks."
  value       = [for subnet in aws_subnet.public : subnet.id]
}

output "public_ecs_security_group_id" {
  description = "Security group ID for public ECS tasks."
  value       = aws_security_group.ecs_public_tasks.id
}

output "s3_vpc_endpoint_id" {
  description = "Gateway VPC endpoint ID for S3."
  value       = aws_vpc_endpoint.s3.id
}

