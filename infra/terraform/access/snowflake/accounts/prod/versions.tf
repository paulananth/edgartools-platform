terraform {
  required_version = ">= 1.6"
  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.0"
    }
  }
  # State holds names and public keys only. Initialise with the account's state bucket: terraform init -backend-config=...
  backend "s3" {}
}

# The access administrator is a key-pair service identity, never a person's account.
provider "snowflake" {
  organization_name = var.organization_name
  account_name      = var.account_name
  user              = var.access_admin_user
  role              = var.access_admin_role
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file(var.access_admin_private_key_file)
}
