#!/usr/bin/env bash
# infra/replication.sh — enable Azure Blob Object Replication of the ciphertext
# container from the primary storage account to the secondary-region account.
#
# Requires (already set by provision.sh): change feed + versioning on the
# source, versioning on the destination. Idempotent.
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
SRC="${NAME_PREFIX}pri"
DEST="${NAME_PREFIX}sec"
CONTAINER="${STORAGE_CONTAINER:-encrypted-files}"
az account set --subscription "${AZURE_SUBSCRIPTION_ID}"

# Final state = the SOURCE account has the policy (both sides are then linked).
# sourceAccount/destinationAccount are full resource IDs, so match by substring.
if az storage account or-policy list -g "${RG}" -n "${SRC}" --query "[?contains(destinationAccount, '${DEST}')]" -o tsv 2>/dev/null | grep -q .; then
  echo "Object replication already configured (${SRC} -> ${DEST})."
  exit 0
fi

# Reuse the destination policy if it already exists, else create it.
POLICY_JSON="$(az storage account or-policy list -g "${RG}" -n "${DEST}" \
  --query "[?contains(sourceAccount, '${SRC}')] | [0]" -o json 2>/dev/null || echo null)"
if [ "${POLICY_JSON}" = "null" ] || [ -z "${POLICY_JSON}" ]; then
  echo "Creating object replication policy on destination ${DEST}..."
  POLICY_JSON="$(az storage account or-policy create -g "${RG}" -n "${DEST}" \
    --source-account "${SRC}" --destination-account "${DEST}" \
    --source-container "${CONTAINER}" --destination-container "${CONTAINER}" -o json)"
fi

echo "Applying the same policy to source ${SRC}..."
POLICY_FILE="${SCRIPT_DIR}/.orpolicy.json"
echo "${POLICY_JSON}" > "${POLICY_FILE}"
# az is a Windows process under Git Bash; give it a path it can open.
if command -v cygpath >/dev/null 2>&1; then
  POLICY_FILE="$(cygpath -w "${POLICY_FILE}")"
fi
az storage account or-policy create -g "${RG}" -n "${SRC}" --policy "@${POLICY_FILE}" -o none
rm -f "${SCRIPT_DIR}/.orpolicy.json"

echo "Object replication enabled: ${SRC}/${CONTAINER} -> ${DEST}/${CONTAINER}"
echo "New blobs replicate asynchronously (minutes)."
