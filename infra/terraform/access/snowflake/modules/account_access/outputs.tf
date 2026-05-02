output "role_names" {
  description = "Managed Snowflake account role names."
  value = {
    for key, role in snowflake_account_role.roles :
    key => role.name
  }
}
