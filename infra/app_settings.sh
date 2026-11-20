#!/usr/bin/env bash
# infra/app_settings.sh — push application settings to the App Service.
#
# Values come from .env and `az` queries. Secrets (DB password, JWT secret,
# App Insights connection string) are set but never echoed to the console.
set -euo pipefail

# Prevent Git Bash from mangling Azure resource IDs / URLs.
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
WEBAPP="${NAME_PREFIX}"
az account set --subscription "${AZURE_SUBSCRIPTION_ID}"

: "${KEYVAULT_URL:?run provision.sh first}"
: "${STORAGE_ACCOUNT_URL:?run provision.sh first}"
: "${MYSQL_HOST:?run provision.sh first}"

# Generate a JWT secret once and reuse it (don't rotate on every run).
EXISTING_JWT="$(az webapp config appsettings list -g "${RG}" -n "${WEBAPP}" \
  --query "[?name=='JWT_SECRET'].value | [0]" -o tsv 2>/dev/null || true)"
if [ -n "${EXISTING_JWT}" ]; then
  JWT_SECRET="${EXISTING_JWT}"
else
  JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
fi

echo "Pushing application settings to ${WEBAPP} (secrets not displayed)..."
az webapp config appsettings set -g "${RG}" -n "${WEBAPP}" --only-show-errors -o none --settings \
  FLASK_CONFIG="prod" \
  FLASK_APP="wsgi:app" \
  SCM_DO_BUILD_DURING_DEPLOYMENT="true" \
  RUN_SEED="false" \
  KEYVAULT_URL="${KEYVAULT_URL}" \
  KEK_NAME="${KEK_NAME:-cloudveil-kek}" \
  STORAGE_ACCOUNT_URL="${STORAGE_ACCOUNT_URL}" \
  STORAGE_CONTAINER="${STORAGE_CONTAINER:-encrypted-files}" \
  PRIMARY_REGION="${PRIMARY_REGION:-${AZURE_PRIMARY_REGION}}" \
  MYSQL_HOST="${MYSQL_HOST}" \
  MYSQL_PORT="3306" \
  MYSQL_USER="${MYSQL_ADMIN_USER}" \
  MYSQL_PASSWORD="${MYSQL_ADMIN_PASSWORD}" \
  MYSQL_DATABASE="${MYSQL_DATABASE:-cloudveil}" \
  MYSQL_SSL_CA="app/certs/DigiCertGlobalRootCA.crt.pem" \
  JWT_SECRET="${JWT_SECRET}" \
  SEED_ADMIN_EMAIL="${SEED_ADMIN_EMAIL}" \
  SEED_ADMIN_PASSWORD="${SEED_ADMIN_PASSWORD}" \
  APPLICATIONINSIGHTS_CONNECTION_STRING="${APPLICATIONINSIGHTS_CONNECTION_STRING:-}"

echo "Application settings updated."
