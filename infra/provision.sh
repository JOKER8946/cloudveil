#!/usr/bin/env bash
# infra/provision.sh — idempotent provisioning of all CloudVeil Azure resources.
#
# Reads configuration from ../.env. Safe to re-run: every resource is created
# only if it does not already exist. Creates PAID resources — run only with the
# user's approval.
set -euo pipefail

# Git Bash on Windows rewrites args that look like POSIX paths (e.g. Azure
# resource IDs starting with "/subscriptions/...") into Windows paths. Disable
# that so resource IDs pass through to az unchanged.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

# ---- load .env (ignore comments / blank lines) ----
if [ ! -f "${ENV_FILE}" ]; then
  echo "ERROR: ${ENV_FILE} not found." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source <(grep -vE '^[[:space:]]*#' "${ENV_FILE}" | grep -vE '^[[:space:]]*$')
set +a

: "${AZURE_SUBSCRIPTION_ID:?missing in .env}"
: "${AZURE_RESOURCE_GROUP:?missing in .env}"
: "${AZURE_PRIMARY_REGION:?missing in .env}"
: "${AZURE_SECONDARY_REGION:?missing in .env}"
: "${NAME_PREFIX:?missing in .env}"
: "${MYSQL_ADMIN_USER:?missing in .env}"
: "${MYSQL_ADMIN_PASSWORD:?missing in .env}"

# ---- derived, non-secret resource names ----
RG="${AZURE_RESOURCE_GROUP}"
LOC="${AZURE_PRIMARY_REGION}"
LOC2="${AZURE_SECONDARY_REGION}"
KV="kv-${NAME_PREFIX}"
KEK_NAME="${KEK_NAME:-cloudveil-kek}"
SA_PRIMARY="${NAME_PREFIX}pri"
SA_SECONDARY="${NAME_PREFIX}sec"
CONTAINER="${STORAGE_CONTAINER:-encrypted-files}"
MYSQL_SERVER="mysql-${NAME_PREFIX}"
MYSQL_DB="cloudveil"
LAW="log-${NAME_PREFIX}"
APPI="appi-${NAME_PREFIX}"
PLAN="plan-${NAME_PREFIX}"
WEBAPP="${NAME_PREFIX}"

log()  { echo; echo "=== $* ==="; }
have() { "$@" >/dev/null 2>&1; }

upsert_env() {
  # Write a non-secret derived value back into .env (update or append).
  local key="$1" val="$2"
  if grep -qE "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    grep -vE "^${key}=" "${ENV_FILE}" > "${ENV_FILE}.tmp" && mv "${ENV_FILE}.tmp" "${ENV_FILE}"
  fi
  # Ensure the file ends with a newline before appending (avoids gluing the new
  # line onto a file that has no trailing newline).
  if [ -s "${ENV_FILE}" ] && [ "$(tail -c1 "${ENV_FILE}"; echo x)" != $'\nx' ]; then
    echo >> "${ENV_FILE}"
  fi
  echo "${key}=${val}" >> "${ENV_FILE}"
}

az account set --subscription "${AZURE_SUBSCRIPTION_ID}" --only-show-errors
echo "Subscription: $(az account show --query name -o tsv)"
SIGNED_IN_OBJECT_ID="$(az ad signed-in-user show --query id -o tsv)"

# ---------------------------------------------------------------------------
log "Resource group ${RG} (${LOC})"
if [ "$(az group exists -n "${RG}")" = "true" ]; then echo "exists";
else az group create -n "${RG}" -l "${LOC}" -o none; echo "created"; fi

# ---------------------------------------------------------------------------
log "Log Analytics workspace ${LAW}"
if have az monitor log-analytics workspace show -g "${RG}" -n "${LAW}"; then echo "exists";
else az monitor log-analytics workspace create -g "${RG}" -n "${LAW}" -l "${LOC}" -o none; echo "created"; fi
WORKSPACE_ID="$(az monitor log-analytics workspace show -g "${RG}" -n "${LAW}" --query id -o tsv)"

