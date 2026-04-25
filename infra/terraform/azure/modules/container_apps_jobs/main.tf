locals {
  base_environment = {
    WAREHOUSE_ENVIRONMENT  = var.environment
    WAREHOUSE_RUNTIME_MODE = var.warehouse_runtime_mode
    WAREHOUSE_BRONZE_ROOT  = var.warehouse_bronze_root
    WAREHOUSE_STORAGE_ROOT = var.warehouse_storage_root
    SERVING_EXPORT_ROOT    = var.serving_export_root
  }

  workflow_job_suffixes = {
    bootstrap_recent_10 = "boot-recent-10"
    daily_incremental   = "daily-incr"
    full_reconcile      = "full-reconcile"
  }
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "${var.name_prefix}-logs"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

resource "azurerm_container_app_environment" "this" {
  name                       = "${var.name_prefix}-jobs"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  tags                       = var.tags
}

resource "azurerm_user_assigned_identity" "jobs" {
  name                = "${var.name_prefix}-jobs"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.jobs.principal_id
}

resource "azurerm_role_assignment" "storage_blob_contributor" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.jobs.principal_id
}

resource "azurerm_key_vault_access_policy" "jobs" {
  key_vault_id = var.key_vault_id
  tenant_id    = var.tenant_id
  object_id    = azurerm_user_assigned_identity.jobs.principal_id

  secret_permissions = [
    "Get",
  ]
}

resource "azurerm_container_app_job" "workflow" {
  for_each = var.workflows

  name                         = "${var.name_prefix}-${lookup(local.workflow_job_suffixes, each.key, replace(each.key, "_", "-"))}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = azurerm_container_app_environment.this.id
  replica_timeout_in_seconds   = 7200
  replica_retry_limit          = 1
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.jobs.id]
  }

  registry {
    server   = var.acr_login_server
    identity = azurerm_user_assigned_identity.jobs.id
  }

  secret {
    name                = "edgar-identity"
    identity            = azurerm_user_assigned_identity.jobs.id
    key_vault_secret_id = var.edgar_identity_secret_uri
  }

  dynamic "manual_trigger_config" {
    for_each = try(each.value.schedule, null) == null ? [1] : []
    content {
      parallelism              = try(each.value.parallelism, 1)
      replica_completion_count = 1
    }
  }

  dynamic "schedule_trigger_config" {
    for_each = try(each.value.schedule, null) == null ? [] : [each.value.schedule]
    content {
      cron_expression          = schedule_trigger_config.value
      parallelism              = try(each.value.parallelism, 1)
      replica_completion_count = 1
    }
  }

  template {
    container {
      name   = "edgar-warehouse"
      image  = var.container_image
      cpu    = each.value.cpu
      memory = each.value.memory
      args   = each.value.command

      env {
        name        = "EDGAR_IDENTITY"
        secret_name = "edgar-identity"
      }

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.jobs.client_id
      }

      dynamic "env" {
        for_each = local.base_environment
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  depends_on = [
    azurerm_key_vault_access_policy.jobs,
    azurerm_role_assignment.acr_pull,
    azurerm_role_assignment.storage_blob_contributor,
  ]
}
