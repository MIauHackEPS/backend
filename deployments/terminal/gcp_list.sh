#!/usr/bin/env bash
# List GCP instances (uses credentials.json by default)
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
GCP_CRED="${GCP_CRED:-./credentials.json}"
ZONE="${ZONE:-europe-west1-b}"
STATE="${1:-${STATE:-}}"

if [ -n "$STATE" ]; then
	curl -sS -G "$BASE_URL/list" --data-urlencode "credentials=${GCP_CRED}" --data-urlencode "zone=${ZONE}" --data-urlencode "state=${STATE}" | jq
else
	curl -sS -G "$BASE_URL/list" --data-urlencode "credentials=${GCP_CRED}" --data-urlencode "zone=${ZONE}" | jq
fi
