###############################################################################
# Private subnets for the MDM data plane.
###############################################################################

resource "aws_subnet" "private" {
  for_each = {
    for idx, az in var.availability_zones :
    az => element(var.private_subnet_cidrs, idx)
  }

  vpc_id            = var.vpc_id
  cidr_block        = each.value
  availability_zone = each.key

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-mdm-private-${each.key}"
    Tier = "private"
  })
}

resource "aws_db_subnet_group" "mdm" {
  name        = "${var.name_prefix}-mdm-subnets"
  subnet_ids  = [for s in aws_subnet.private : s.id]
  description = "Private subnets for MDM RDS PostgreSQL."
  tags        = var.tags
}

###############################################################################
# Security group: only ECS task role can reach 5432.
###############################################################################

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-mdm-rds"
  description = "RDS PostgreSQL access for MDM. Only ECS tasks may connect."
  vpc_id      = var.vpc_id
  tags        = var.tags
}

resource "aws_security_group_rule" "rds_ingress_ecs" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = var.ecs_security_group_id
  description              = "PostgreSQL from ECS tasks"
}

resource "aws_security_group_rule" "rds_egress_vpc" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  security_group_id = aws_security_group.rds.id
  cidr_blocks       = [var.vpc_cidr]
  description       = "Egress within VPC only"
}

###############################################################################
# RDS PostgreSQL instance.
###############################################################################

resource "aws_db_instance" "mdm" {
  identifier                  = "${var.name_prefix}-mdm"
  engine                      = "postgres"
  engine_version              = var.db_engine_version
  instance_class              = var.db_instance_class
  allocated_storage           = var.db_allocated_storage
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = var.db_name
  username                    = var.db_master_username
  manage_master_user_password = true
  port                        = 5432
  publicly_accessible         = false
  multi_az                    = false
  db_subnet_group_name        = aws_db_subnet_group.mdm.name
  vpc_security_group_ids      = [aws_security_group.rds.id]
  skip_final_snapshot         = false
  final_snapshot_identifier   = "${var.name_prefix}-mdm-final-${formatdate("YYYYMMDDhhmmss", timestamp())}"
  backup_retention_period     = 7
  deletion_protection         = true
  apply_immediately           = false

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-mdm"
  })

  lifecycle {
    ignore_changes = [final_snapshot_identifier]
  }
}

###############################################################################
# Secrets Manager: empty containers for operator-populated runtime values.
###############################################################################

resource "aws_secretsmanager_secret" "postgres_dsn" {
  name        = "${var.name_prefix}/mdm/postgres_dsn"
  description = "Empty PostgreSQL connection string container for MDM. Populate the value out-of-band."
  tags        = var.tags
}

resource "aws_secretsmanager_secret" "neo4j" {
  name        = "${var.name_prefix}/mdm/neo4j"
  description = "Empty Neo4j connection details container for MDM. Populate the value out-of-band."
  tags        = var.tags
}

resource "aws_secretsmanager_secret" "api_keys" {
  name        = "${var.name_prefix}/mdm/api_keys"
  description = "Empty MDM API key container. Populate the value out-of-band."
  tags        = var.tags
}
