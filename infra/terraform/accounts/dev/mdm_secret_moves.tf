###############################################################################
# MDM secret ownership migration.
#
# The MDM runtime now uses Snowflake Postgres. Runtime secret containers live in
# the warehouse_runtime module so Terraform keeps managing empty containers while
# secret values stay out of Terraform state.
###############################################################################

moved {
  from = module.mdm[0].aws_secretsmanager_secret.postgres_dsn
  to   = module.runtime.aws_secretsmanager_secret.mdm_postgres_dsn
}

moved {
  from = module.mdm[0].aws_secretsmanager_secret.api_keys
  to   = module.runtime.aws_secretsmanager_secret.mdm_api_keys
}

moved {
  from = module.mdm[0].aws_secretsmanager_secret.snowflake
  to   = module.runtime.aws_secretsmanager_secret.mdm_snowflake
}