log "Application Insights ${APPI}"
az extension add -n application-insights --only-show-errors -o none 2>/dev/null || true
if have az monitor app-insights component show --app "${APPI}" -g "${RG}"; then echo "exists";
else
  az monitor app-insights component create --app "${APPI}" -g "${RG}" -l "${LOC}" \
    --workspace "${WORKSPACE_ID}" --application-type web -o none
  echo "created"
fi
APPI_CONN="$(az monitor app-insights component show --app "${APPI}" -g "${RG}" --query connectionString -o tsv)"

# ---------------------------------------------------------------------------
log "Key Vault ${KV} (RBAC, purge protection)"
if have az keyvault show -n "${KV}" -g "${RG}"; then echo "exists";
else
  az keyvault create -n "${KV}" -g "${RG}" -l "${LOC}" \
    --enable-rbac-authorization true \
    --enable-purge-protection true \
    --retention-days 90 -o none
  echo "created"
fi
KV_URL="$(az keyvault show -n "${KV}" -g "${RG}" --query properties.vaultUri -o tsv)"
KV_ID="$(az keyvault show -n "${KV}" -g "${RG}" --query id -o tsv)"

# Signed-in user needs Crypto Officer to create/rotate the KEK (RBAC vault).
log "Grant signed-in user 'Key Vault Crypto Officer' on ${KV}"
az role assignment create --assignee-object-id "${SIGNED_IN_OBJECT_ID}" \
  --assignee-principal-type User \
  --role "Key Vault Crypto Officer" --scope "${KV_ID}" -o none 2>/dev/null || echo "already assigned"
echo "Waiting 30s for RBAC propagation before key creation..."
sleep 30

log "RSA-3072 key ${KEK_NAME}"
if have az keyvault key show --vault-name "${KV}" --name "${KEK_NAME}"; then echo "exists";
else
  az keyvault key create --vault-name "${KV}" --name "${KEK_NAME}" \
    --kty RSA --size 3072 --ops wrapKey unwrapKey -o none
  echo "created"
fi

# ---------------------------------------------------------------------------
provision_storage() {
  local account="$1" location="$2" with_change_feed="$3"
  log "Storage account ${account} (${location})"
  if have az storage account show -n "${account}" -g "${RG}"; then echo "exists";
  else
    az storage account create -n "${account}" -g "${RG}" -l "${location}" \
      --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \
      --allow-blob-public-access false -o none
    echo "created"
  fi
  if [ "${with_change_feed}" = "true" ]; then
    az storage account blob-service-properties update --account-name "${account}" -g "${RG}" \
      --enable-versioning true --enable-change-feed true -o none
  else
    az storage account blob-service-properties update --account-name "${account}" -g "${RG}" \
      --enable-versioning true -o none
  fi
  # Private container (created via account key at provision time; app uses Managed Identity).
  local key
  key="$(az storage account keys list -n "${account}" -g "${RG}" --query '[0].value' -o tsv)"
  if have az storage container show --account-name "${account}" --account-key "${key}" --name "${CONTAINER}"; then
    echo "container ${CONTAINER} exists"
  else
    az storage container create --account-name "${account}" --account-key "${key}" \
      --name "${CONTAINER}" --public-access off -o none
    echo "container ${CONTAINER} created"
  fi
}

provision_storage "${SA_PRIMARY}" "${LOC}" "true"
provision_storage "${SA_SECONDARY}" "${LOC2}" "false"
SA_PRIMARY_URL="$(az storage account show -n "${SA_PRIMARY}" -g "${RG}" --query primaryEndpoints.blob -o tsv)"

# ---------------------------------------------------------------------------
log "MySQL Flexible Server ${MYSQL_SERVER} (Burstable B1ms) — this can take several minutes"
if have az mysql flexible-server show -n "${MYSQL_SERVER}" -g "${RG}"; then echo "exists";
else
  az mysql flexible-server create -n "${MYSQL_SERVER}" -g "${RG}" -l "${LOC}" \
    --admin-user "${MYSQL_ADMIN_USER}" --admin-password "${MYSQL_ADMIN_PASSWORD}" \
    --sku-name Standard_B1ms --tier Burstable \
    --storage-size 20 --version 8.0.21 \
    --public-access None --yes -o none
  echo "created"
