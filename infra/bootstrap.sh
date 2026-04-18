#!/usr/bin/env bash
# Run this ONCE before the first `terraform init`.
# Creates the storage account that holds the Terraform state file.
set -euo pipefail

LOCATION="westeurope"
RG="rg-tfstate"
SA="stcontractcomplytf"   # must be globally unique, 3-24 lowercase alphanumeric
CONTAINER="tfstate"

az group create --name "$RG" --location "$LOCATION"
az storage account create --name "$SA" --resource-group "$RG" \
  --location "$LOCATION" --sku Standard_LRS --min-tls-version TLS1_2
az storage container create --name "$CONTAINER" --account-name "$SA"

echo ""
echo "Bootstrap complete. Now run:"
echo "  cd infra && terraform init"
