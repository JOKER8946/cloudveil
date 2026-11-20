#!/usr/bin/env bash
# infra/roles.sh — idempotent RBAC role assignments for CloudVeil.
#
#   Web App managed identity -> Key Vault Crypto User (vault)
#                            -> Storage Blob Data Contributor (primary account)
#   Signed-in user           -> Key Vault Crypto Officer (create/rotate KEK)
#                            -> Storage Blob Data Contributor (primary, for tamper test)
set -euo pipefail

# Prevent Git Bash from mangling Azure resource IDs ("/subscriptions/...").
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
WEBAPP="${NAME_PREFIX}"

az account set --subscription "${AZURE_SUBSCRIPTION_ID}"

KV_ID="$(az keyvault show -n "${KV}" -g "${RG}" --query id -o tsv)"
SA_ID="$(az storage account show -n "${SA_PRIMARY}" -g "${RG}" --query id -o tsv)"
MI_PRINCIPAL="$(az webapp identity show -g "${RG}" -n "${WEBAPP}" --query principalId -o tsv)"
USER_OID="$(az ad signed-in-user show --query id -o tsv)"

assign() {
  local assignee="$1" ptype="$2" role="$3" scope="$4"
  echo "  -> ${role}"
  az role assignment create --assignee-object-id "${assignee}" --assignee-principal-type "${ptype}" \
    --role "${role}" --scope "${scope}" -o none 2>/dev/null || echo "     (already assigned)"
}

echo "=== Web App managed identity (${MI_PRINCIPAL}) ==="
assign "${MI_PRINCIPAL}" ServicePrincipal "Key Vault Crypto User"          "${KV_ID}"
assign "${MI_PRINCIPAL}" ServicePrincipal "Storage Blob Data Contributor"  "${SA_ID}"

echo "=== Signed-in user (${USER_OID}) ==="
assign "${USER_OID}" User "Key Vault Crypto Officer"         "${KV_ID}"
assign "${USER_OID}" User "Storage Blob Data Contributor"    "${SA_ID}"

echo "Done. (RBAC changes can take a minute or two to propagate.)"
