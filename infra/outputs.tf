output "acr_login_server" {
  description = "ACR login server — used in GitHub Actions secrets"
  value       = azurerm_container_registry.main.login_server
}

output "acr_admin_username" {
  description = "ACR admin username"
  value       = azurerm_container_registry.main.admin_username
  sensitive   = true
}

output "acr_admin_password" {
  description = "ACR admin password"
  value       = azurerm_container_registry.main.admin_password
  sensitive   = true
}

output "api_url" {
  description = "Public URL of the FastAPI service"
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "ui_url" {
  description = "Public URL of the Streamlit UI"
  value       = "https://${azurerm_container_app.ui.ingress[0].fqdn}"
}

output "key_vault_uri" {
  description = "Key Vault URI for adding secrets"
  value       = azurerm_key_vault.main.vault_uri
}

output "storage_connection_string" {
  description = "Blob storage connection string"
  value       = azurerm_storage_account.main.primary_connection_string
  sensitive   = true
}
