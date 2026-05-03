###############################################################################
# MDM data plane: RDS PostgreSQL + private subnets + Secrets Manager.
#
# Toggled via var.mdm_enabled (default false). Reuses the existing VPC and the
# ECS task security group so only canonical warehouse tasks can reach Postgres.
###############################################################################

module "mdm" {
  count  = var.mdm_enabled ? 1 : 0
  source = "../../modules/mdm_database"

  environment = local.environment
  name_prefix = "edgartools-${local.environment}"

  vpc_id                = module.network.vpc_id
  vpc_cidr              = var.vpc_cidr
  private_subnet_cidrs  = var.mdm_private_subnet_cidrs
  availability_zones    = var.availability_zones
  ecs_security_group_id = module.network.public_ecs_security_group_id

  db_instance_class = var.mdm_db_instance_class
  db_engine_version = var.mdm_db_engine_version

  tags = var.tags
}
