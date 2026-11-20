#!/usr/bin/env bash
# infra/diagnostics.sh — route Key Vault AuditEvent logs and Storage blob
# logs to the Log Analytics workspace. Idempotent.
set -euo pipefail
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
set -a
# shellcheck disable=SC1090
source <(grep -vE '^[[:space:]]*#' "${ENV_FILE}" | grep -vE '^[[:space:]]*$')
set +a

RG="${AZURE_RESOURCE_GROUP}"
KV="kv-${NAME_PREFIX}"
SA_PRIMARY="${NAME_PREFIX}pri"
LAW="log-${NAME_PREFIX}"
az account set --subscription "${AZURE_SUBSCRIPTION_ID}"

WORKSPACE_ID="$(az monitor log-analytics workspace show -g "${RG}" -n "${LAW}" --query id -o tsv)"
KV_ID="$(az keyvault show -n "${KV}" -g "${RG}" --query id -o tsv)"
BLOB_ID="$(az storage account show -n "${SA_PRIMARY}" -g "${RG}" --query id -o tsv)/blobServices/default"

echo "Key Vault AuditEvent -> Log Analytics..."
az monitor diagnostic-settings create --name cv-kv-diag \
  --resource "${KV_ID}" --workspace "${WORKSPACE_ID}" \
  --logs '[{"category":"AuditEvent","enabled":true}]' -o none 2>/dev/null \
  || echo "  (already configured)"

echo "Storage blob read/write/delete -> Log Analytics..."
az monitor diagnostic-settings create --name cv-blob-diag \
  --resource "${BLOB_ID}" --workspace "${WORKSPACE_ID}" \
  --logs '[{"category":"StorageRead","enabled":true},{"category":"StorageWrite","enabled":true},{"category":"StorageDelete","enabled":true}]' \
  -o none 2>/dev/null || echo "  (already configured)"

echo "Diagnostics configured. Key Vault unwrap events appear in the"
echo "AzureDiagnostics table (KQL):"
echo '  AzureDiagnostics | where ResourceProvider == "MICROSOFT.KEYVAULT" and OperationName == "KeyUnwrap" | order by TimeGenerated desc'
