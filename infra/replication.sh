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

if az storage account or-policy list -g "${RG}" -n "${DEST}" --query "[?sourceAccount=='${SRC}']" -o tsv 2>/dev/null | grep -q .; then
  echo "Object replication policy already exists (${SRC} -> ${DEST})."
  exit 0
fi

echo "Creating object replication policy on destination ${DEST}..."
POLICY_JSON="$(az storage account or-policy create -g "${RG}" -n "${DEST}" \
  --source-account "${SRC}" --destination-account "${DEST}" \
  --source-container "${CONTAINER}" --destination-container "${CONTAINER}" -o json)"

echo "Applying the same policy to source ${SRC}..."
echo "${POLICY_JSON}" > "${SCRIPT_DIR}/.orpolicy.json"
az storage account or-policy create -g "${RG}" -n "${SRC}" \
  --policy "@${SCRIPT_DIR}/.orpolicy.json" -o none
rm -f "${SCRIPT_DIR}/.orpolicy.json"

echo "Object replication enabled: ${SRC}/${CONTAINER} -> ${DEST}/${CONTAINER}"
echo "New blobs replicate asynchronously (minutes)."
