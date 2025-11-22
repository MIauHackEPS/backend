#!/usr/bin/env bash
# Script to POST deployments/astro/all_list.json to the /all/list endpoint
# Usage: ./all_list_fixed.sh [STATE]
# If STATE is provided, it overrides the `state` field in the JSON payload.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
PAYLOAD="$(dirname "$0")/../astro/all_list.json"
STATE="${1:-${STATE:-}}"

if [ ! -f "$PAYLOAD" ]; then
  echo "Payload not found: $PAYLOAD"
  exit 1
fi

if [ -n "$STATE" ]; then
  echo "Posting $PAYLOAD to $BASE_URL/all/list (state=$STATE)"
  # Use jq to override the state field and stream to curl
  jq --arg s "$STATE" '.state = $s' "$PAYLOAD" | curl -sS -X POST "$BASE_URL/all/list" -H "Content-Type: application/json" -d @- | jq
else
  echo "Posting $PAYLOAD to $BASE_URL/all/list"
  curl -sS -X POST "$BASE_URL/all/list" -H "Content-Type: application/json" -d "@${PAYLOAD}" | jq
fi

echo "Finished. Review output above."