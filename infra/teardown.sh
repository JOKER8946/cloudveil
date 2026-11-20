#!/usr/bin/env bash
# infra/teardown.sh — delete the CloudVeil resource group (DESTRUCTIVE).
#
# Asks for explicit confirmation. Note: the Key Vault has purge protection, so
# its name stays soft-deleted for the retention window and cannot be purged
# early.
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
az account set --subscription "${AZURE_SUBSCRIPTION_ID}"

echo "This will DELETE the entire resource group: ${RG}"
read -r -p "Type the resource group name to confirm: " CONFIRM
if [ "${CONFIRM}" != "${RG}" ]; then
  echo "Aborted."
  exit 1
fi

az group delete -n "${RG}" --yes
echo "Deletion started for ${RG}."
