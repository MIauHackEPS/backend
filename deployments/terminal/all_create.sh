#!/usr/bin/env bash
# Script to POST deployments/astro/all_create.json to the /all/create endpoint
# Edit BASE_URL if your FastAPI runs on a different host/port.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
PAYLOAD="$(dirname "$0")/../astro/all_create.json"

if [ ! -f "$PAYLOAD" ]; then
  echo "Payload not found: $PAYLOAD"
  exit 1
fi

echo "Posting $PAYLOAD to $BASE_URL/all/create"
curl -sS -X POST "$BASE_URL/all/create" \
  -H "Content-Type: application/json" \
  -d "@${PAYLOAD}" | jq

echo "Finished. Review output above. (Creates are billable)"
