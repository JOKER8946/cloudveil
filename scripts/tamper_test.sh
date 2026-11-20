#!/usr/bin/env bash
# scripts/tamper_test.sh — prove tamper detection on the LIVE site.
#
#   upload a file -> overwrite its ciphertext blob directly via az CLI ->
#   download via the API and confirm HTTP 409 + an INTEGRITY_FAIL audit row.
set -euo pipefail
# NOTE: do NOT set MSYS_NO_PATHCONV here — it stops Git Bash from converting
# curl's /tmp cookie-jar paths to Windows paths, so curl can't write them. The
# az calls below use only short blob names, not leading-slash resource IDs.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
set -a
# shellcheck disable=SC1090
source <(grep -vE '^[[:space:]]*#' "${ROOT_DIR}/.env" | grep -vE '^[[:space:]]*$')
set +a

BASE_URL="${BASE_URL:-https://${WEBAPP_HOST:?}}"
SA_PRIMARY="${NAME_PREFIX}pri"
CONTAINER="${STORAGE_CONTAINER:-encrypted-files}"
STUDENT="smoke.student@example.com"
PW="Smoke@Test123"
TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT
CURL="curl -s -m 90"
csrf() { grep -i cv_csrf "$1" | tail -1 | awk '{print $NF}'; }

az account set --subscription "${AZURE_SUBSCRIPTION_ID}"

echo "[1] register + login student"
$CURL -o /dev/null -X POST "${BASE_URL}/api/auth/register" -H 'Content-Type: application/json' \
  --data "{\"full_name\":\"Smoke\",\"email\":\"${STUDENT}\",\"password\":\"${PW}\"}" || true
$CURL -c "${TMP}/s.jar" -X POST "${BASE_URL}/api/auth/login" -H 'Content-Type: application/json' \
  --data "{\"email\":\"${STUDENT}\",\"password\":\"${PW}\"}" >/dev/null

echo "[2] upload a file"
FID=$(printf 'tamper target %s' "$(date)" | $CURL -b "${TMP}/s.jar" -H "X-CSRF-Token: $(csrf "${TMP}/s.jar")" \
  -F "category=other" -F "file=@-;filename=tamper.txt" "${BASE_URL}/api/files" \
  | python -c "import sys,json;print(json.load(sys.stdin)['file']['id'])")
echo "    file_id=${FID}"

echo "[3] sanity download (should be 200)"
code=$($CURL -o /dev/null -w "%{http_code}" -b "${TMP}/s.jar" "${BASE_URL}/api/files/${FID}/download")
[ "$code" = "200" ] && echo "    ok (200)" || { echo "    unexpected ${code}"; exit 1; }

echo "[4] overwrite the newest ciphertext blob with junk (direct az write)"
BLOB=$(az storage blob list --account-name "${SA_PRIMARY}" --container-name "${CONTAINER}" \
  --auth-mode login --query "sort_by([], &properties.lastModified)[-1].name" -o tsv)
echo "    tampering with ${BLOB}"
az storage blob upload --account-name "${SA_PRIMARY}" --container-name "${CONTAINER}" \
  --name "${BLOB}" --auth-mode login --overwrite \
  --data "CORRUPTED-BY-TAMPER-TEST-0123456789-0123456789-0123456789" -o none

echo "[5] download again — expect 409 (integrity failure)"
code=$($CURL -o /dev/null -w "%{http_code}" -b "${TMP}/s.jar" "${BASE_URL}/api/files/${FID}/download")
if [ "$code" = "409" ]; then
  echo "    PASS: tamper detected (HTTP 409)"
else
  echo "    FAIL: expected 409, got ${code}"; exit 1
fi

echo "[6] confirm INTEGRITY_FAIL in the audit log (admin)"
$CURL -c "${TMP}/a.jar" -X POST "${BASE_URL}/api/auth/login" -H 'Content-Type: application/json' \
  --data "{\"email\":\"${SEED_ADMIN_EMAIL}\",\"password\":\"${SEED_ADMIN_PASSWORD}\"}" >/dev/null
HITS=$($CURL -b "${TMP}/a.jar" "${BASE_URL}/api/admin/audit?action=INTEGRITY_FAIL" \
  | python -c "import sys,json;print(json.load(sys.stdin)['total'])")
[ "${HITS}" -ge 1 ] && echo "    PASS: ${HITS} INTEGRITY_FAIL audit row(s)" || { echo "    FAIL: no audit row"; exit 1; }

echo
echo "== TAMPER TEST PASSED (file ${FID} is now permanently unreadable) =="
