#!/usr/bin/env bash
# Script to POST deployments/astro/all_delete.json to the /all/delete endpoint
# Edit BASE_URL if your FastAPI runs on a different host/port.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
PAYLOAD="$(dirname "$0")/../astro/all_delete.json"

if [ ! -f "$PAYLOAD" ]; then
  echo "Payload not found: $PAYLOAD"
  exit 1
fi

echo "Posting $PAYLOAD to $BASE_URL/all/delete"
read -p "THIS WILL ATTEMPT TO DELETE RESOURCES IN BOTH PROVIDERS. Continue? [y/N] " confirm
confirm=${confirm:-N}
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo "Aborted by user. No requests sent."
  exit 0
fi

curl -sS -X POST "$BASE_URL/all/delete" \
  -H "Content-Type: application/json" \
  -d "@${PAYLOAD}" | jq

echo "Finished. Review output above. (Deletes are billable)"
