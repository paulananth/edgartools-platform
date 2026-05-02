output "database_name" {
  description = "Provisioned Snowflake database."
  value       = snowflake_database.this.name
}

output "schema_names" {
  description = "Provisioned Snowflake schemas."
  value = {
    for key, schema in snowflake_schema.schemas :
    key => schema.name
  }
}

output "role_names" {
  description = "Snowflake account role names expected by the access-control root."
  value       = local.roles
}

output "warehouse_names" {
  description = "Provisioned Snowflake warehouses."
  value = {
    for key, warehouse in snowflake_warehouse.warehouses :
    key => warehouse.name
  }
}