fi
# Allow Azure services only (App Service outbound) through the firewall.
az mysql flexible-server firewall-rule create -g "${RG}" -n "${MYSQL_SERVER}" \
  --rule-name AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 -o none 2>/dev/null || true
# Enforce TLS.
az mysql flexible-server parameter set -g "${RG}" -s "${MYSQL_SERVER}" \
  --name require_secure_transport --value ON -o none 2>/dev/null || true
if have az mysql flexible-server db show -g "${RG}" -s "${MYSQL_SERVER}" -d "${MYSQL_DB}"; then
  echo "database ${MYSQL_DB} exists"
else
  az mysql flexible-server db create -g "${RG}" -s "${MYSQL_SERVER}" -d "${MYSQL_DB}" -o none
  echo "database ${MYSQL_DB} created"
fi
MYSQL_HOST="$(az mysql flexible-server show -n "${MYSQL_SERVER}" -g "${RG}" --query fullyQualifiedDomainName -o tsv)"

# ---------------------------------------------------------------------------
log "App Service plan ${PLAN} (Linux B1)"
if have az appservice plan show -g "${RG}" -n "${PLAN}"; then echo "exists";
else az appservice plan create -g "${RG}" -n "${PLAN}" --is-linux --sku B1 -l "${LOC}" -o none; echo "created"; fi

log "Web App ${WEBAPP} (Python 3.12)"
if have az webapp show -g "${RG}" -n "${WEBAPP}"; then echo "exists";
else az webapp create -g "${RG}" -p "${PLAN}" -n "${WEBAPP}" --runtime "PYTHON:3.12" -o none; echo "created"; fi
az webapp update -g "${RG}" -n "${WEBAPP}" --https-only true -o none
az webapp identity assign -g "${RG}" -n "${WEBAPP}" -o none
az webapp config set -g "${RG}" -n "${WEBAPP}" --startup-file "bash startup.sh" -o none
WEBAPP_HOST="$(az webapp show -g "${RG}" -n "${WEBAPP}" --query defaultHostName -o tsv)"

# ---------------------------------------------------------------------------
# Persist non-secret derived names back into .env for later scripts.
upsert_env KEYVAULT_URL        "${KV_URL}"
upsert_env KEK_NAME            "${KEK_NAME}"
upsert_env STORAGE_ACCOUNT_URL "${SA_PRIMARY_URL}"
upsert_env STORAGE_CONTAINER   "${CONTAINER}"
upsert_env PRIMARY_REGION      "${LOC}"
upsert_env MYSQL_HOST          "${MYSQL_HOST}"
upsert_env MYSQL_DATABASE      "${MYSQL_DB}"
upsert_env WEBAPP_NAME         "${WEBAPP}"
upsert_env WEBAPP_HOST         "${WEBAPP_HOST}"
upsert_env SA_SECONDARY        "${SA_SECONDARY}"
upsert_env APPLICATIONINSIGHTS_CONNECTION_STRING "${APPI_CONN}"

# ---------------------------------------------------------------------------
cat <<SUMMARY

============================================================
  CloudVeil provisioning complete
============================================================
  Resource group : ${RG}
  Key Vault      : ${KV}   (KEK: ${KEK_NAME})
  Storage        : ${SA_PRIMARY} (primary) / ${SA_SECONDARY} (secondary)
  Container      : ${CONTAINER}
  MySQL          : ${MYSQL_HOST}  (db: ${MYSQL_DB})
  App Insights   : ${APPI}
  Web App        : https://${WEBAPP_HOST}
------------------------------------------------------------
  Non-secret names written back to .env.
  Next: infra/roles.sh, infra/github_oidc.sh, infra/app_settings.sh
============================================================
SUMMARY
