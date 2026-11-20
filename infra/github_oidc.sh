#!/usr/bin/env bash
# infra/github_oidc.sh — set up GitHub Actions -> Azure deployment via OIDC.
#
# Creates an Entra app registration + federated credential scoped to the repo's
# main branch, grants it Contributor on the resource group, and stores the
# AZURE_* client/tenant/subscription IDs as GitHub Actions secrets.
#
# NOTE: requires permission to create Entra app registrations. On locked-down
# school/university tenants this may fail (AuthorizationFailed) — if so, we fall
# back to publish-profile deployment (see infra/README.md).
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

: "${GITHUB_REPO:?missing in .env, e.g. user/cloudveil}"
RG="${AZURE_RESOURCE_GROUP}"
APP_NAME="cloudveil-github-oidc"

# GitHub may issue OIDC tokens with an "immutable" subject that embeds numeric
# owner/repo IDs (repo:owner@<id>/repo@<id>:...). Derive the exact subject
# prefix from GitHub so the federated credential matches whatever it presents,
# falling back to the classic format if the API doesn't expose a prefix.
SUB_PREFIX="$(gh api "repos/${GITHUB_REPO}/actions/oidc/customization/sub" --jq '.sub_claim_prefix' 2>/dev/null || true)"
if [ -n "${SUB_PREFIX}" ] && [ "${SUB_PREFIX}" != "null" ]; then
  SUBJECT="${SUB_PREFIX}:ref:refs/heads/main"
else
  SUBJECT="repo:${GITHUB_REPO}:ref:refs/heads/main"
fi

az account set --subscription "${AZURE_SUBSCRIPTION_ID}"
TENANT_ID="$(az account show --query tenantId -o tsv)"

echo "=== Entra app registration '${APP_NAME}' ==="
APP_ID="$(az ad app list --display-name "${APP_NAME}" --query '[0].appId' -o tsv 2>/dev/null || true)"
if [ -z "${APP_ID}" ]; then
  APP_ID="$(az ad app create --display-name "${APP_NAME}" --query appId -o tsv)"
  echo "created app ${APP_ID}"
else
  echo "reusing app ${APP_ID}"
fi

# Service principal for the app.
if ! az ad sp show --id "${APP_ID}" >/dev/null 2>&1; then
  az ad sp create --id "${APP_ID}" -o none
  echo "created service principal"
fi
SP_OID="$(az ad sp show --id "${APP_ID}" --query id -o tsv)"

echo "=== Federated credential for ${SUBJECT} ==="
if az ad app federated-credential list --id "${APP_ID}" \
      --query "[?subject=='${SUBJECT}']" -o tsv | grep -q .; then
  echo "exists"
else
  # Remove any stale 'github-main' credential (e.g. an old subject) so the name
  # is free, then create one with the correct subject.
  az ad app federated-credential delete --id "${APP_ID}" \
    --federated-credential-id github-main -o none 2>/dev/null || true
  az ad app federated-credential create --id "${APP_ID}" --parameters "{
    \"name\": \"github-main\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"${SUBJECT}\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
  echo "created"
fi

echo "=== Contributor on resource group ${RG} ==="
RG_ID="$(az group show -n "${RG}" --query id -o tsv)"
az role assignment create --assignee-object-id "${SP_OID}" --assignee-principal-type ServicePrincipal \
  --role "Contributor" --scope "${RG_ID}" -o none 2>/dev/null || echo "already assigned"

echo "=== Setting GitHub Actions secrets on ${GITHUB_REPO} ==="
gh secret set AZURE_CLIENT_ID       --repo "${GITHUB_REPO}" --body "${APP_ID}"
gh secret set AZURE_TENANT_ID       --repo "${GITHUB_REPO}" --body "${TENANT_ID}"
gh secret set AZURE_SUBSCRIPTION_ID --repo "${GITHUB_REPO}" --body "${AZURE_SUBSCRIPTION_ID}"

echo "Done. AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_SUBSCRIPTION_ID set as repo secrets."
