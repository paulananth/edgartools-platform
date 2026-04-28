resource "random_password" "sql_admin" {
  length           = 24
  special          = true
  override_special = "!#$%*-_=+"
}

resource "random_password" "neo4j" {
  length           = 24
  special          = true
  override_special = "!#$%*-_=+"
}

resource "random_password" "api_key" {
  length  = 40
  special = false
}

resource "azurerm_mssql_server" "mdm" {
  name                          = var.sql_server_name
  resource_group_name           = var.resource_group_name
  location                      = coalesce(var.sql_location, var.location)
  version                       = "12.0"
  administrator_login           = var.sql_admin_username
  administrator_login_password  = random_password.sql_admin.result
  minimum_tls_version           = "1.2"
  public_network_access_enabled = var.sql_public_network_access_enabled
  tags                          = var.tags
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

resource "azurerm_container_app_environment_storage" "neo4j" {
  name                         = "${var.name_prefix}-neo4j-data"
  container_app_environment_id = var.container_app_environment_id
  account_name                 = azurerm_storage_account.neo4j.name
  share_name                   = azurerm_storage_share.neo4j.name
  access_key                   = azurerm_storage_account.neo4j.primary_access_key
  access_mode                  = "ReadWrite"
}

resource "azurerm_container_app" "neo4j" {
  name                         = "${var.name_prefix}-neo4j"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.container_app_environment_id
  revision_mode                = "Single"
  tags                         = var.tags

  secret {
    name  = "neo4j-auth"
    value = "${var.neo4j_user}/${random_password.neo4j.result}"
  }

  template {
    min_replicas = var.neo4j_min_replicas
    max_replicas = var.neo4j_max_replicas

    container {
      name   = "neo4j"
      image  = var.neo4j_image
      cpu    = var.neo4j_cpu
      memory = var.neo4j_memory

      env {
        name        = "NEO4J_AUTH"
        secret_name = "neo4j-auth"
      }

      env {
        name  = "NEO4J_server_default__listen__address"
        value = "0.0.0.0"
      }

      env {
        name  = "NEO4J_server_bolt_listen__address"
        value = "0.0.0.0:7687"
      }

      env {
        name  = "NEO4J_dbms_security_auth__enabled"
        value = "true"
      }

      volume_mounts {
        name = "neo4j-data"
        path = "/data"
      }
    }

    volume {
      name         = "neo4j-data"
      storage_name = azurerm_container_app_environment_storage.neo4j.name
      storage_type = "AzureFile"
    }
  }

  ingress {
    external_enabled = var.neo4j_external_enabled
    target_port      = 7687
    exposed_port     = 7687
    transport        = "tcp"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

locals {
  sql_server_fqdn = azurerm_mssql_server.mdm.fully_qualified_domain_name
  database_url = format(
    "mssql+pyodbc://%s:%s@%s:1433/%s?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no",
    var.sql_admin_username,
    urlencode(random_password.sql_admin.result),
    local.sql_server_fqdn,
    azurerm_mssql_database.mdm.name,
  )
  # Use bolt:// not neo4j:// — the neo4j:// scheme triggers routing discovery
  # which fails on single-instance deployments without bolt_advertised_address set.
  # Use short app name (not the full .internal. FQDN) — Azure Container Apps routes
  # internal TCP by app name through Envoy. The .internal. FQDN causes TCP timeouts
  # because Envoy's HTTP host-based routing doesn't carry into TCP connections.
  # Ref: https://learn.microsoft.com/en-us/azure/container-apps/connect-apps
  neo4j_bolt_uri = "bolt://${azurerm_container_app.neo4j.name}:7687"
  api_keys       = length(var.api_keys) > 0 ? var.api_keys : [random_password.api_key.result]
  api_keys_csv   = join(",", local.api_keys)
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "mdm-database-url"
  value        = local.database_url
  key_vault_id = var.key_vault_id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "sql_admin_username" {
  name         = "mdm-sql-admin-username"
  value        = var.sql_admin_username
  key_vault_id = var.key_vault_id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "sql_admin_password" {
  name         = "mdm-sql-admin-password"
  value        = random_password.sql_admin.result
  key_vault_id = var.key_vault_id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "neo4j" {
  name         = "mdm-neo4j"
  key_vault_id = var.key_vault_id
  tags         = var.tags
  value = jsonencode({
    uri      = local.neo4j_bolt_uri
    user     = var.neo4j_user
    password = random_password.neo4j.result
  })
}

resource "azurerm_key_vault_secret" "neo4j_uri" {
  name         = "mdm-neo4j-uri"
  value        = local.neo4j_bolt_uri
  key_vault_id = var.key_vault_id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "neo4j_user" {
  name         = "mdm-neo4j-user"
  value        = var.neo4j_user
  key_vault_id = var.key_vault_id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "neo4j_password" {
  name         = "mdm-neo4j-password"
  value        = random_password.neo4j.result
  key_vault_id = var.key_vault_id
  tags         = var.tags
}

resource "azurerm_key_vault_secret" "api_keys" {
  name         = "mdm-api-keys"
  key_vault_id = var.key_vault_id
  tags         = var.tags
  value = jsonencode({
    keys = local.api_keys
  })
}

resource "azurerm_key_vault_secret" "api_keys_csv" {
  name         = "mdm-api-keys-csv"
  key_vault_id = var.key_vault_id
  tags         = var.tags
  value        = local.api_keys_csv
}

locals {
  mdm_secret_refs = {
    mdm-database-url   = azurerm_key_vault_secret.database_url.id
    mdm-neo4j-uri      = azurerm_key_vault_secret.neo4j_uri.id
    mdm-neo4j-user     = azurerm_key_vault_secret.neo4j_user.id
    mdm-neo4j-password = azurerm_key_vault_secret.neo4j_password.id
    mdm-api-keys-csv   = azurerm_key_vault_secret.api_keys_csv.id
  }

  mdm_jobs = {
    migrate = {
      name    = "${var.name_prefix}-mdm-migrate"
      command = ["mdm", "migrate"]
    }
    run = {
      name    = "${var.name_prefix}-mdm-run"
      command = var.mdm_run_limit > 0 ? ["mdm", "run", "--entity-type", "all", "--limit", tostring(var.mdm_run_limit)] : ["mdm", "run", "--entity-type", "all"]
    }
    counts = {
      name    = "${var.name_prefix}-mdm-counts"
      command = ["mdm", "counts"]
    }
    backfill_relationships = {
      name    = "${var.name_prefix}-mdm-graph-load"
      command = ["mdm", "backfill-relationships", "--limit", "100"]
    }
    sync_graph = {
      name    = "${var.name_prefix}-mdm-graph-sync"
      command = ["mdm", "sync-graph", "--limit", "100"]
    }
    verify_graph = {
      name    = "${var.name_prefix}-mdm-graph-verify"
      command = ["mdm", "verify-graph"]
    }
  }
}

resource "azurerm_container_app" "mdm_api" {
  name                         = "${var.name_prefix}-mdm-api"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.container_app_environment_id
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.workload_identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.workload_identity_id
  }

  dynamic "secret" {
    for_each = local.mdm_secret_refs
    content {
      name                = secret.key
      identity            = var.workload_identity_id
      key_vault_secret_id = secret.value
    }
  }

  template {
    min_replicas = var.mdm_api_min_replicas
    max_replicas = var.mdm_api_max_replicas

    container {
      name   = "mdm-api"
      image  = var.container_image
      cpu    = var.mdm_api_cpu
      memory = var.mdm_api_memory
      args   = ["mdm", "api", "--host", "0.0.0.0", "--port", "8080"]

      env {
        name  = "AZURE_CLIENT_ID"
        value = var.workload_identity_client_id
      }

      env {
        name        = "MDM_DATABASE_URL"
        secret_name = "mdm-database-url"
      }

      env {
        name        = "NEO4J_URI"
        secret_name = "mdm-neo4j-uri"
      }

      env {
        name        = "NEO4J_USER"
        secret_name = "mdm-neo4j-user"
      }

      env {
        name        = "NEO4J_PASSWORD"
        secret_name = "mdm-neo4j-password"
      }

      env {
        name        = "MDM_API_KEYS"
        secret_name = "mdm-api-keys-csv"
      }
    }
  }

  ingress {
    external_enabled = var.mdm_api_external_enabled
    target_port      = 8080
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

resource "azurerm_container_app_job" "mdm" {
  for_each = local.mdm_jobs

  name                         = each.value.name
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = var.container_app_environment_id
  replica_timeout_in_seconds   = 7200
  replica_retry_limit          = 1
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.workload_identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.workload_identity_id
  }

  dynamic "secret" {
    for_each = local.mdm_secret_refs
    content {
      name                = secret.key
      identity            = var.workload_identity_id
      key_vault_secret_id = secret.value
    }
  }

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name   = "mdm"
      image  = var.container_image
      cpu    = 1
      memory = "2Gi"
      args   = each.value.command

      env {
        name  = "AZURE_CLIENT_ID"
        value = var.workload_identity_client_id
      }

      env {
        name        = "MDM_DATABASE_URL"
        secret_name = "mdm-database-url"
      }

      env {
        name        = "NEO4J_URI"
        secret_name = "mdm-neo4j-uri"
      }

      env {
        name        = "NEO4J_USER"
        secret_name = "mdm-neo4j-user"
      }

      env {
        name        = "NEO4J_PASSWORD"
        secret_name = "mdm-neo4j-password"
      }

      env {
        name        = "MDM_API_KEYS"
        secret_name = "mdm-api-keys-csv"
      }

      dynamic "env" {
        for_each = var.mdm_silver_duckdb_path == null ? {} : { MDM_SILVER_DUCKDB = var.mdm_silver_duckdb_path }
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }
}
