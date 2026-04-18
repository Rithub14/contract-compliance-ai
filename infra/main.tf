terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }

  # Remote state — create the storage account once with bootstrap.sh before running terraform init
  backend "azurerm" {
    resource_group_name  = "rg-tfstate"
    storage_account_name = "stcontractcomplytf"
    container_name       = "tfstate"
    key                  = "contract-compliance.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}

data "azurerm_client_config" "current" {}

# ── Resource Group ─────────────────────────────────────────────────────────────

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
}

# ── Log Analytics (required by Container Apps) ─────────────────────────────────

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.app_name}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

# ── Container Registry ─────────────────────────────────────────────────────────

resource "azurerm_container_registry" "main" {
  name                = "${replace(var.app_name, "-", "")}acr"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = var.acr_sku
  admin_enabled       = true
}

# ── Storage Account (contract blobs) ──────────────────────────────────────────

resource "azurerm_storage_account" "main" {
  name                     = "${replace(var.app_name, "-", "")}storage"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
}

resource "azurerm_storage_container" "contracts" {
  name                  = "contracts"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# ── Key Vault ──────────────────────────────────────────────────────────────────

resource "azurerm_key_vault" "main" {
  name                      = "${var.app_name}-kv"
  location                  = azurerm_resource_group.main.location
  resource_group_name       = azurerm_resource_group.main.name
  tenant_id                 = data.azurerm_client_config.current.tenant_id
  sku_name                  = "standard"
  enable_rbac_authorization = true
}

# ── Container Apps Environment ─────────────────────────────────────────────────

resource "azurerm_container_app_environment" "main" {
  name                       = "${var.app_name}-env"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

# ── API Container App ──────────────────────────────────────────────────────────

resource "azurerm_container_app" "api" {
  name                         = "${var.app_name}-api"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "api"
      image  = "${azurerm_container_registry.main.login_server}/${var.app_name}-api:latest"
      cpu    = 1.0
      memory = "2Gi"

      env {
        name  = "USE_MOCKS"
        value = "true"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

# ── UI Container App ───────────────────────────────────────────────────────────

resource "azurerm_container_app" "ui" {
  name                         = "${var.app_name}-ui"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "ui"
      image  = "${azurerm_container_registry.main.login_server}/${var.app_name}-ui:latest"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "API_BASE_URL"
        value = "https://${azurerm_container_app.api.ingress[0].fqdn}"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8501
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}
