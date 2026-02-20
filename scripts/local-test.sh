#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env.local"
  set +a
fi

if [[ -z "${LOCAL_DEV_WALLET:-}" ]]; then
  echo "missing LOCAL_DEV_WALLET. add it to .env.local first."
  echo "example: echo 'LOCAL_DEV_WALLET=<your_solana_wallet>' >> .env.local"
  exit 1
fi

BASE_URL="${RECON_BASE_URL:-http://127.0.0.1:8080}"
MAX_SIGNATURES="${RECON_MAX_SIGNATURES:-20}"

echo "checking health at ${BASE_URL}/health"
curl -fsS "${BASE_URL}/health"
echo

echo "requesting wallet report for ${LOCAL_DEV_WALLET}"
response="$(
  curl -sS -w '\n%{http_code}' "${BASE_URL}/v1/wallet/report" \
    -H 'content-type: application/json' \
    -d "{\"wallet\":\"${LOCAL_DEV_WALLET}\",\"max_signatures\":${MAX_SIGNATURES}}"
)"
http_code="${response##*$'\n'}"
response_body="${response%$'\n'*}"
echo "${response_body}"

if [[ "${http_code}" != "200" ]]; then
  echo "request failed with status ${http_code}"
  if [[ "${http_code}" == "503" ]]; then
    echo "hint: solana rpc is likely rate-limited. set SOLANA_RPC_URL to a private provider endpoint."
  fi
  exit 1
fi
echo
