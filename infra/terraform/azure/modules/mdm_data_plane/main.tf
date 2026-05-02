resource "azurerm_mssql_server" "mdm" {
  name                          = var.sql_server_name
  resource_group_name           = var.resource_group_name
  location                      = coalesce(var.sql_location, var.location)
  version                       = "12.0"
  minimum_tls_version           = "1.2"
  public_network_access_enabled = var.sql_public_network_access_enabled
  tags                          = var.tags

  azuread_administrator {
    login_username              = var.sql_aad_admin_login_username
    object_id                   = var.sql_aad_admin_object_id
    tenant_id                   = var.tenant_id
    azuread_authentication_only = true
  }
}

resource "azurerm_mssql_database" "mdm" {
  name        = var.sql_database_name
  server_id   = azurerm_mssql_server.mdm.id
  sku_name    = var.sql_database_sku_name
  max_size_gb = var.sql_database_max_size_gb
  collation   = "SQL_Latin1_General_CP1_CI_AS"
  tags        = var.tags
}

resource "azurerm_mssql_firewall_rule" "azure_services" {
  count = var.sql_allow_azure_services ? 1 : 0

  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.mdm.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_mssql_firewall_rule" "operator" {
  for_each = var.sql_firewall_rules

  name             = each.key
  server_id        = azurerm_mssql_server.mdm.id
  start_ip_address = each.value.start_ip_address
  end_ip_address   = each.value.end_ip_address
}

resource "azurerm_storage_account" "neo4j" {
  name                            = var.neo4j_storage_account_name
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Premium"
  account_kind                    = "FileStorage"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = var.tags
}

resource "azurerm_storage_share" "neo4j" {
  name                 = "neo4j-data"
  storage_account_name = azurerm_storage_account.neo4j.name
  quota                = 100
}
