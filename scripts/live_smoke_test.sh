#!/usr/bin/env bash
# scripts/live_smoke_test.sh — end-to-end check against the LIVE CloudVeil site.
#
#   register -> upload+encrypt -> list -> share -> officer download -> 403 for
#   an unauthorized user. Exits non-zero on the first failed assertion.
#
# Usage:
#   BASE_URL=https://<app>.azurewebsites.net bash scripts/live_smoke_test.sh
#   (BASE_URL defaults to WEBAPP_HOST from ../.env; admin creds from ../.env)
#
# Payloads are streamed via stdin / captured into variables (no temp-file paths
# passed to curl) so it works identically on Linux and Windows Git Bash. Cookie
# jars are the only files; curl handles those fine.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
set -a
# shellcheck disable=SC1090
source <(grep -vE '^[[:space:]]*#' "${ROOT_DIR}/.env" | grep -vE '^[[:space:]]*$')
set +a

BASE_URL="${BASE_URL:-https://${WEBAPP_HOST:?set BASE_URL or WEBAPP_HOST}}"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

CURL="curl -s -m 90"
PASS=0
pass() { echo "  PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $*"; exit 1; }

STUDENT="smoke.student@example.com"
OFFICER="smoke.officer@example.com"
INTRUDER="smoke.intruder@example.com"
PW="Smoke@Test123"
PAYLOAD="CloudVeil smoke-test payload $(date +%s)"

csrf() { grep -i cv_csrf "$1" | tail -1 | awk '{print $NF}'; }

jlogin() { # email jarfile
  $CURL -c "$2" -X POST "${BASE_URL}/api/auth/login" -H 'Content-Type: application/json' \
    --data "{\"email\":\"$1\",\"password\":\"${PW}\"}" >/dev/null
}

echo "== CloudVeil live smoke test against ${BASE_URL} =="

echo "[1] warm up + health"
for _ in 1 2 3; do $CURL -o /dev/null "${BASE_URL}/api/health" || true; done
code=$($CURL -o /dev/null -w "%{http_code}" "${BASE_URL}/api/health")
[ "$code" = "200" ] && pass "health 200" || fail "health was $code"

echo "[2] register student/officer/intruder (409 = already exists, ok)"
for e in "$STUDENT" "$OFFICER" "$INTRUDER"; do
  c=$($CURL -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/auth/register" \
    -H 'Content-Type: application/json' \
    --data "{\"full_name\":\"Smoke\",\"email\":\"${e}\",\"password\":\"${PW}\"}")
  { [ "$c" = "201" ] || [ "$c" = "409" ]; } && pass "register ${e} (${c})" || fail "register ${e} -> ${c}"
done

echo "[3] admin promotes officer"
$CURL -c "${TMP}/admin.jar" -X POST "${BASE_URL}/api/auth/login" \
  -H 'Content-Type: application/json' \
  --data "{\"email\":\"${SEED_ADMIN_EMAIL}\",\"password\":\"${SEED_ADMIN_PASSWORD}\"}" >/dev/null
OID=$($CURL -b "${TMP}/admin.jar" "${BASE_URL}/api/admin/users" \
  | python -c "import sys,json;us=json.load(sys.stdin)['users'];print(next(u['id'] for u in us if u['email']=='${OFFICER}'))")
code=$($CURL -o /dev/null -w "%{http_code}" -b "${TMP}/admin.jar" \
  -X PATCH "${BASE_URL}/api/admin/users/${OID}" \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $(csrf "${TMP}/admin.jar")" \
  --data '{"role":"officer"}')
[ "$code" = "200" ] && pass "promoted ${OFFICER} to officer" || fail "promote -> ${code}"

echo "[4] student login + upload"
jlogin "$STUDENT" "${TMP}/stu.jar"
UP=$(printf '%s' "$PAYLOAD" | $CURL -b "${TMP}/stu.jar" -H "X-CSRF-Token: $(csrf "${TMP}/stu.jar")" \
  -F "category=application_form" -F "file=@-;filename=payload.txt" "${BASE_URL}/api/files")
FID=$(echo "$UP" | python -c "import sys,json;print(json.load(sys.stdin)['file']['id'])")
[ -n "$FID" ] && pass "uploaded file ${FID}" || fail "upload failed: ${UP}"

echo "[5] student lists own files"
N=$($CURL -b "${TMP}/stu.jar" "${BASE_URL}/api/files" \
  | python -c "import sys,json;print(len(json.load(sys.stdin)['files']))")
[ "$N" -ge 1 ] && pass "list shows ${N} file(s)" || fail "list empty"

echo "[6] student shares with officer"
code=$($CURL -o /dev/null -w "%{http_code}" -b "${TMP}/stu.jar" \
  -H "X-CSRF-Token: $(csrf "${TMP}/stu.jar")" -H 'Content-Type: application/json' \
  -X POST "${BASE_URL}/api/files/${FID}/share" --data "{\"grantee_email\":\"${OFFICER}\"}")
[ "$code" = "200" ] && pass "shared with ${OFFICER}" || fail "share -> ${code}"

echo "[7] officer downloads shared file (plaintext must match)"
jlogin "$OFFICER" "${TMP}/off.jar"
DL=$($CURL -w $'\n%{http_code}' -b "${TMP}/off.jar" "${BASE_URL}/api/files/${FID}/download")
code="${DL##*$'\n'}"
body="${DL%$'\n'*}"
if [ "$code" = "200" ] && [ "$body" = "$PAYLOAD" ]; then
  pass "officer downloaded and plaintext matches"
else
  fail "officer download -> ${code} (content match: $([ "$body" = "$PAYLOAD" ] && echo yes || echo no))"
fi

echo "[8] unauthorized user is denied (403)"
jlogin "$INTRUDER" "${TMP}/intr.jar"
code=$($CURL -o /dev/null -w "%{http_code}" -b "${TMP}/intr.jar" \
  "${BASE_URL}/api/files/${FID}/download")
[ "$code" = "403" ] && pass "intruder denied (403)" || fail "intruder download -> ${code} (expected 403)"

echo
echo "== ALL ${PASS} CHECKS PASSED =="
