variable "app_name" {
  description = "Prefix used for all resource names"
  type        = string
  default     = "contract-compliance"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "westeurope"
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "rg-contract-compliance"
}

variable "acr_sku" {
  description = "Azure Container Registry SKU (Basic / Standard / Premium)"
  type        = string
  default     = "Basic"
}
